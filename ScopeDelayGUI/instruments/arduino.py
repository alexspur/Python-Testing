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

    def connect(self, port: str, baudrate: int = 115200):
        if self.ser and self.ser.is_open:
            self.ser.close()

        self.ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=0.1,
            write_timeout=0.1
        )
        time.sleep(1.0)
        self.ser.reset_input_buffer()

    def send(self, text: str):
        if not self.ser or not self.ser.is_open:
            raise RuntimeError("Arduino not connected")
        self.ser.write((text + "\n").encode("ascii"))

    def send_command(self, cmd: str) -> str:
        """
        Send a command to Arduino and read the response.

        Args:
            cmd: Command string to send

        Returns:
            Response from Arduino
        """
        if not self.ser or not self.ser.is_open:
            raise RuntimeError("Arduino not connected")
        self.ser.write((cmd + "\n").encode("ascii"))
        response = self.ser.readline().decode(errors="ignore").strip()
        return response

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            self.ser = None
    # Add this method to ArduinoController class in instruments/arduino.py

    def set_pressure_voltage(self, voltage: float) -> str:
        """
        Send voltage command to Arduino for pressure regulator control.
        
        Args:
            voltage: Output voltage (0-10V)
            
        Returns:
            Response from Arduino
        """
        if not self.ser or not self.ser.is_open:
            raise RuntimeError("Arduino not connected")
        
        voltage = max(0.0, min(10.0, voltage))
        cmd = f"VOLT {voltage:.3f}\n"
        self.ser.write(cmd.encode("ascii"))
        
        # Read response
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

