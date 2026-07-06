# instruments/arduino.py
# import serial
# import time


# class ArduinoController:
#     def __init__(self):
#         self.ser: serial.Serial | None = None

#     def connect(self, port: str, baudrate: int = 9600):
#         if self.ser and self.ser.is_open:
#             self.ser.close()

#         self.ser = serial.Serial(
#             port=port,
#             baudrate=baudrate,
#             timeout=1
#         )
#         time.sleep(1.0)
#         self.ser.reset_input_buffer()

#     def send(self, text: str):
#         if not self.ser or not self.ser.is_open:
#             raise RuntimeError("Arduino not connected")
#         self.ser.write((text + "\n").encode("ascii"))

#     def close(self):
#         if self.ser and self.ser.is_open:
#             self.ser.close()
#             self.ser = None
import serial
import threading
import time


class ArduinoController:
    """Portenta serial wrapper.

    Both the GUI thread (set_pressure_voltage / set_digital_output /
    glassman_send_portenta) and the PressureStreamWorker thread share
    this one serial handle. pyserial on Windows is not safe for
    concurrent read+write, so every send/readline goes through a
    single lock. The stream worker should use self.readline() (not
    self.serial.readline()) so its reads participate in the same lock.
    """

    def __init__(self):
        self.ser: serial.Serial | None = None
        self._lock = threading.Lock()

    # Alias for compatibility with stream worker
    @property
    def serial(self):
        return self.ser

    def connect(self, port: str, baudrate: int = 115200):
        with self._lock:
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.ser = serial.Serial(
                port=port,
                baudrate=baudrate,
                timeout=0.1,
                write_timeout=0.1
            )
        time.sleep(1.0)
        with self._lock:
            if self.ser and self.ser.is_open:
                self.ser.reset_input_buffer()

    def send(self, text: str):
        with self._lock:
            if not self.ser or not self.ser.is_open:
                raise RuntimeError("Arduino not connected")
            self.ser.write((text + "\n").encode("ascii"))

    def readline(self) -> str:
        """Thread-safe readline. Returns '' on disconnect/error."""
        with self._lock:
            if not self.ser or not self.ser.is_open:
                return ""
            try:
                return self.ser.readline().decode(errors="ignore").strip()
            except Exception:
                return ""

    def send_command(self, cmd: str) -> str:
        """
        Send a command to Arduino and read the response. Atomic under
        the lock so the response can't be stolen by the stream worker.
        """
        with self._lock:
            if not self.ser or not self.ser.is_open:
                raise RuntimeError("Arduino not connected")
            self.ser.write((cmd + "\n").encode("ascii"))
            response = self.ser.readline().decode(errors="ignore").strip()
            return response

    def close(self):
        with self._lock:
            if self.ser and self.ser.is_open:
                try:
                    self.ser.close()
                except Exception:
                    pass
            self.ser = None
    # Add this method to ArduinoController class in instruments/arduino.py

    def set_pressure_voltage(self, voltage: float) -> str:
        """
        Send voltage command to Arduino for pressure regulator control.
        Atomic under the lock — write+read in one critical section so
        the PressureStreamWorker can't steal the ACK.
        """
        voltage = max(0.0, min(10.0, voltage))
        cmd = f"VOLT {voltage:.3f}\n"
        with self._lock:
            if not self.ser or not self.ser.is_open:
                raise RuntimeError("Arduino not connected")
            self.ser.write(cmd.encode("ascii"))
            response = self.ser.readline().decode(errors="ignore").strip()
        return response
    def set_digital_output(self, channel: int, state: int) -> str:
        """
        Set a digital output channel ON or OFF.
        
        Args:
            channel: Digital output channel (0-7)
            state: 1 for ON, 0 for OFF
            
        Returns:
            Response from Arduino
        """
        if state:
            cmd = f"ON {channel}"
        else:
            cmd = f"OFF {channel}"
        return self.send_command(cmd)

