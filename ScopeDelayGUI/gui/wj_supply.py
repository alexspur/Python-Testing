# wj_supply.py
import serial
import time

SOH = b'\x01'
CR  = b'\x0D'

class WJPowerSupply:
    def __init__(self, port, baud=9600, timeout=0.3):
        self.ser = serial.Serial(port, baudrate=baud, timeout=timeout)

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()

    def _send(self, packet):
        self.ser.write(packet)
        return self.ser.read_until(CR)

    def _make_packet(self, cmd, data_hex="000"):
        """
        Format:
        SOH + CMD (1 char) + 3 HEX chars + checksum + CR
        """
        body = cmd + data_hex
        checksum = sum(body.encode()) & 0xFF
        packet = SOH + body.encode() + ("%02X" % checksum).encode() + CR
        return packet

    # ----------------------------
    # HIGH-VOLTAGE CONTROL
    # ----------------------------

    def set_voltage(self, kv, max_kv):
        # Convert kV to 12-bit hex (0–FFF) based on manual scaling (page 39)
        v_hex = int((kv / max_kv) * 4095)
        return self._send(self._make_packet("V", f"{v_hex:03X}"))

    def set_current(self, mA, max_mA):
        i_hex = int((mA / max_mA) * 4095)
        return self._send(self._make_packet("C", f"{i_hex:03X}"))

    def hv_on(self):
        return self._send(self._make_packet("S", "001"))

    def hv_off(self):
        return self._send(self._make_packet("S", "000"))

    def reset(self):
        return self._send(self._make_packet("R", "000"))

    # ----------------------------
    # MONITOR BLOCK
    # ----------------------------
    def query(self):
        """
        Sends a Q packet once per second (required)
        Manual page 38: timeout is 1.5s, must send < 1.5s
        """
        resp = self._send(self._make_packet("Q", "000"))
        return resp.decode(errors="ignore")
