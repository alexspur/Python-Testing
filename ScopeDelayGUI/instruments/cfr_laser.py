"""
Quantel CFR laser controller (RS-232 over USB).

Framework-agnostic, thread-safe serial wrapper used by gui/laser_panel.py.
The serial / command logic is the same proven set used by the standalone
gui/cfr_laser_gui.py, factored out so the PyQt main window can drive a minimal
laser panel.

Serial config per manual: 9600 8N1, no flow control, only Tx and Rx used.
Minimum inter-command delay is ~150 ms. Commands terminate with CR LF.
"""

import threading
import time

import serial


# ---------- Interlock bit definitions, straight from the manual ----------
IF1_BITS = [
    ("a", "E-STOP button pressed"),
    ("b", "BNC remote interlock OPEN"),
    ("c", "Laser head thermostat OPEN"),
    ("d", "Laser head housing switch OPEN"),
    ("e", "ICE450 housing switch OPEN"),
    ("f", "Internal bus error"),
    ("g", "External bus error"),
    ("h", "Flashlamp timeout"),
]

IF2_BITS = [
    ("a", "Heater thermostat OPEN"),
    ("b", "Charger temperature OVER max"),
    ("c", "Coolant temperature UNDER min"),
    ("d", "Coolant temperature OVER max"),
    ("e", "Coolant level LOW"),
    ("f", "Coolant flow LOW"),
    ("g", "Charger / coolant / SHG temp BELOW min"),
    ("h", "Flashlamp power setting too HIGH"),
]

IF3_BITS = [
    ("a", "PSU charge error (no end of charge before fire)"),
    ("b", "Voltage over setting"),
    ("c", "No simmer sensed"),
    ("d", "External flash signal frequency too LOW"),
    ("e", "External flash signal frequency too HIGH"),
    ("f", "Capacitor discharge problem"),
    ("g", "Simmer timeout"),
    ("h", "PIV master/slave interlock mismatch"),
]

IQ_BITS = [
    ("a", "8-second forced delay after flashlamp start"),
    ("b", "Coolant temperature too LOW"),
    ("c", "Q-Switch timeout"),
    ("d", "Shutter is CLOSED"),
    ("e", "(unused)"),
    ("f", "(unused)"),
    ("g", "(unused)"),
    ("h", "(unused)"),
]


def parse_interlock_response(resp, bit_defs, prefix):
    """
    Parse a response like 'IF1 00 01 00 00' into a list of active fault names.
    The 8 bits map to a-h in order. Spaces between byte pairs are ignored.
    Returns list of human-readable fault strings (empty list = no faults).
    """
    if not resp:
        return ["(no response)"]

    cleaned = resp.replace(prefix, "").replace(" ", "").strip()
    bits = "".join(c for c in cleaned if c in "01")

    if len(bits) < 8:
        return [f"(malformed response: {resp!r})"]

    bits = bits[:8]
    faults = []
    for i, (label, desc) in enumerate(bit_defs):
        if bits[i] == "1":
            faults.append(f"{label}: {desc}")
    return faults


class CFRLaserController:
    """Minimal thread-safe RS-232 controller for the Quantel CFR laser."""

    def __init__(self):
        self.ser = None
        self.lock = threading.Lock()  # serialize access across worker threads

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    def connect(self, port, baudrate=9600):
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1.0,
            write_timeout=1.0,
        )

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.ser = None

    @property
    def is_open(self):
        return bool(self.ser and self.ser.is_open)

    # ------------------------------------------------------------------
    # Low-level I/O
    # ------------------------------------------------------------------
    def _send_raw(self, cmd, read_timeout=0.5):
        if not self.is_open:
            return None
        try:
            self.ser.reset_input_buffer()
            self.ser.write((cmd + "\r\n").encode("ascii"))
            self.ser.flush()

            old_timeout = self.ser.timeout
            self.ser.timeout = read_timeout
            resp_bytes = self.ser.read_until(b"\r\n", size=128)
            time.sleep(0.05)
            extra = self.ser.read(self.ser.in_waiting or 0)
            self.ser.timeout = old_timeout

            return (resp_bytes + extra).decode("ascii", errors="ignore").strip()
        except Exception as e:
            return f"__ERROR__ {e}"

    def send_cmd(self, cmd, read_timeout=0.5):
        """Send one command (CR/LF added), return the response string.

        Thread-safe: holds the lock for the exchange plus the manual-mandated
        ~150 ms inter-command settle so back-to-back calls don't run together.
        """
        with self.lock:
            resp = self._send_raw(cmd, read_timeout=read_timeout)
            time.sleep(0.16)
        return resp

    # ------------------------------------------------------------------
    # Interlocks
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_wor_field(wor, letter):
        if not wor:
            return None
        tokens = wor.replace(":", " ").split()
        for i, tok in enumerate(tokens):
            if tok == letter and i + 1 < len(tokens):
                next_tok = tokens[i + 1]
                if next_tok and next_tok[0].isdigit():
                    return next_tok[0]
        return None

    def check_interlocks(self):
        """Query WOR then IF1/IF2/IF3/IQ. Returns (clear: bool, summary, color)."""
        if not self.is_open:
            return (False, "Not connected", "red")

        wor = self.send_cmd("WOR")
        if not wor:
            return (False, "WOR query failed", "red")

        i_present = self._extract_wor_field(wor, "I")
        if i_present is None:
            return (False, f"Could not parse WOR: {wor!r}", "red")

        if i_present == "0":
            return (True, f"WOR: {wor}\nNo interlocks present.", "darkgreen")

        all_faults = []
        for cmd, prefix, bits in [
            ("IF1", "IF1", IF1_BITS),
            ("IF2", "IF2", IF2_BITS),
            ("IF3", "IF3", IF3_BITS),
            ("IQ", "IQS", IQ_BITS),
        ]:
            resp = self.send_cmd(cmd)
            if not resp:
                all_faults.append(f"{cmd}: query failed")
                continue
            for f in parse_interlock_response(resp, bits, prefix):
                all_faults.append(f"{cmd}.{f}")

        if all_faults:
            return (False, "INTERLOCKS PRESENT:\n  " + "\n  ".join(all_faults), "red")
        return (False, "WOR says interlocks present but no specific bits set.", "orange")
