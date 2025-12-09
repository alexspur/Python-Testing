# instruments/wj.py

import serial
import serial.tools.list_ports

SOH = b"\x01"
CR = b"\r"


ERROR_MESSAGES = {
    1: "Undefined command code (not S, Q, or V)",
    2: "Checksum error",
    3: "Extra byte(s) received",
    4: "Illegal digital control byte (HV ON/OFF/RESET conflict)",
    5: "Illegal Set command while fault active (Reset required)",
    6: "Processing error in power supply",
}


class WJPowerSupply:
    """
    Driver for XP Glassman WJ Series over USB/RS-232.

    Implements:
      - SET command ('S') for voltage, current, HV ON, HV OFF, RESET
      - QUERY command ('Q') for monitors + status
      - VERSION command ('V')
      - Error decoding (E packets)

    Scaling assumes WJ100P6.0: 0–100 kV, 0–6 mA.
    """

    def __init__(self, vmax_kv: float = 100.0, imax_ma: float = 6.0):
        self.vmax_kv = float(vmax_kv)
        self.imax_ma = float(imax_ma)
        self.ser: serial.Serial | None = None

        # Last commanded analog setpoints (so we can send HV ON/OFF/RESET
        # without changing V/I each time)
        self.v_set_kv: float = 0.0
        self.i_set_ma: float = 0.0

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------
    @staticmethod
    def list_ports():
        return [p.device for p in serial.tools.list_ports.comports()]

    def connect(self, port: str, baudrate: int = 9600, timeout: float = 0.3):
        self.close()
        self.ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout,
        )

    def close(self):
        if self.ser is not None:
            self.ser.close()
            self.ser = None

    @property
    def is_connected(self) -> bool:
        return self.ser is not None and self.ser.is_open

    # ------------------------------------------------------------------
    # Low-level protocol
    # ------------------------------------------------------------------
    def _build_packet(self, core: str) -> bytes:
        """
        core: ASCII body (e.g. 'Q', 'V', or full 'S....' data).
        Returns SOH + core + checksum(ASCII hex) + CR.
        Checksum is modulo-256 sum of core bytes (no SOH).
        """
        body = core.encode("ascii")
        cs = sum(body) & 0xFF
        cs_ascii = f"{cs:02X}".encode("ascii")  # e.g. 0x51 -> b"51"
        return SOH + body + cs_ascii + CR

    def _write_readline(self, core: str) -> str:
        if not self.is_connected:
            raise RuntimeError("WJPowerSupply not connected")

        pkt = self._build_packet(core)
        self.ser.reset_input_buffer()
        self.ser.write(pkt)
        line = self.ser.readline().decode("ascii", errors="ignore").strip()
        return line

    # ------------------------------------------------------------------
    # High-level commands
    # ------------------------------------------------------------------
    def query(self) -> dict:
        """
        Send Q command, parse R response into engineering units.

        Returns dict:
            {
              'type': 'R',
              'raw': 'R......',
              'kv': float,
              'ma': float,
              'control_mode': 'V' or 'I',
              'fault': bool,
              'hv_on': bool,
            }
        or an error dict if an E packet is seen.
        """
        resp = self._write_readline("Q")

        if not resp:
            return {"type": "NONE", "raw": ""}

        if resp.startswith("E"):
            return self._parse_error(resp)

        if not resp.startswith("R"):
            return {"type": "UNKNOWN", "raw": resp}

        # R packet: bytes 2-4 = V (0–3FF), 5-7 = I (0–3FF),
        # 8-10 reserved, 11-13 digital status (3 hex chars). :contentReference[oaicite:1]{index=1}
        s = resp.strip()
        if len(s) < 13:
            return {"type": "R", "raw": s, "parse_error": "short response"}

        try:
            v_code = int(s[1:4], 16)
            i_code = int(s[4:7], 16)
        except ValueError:
            return {"type": "R", "raw": s, "parse_error": "bad hex in V/I"}

        # Digital monitors (12 bits across three ASCII hex chars)
        try:
            dig_str = s[10:13]  # bytes 11-13
            dig_val = int(dig_str, 16)
        except ValueError:
            dig_val = 0

        byte11 = dig_val & 0xF  # lowest nibble: control mode, fault, HV ON
        control_mode_current = bool(byte11 & 0x1)  # 1 = current mode :contentReference[oaicite:2]{index=2}
        fault = bool(byte11 & 0x2)                # 1 = fault
        hv_on = bool(byte11 & 0x4)                # 1 = HV ON

        kv = self.vmax_kv * (v_code / 0x3FF)
        ma = self.imax_ma * (i_code / 0x3FF)

        return {
            "type": "R",
            "raw": s,
            "kv": kv,
            "ma": ma,
            "control_mode": "I" if control_mode_current else "V",
            "fault": fault,
            "hv_on": hv_on,
        }

    def get_version(self) -> dict:
        """
        Send V command; returns dict:
            {'type': 'B', 'raw': 'B..', 'version': '##'}
        or error dict.
        """
        resp = self._write_readline("V")

        if resp.startswith("E"):
            return self._parse_error(resp)

        if not resp.startswith("B"):
            return {"type": "UNKNOWN", "raw": resp}

        # B 2byte_revision 2byte_checksum <CR> :contentReference[oaicite:3]{index=3}
        s = resp.strip()
        version = s[1:3] if len(s) >= 3 else ""
        return {"type": "B", "raw": s, "version": version}

    # ----------------- SET command helpers -----------------------------

    def _scale_voltage(self, kv: float) -> int:
        kv = max(0.0, min(self.vmax_kv, kv))
        return int(round((kv / self.vmax_kv) * 0xFFF))

    def _scale_current(self, ma: float) -> int:
        ma = max(0.0, min(self.imax_ma, ma))
        return int(round((ma / self.imax_ma) * 0xFFF))

    def _build_set_core(
        self,
        kv: float | None,
        ma: float | None,
        hv_on: bool = False,
        hv_off: bool = False,
        reset: bool = False,
    ) -> str:
        """
        Build the ASCII body for 'S' command:
          S VVV III 000000 D

        where VVV/III are 3-digit hex, 000000 = reserved,
        D = 1 hex digit for digital controls (HV OFF/ON/RESET). :contentReference[oaicite:4]{index=4}
        """
        # Update stored setpoints if caller passed them
        if kv is not None:
            self.v_set_kv = kv
        if ma is not None:
            self.i_set_ma = ma

        v_code = self._scale_voltage(self.v_set_kv)
        i_code = self._scale_current(self.i_set_ma)

        # Digital control nibble :contentReference[oaicite:5]{index=5}
        # bit0 HV Off (Off=1)
        # bit1 HV On (On=1)
        # bit2 Reset (1=reset)
        bits = 0
        bits |= 0x1 if hv_off else 0
        bits |= 0x2 if hv_on else 0
        bits |= 0x4 if reset else 0

        # only one of HV ON / HV OFF / RESET allowed → let supply enforce
        d_hex = f"{bits:X}"  # one hex digit

        core = f"S{v_code:03X}{i_code:03X}000000{d_hex}"
        return core

    def send_set(
        self,
        kv: float | None = None,
        ma: float | None = None,
        hv_on: bool = False,
        hv_off: bool = False,
        reset: bool = False,
    ) -> dict:
        """
        General SET command.

        kv / ma: new setpoints in engineering units (kV, mA). If None,
                 uses last commanded values.
        hv_on, hv_off, reset: booleans for digital control pulse.

        Returns:
            {'type': 'A', 'raw': 'A'} on success (ACK),
            or error dict from E packet.
        """
        core = self._build_set_core(kv, ma, hv_on, hv_off, reset)
        resp = self._write_readline(core)

        if resp.startswith("E"):
            return self._parse_error(resp)

        if resp.startswith("A"):
            return {"type": "A", "raw": resp.strip()}

        return {"type": "UNKNOWN", "raw": resp}

    # Convenience wrappers
    def set_program(self, kv: float, ma: float) -> dict:
        return self.send_set(kv=kv, ma=ma)

    def hv_on_pulse(self) -> dict:
        return self.send_set(hv_on=True)

    # def hv_off_pulse(self) -> dict:
    #     return self.send_set(hv_off=True)

    def hv_off_pulse(self) -> dict:
        """
        WJ supplies IGNORE the HV OFF bit unless V=0 and I=0.
        So force both to zero when sending HV OFF.
        """
        self.v_set_kv = 0.0
        self.i_set_ma = 0.0
        return self.send_set(kv=0.0, ma=0.0, hv_off=True)
    def reset_pulse(self) -> dict:
        # Per manual, Reset forces V=0, I=0, HV Enable off :contentReference[oaicite:6]{index=6}
        self.v_set_kv = 0.0
        self.i_set_ma = 0.0
        return self.send_set(kv=0.0, ma=0.0, reset=True)

    # ------------------------------------------------------------------
    # Error parsing
    # ------------------------------------------------------------------
    def _parse_error(self, resp: str) -> dict:
        """
        Parse E packets: E <code> <cs1><cs2><CR>
        """
        s = resp.strip()
        code = None
        if len(s) >= 2:
            try:
                code = int(s[1])
            except ValueError:
                code = None
        msg = ERROR_MESSAGES.get(code, "Unknown error")
        return {"type": "E", "raw": s, "code": code, "message": msg}
