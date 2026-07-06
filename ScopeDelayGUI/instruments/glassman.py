# instruments/glassman.py
#
# Lightweight pyserial wrapper for the Glassman Mega (V/I monitor +
# HV ENABLE relay). Mirrors the GlassmanSerial helper used by the
# standalone glassman_test_gui.py. The Portenta side is NOT here —
# that hardware is the same Portenta as the SF6 panel, so commands
# ride on the existing ArduinoController (self.arduino).

import time
import threading
import serial


class GlassmanSerial:
    """Thin pyserial wrapper for the Arduino Mega (Glassman monitor).

    send() runs on the GUI thread (from HV ON / HV OFF / Apply Program);
    readline() runs on the Mega reader QThread. pyserial on Windows is
    not reliably safe for concurrent read+write on the same handle, so
    we serialize both behind a single lock.
    """

    def __init__(self):
        self.ser: serial.Serial | None = None
        self._lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        return self.ser is not None and self.ser.is_open

    def connect(self, port: str, baud: int = 115200):
        self.close()
        self.ser = serial.Serial(port, baud, timeout=0.1, write_timeout=0.1)
        time.sleep(2.0)  # wait for Arduino reset
        with self._lock:
            self.ser.reset_input_buffer()

    def close(self):
        with self._lock:
            if self.ser is not None and self.ser.is_open:
                try:
                    self.ser.close()
                except Exception:
                    pass
            self.ser = None

    def send(self, cmd: str):
        with self._lock:
            if self.ser is None or not self.ser.is_open:
                raise RuntimeError("Not connected")
            self.ser.write((cmd + "\n").encode("ascii"))

    def readline(self) -> str:
        with self._lock:
            if self.ser is None or not self.ser.is_open:
                return ""
            try:
                return self.ser.readline().decode(errors="ignore").strip()
            except Exception:
                return ""
