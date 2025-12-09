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
import time


class ArduinoController:
    def __init__(self):
        self.ser: serial.Serial | None = None

    # Alias for compatibility with stream worker
    @property
    def serial(self):
        return self.ser

    def connect(self, port: str, baudrate: int = 9600):
        if self.ser and self.ser.is_open:
            self.ser.close()

        self.ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=0.1
        )
        time.sleep(1.0)
        self.ser.reset_input_buffer()

    def send(self, text: str):
        if not self.ser or not self.ser.is_open:
            raise RuntimeError("Arduino not connected")
        self.ser.write((text + "\n").encode("ascii"))

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            self.ser = None
