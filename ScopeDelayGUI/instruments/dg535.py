import time
import serial

class DG535Controller:
    def __init__(self, port="COM4"):
        self.port = port
        self.ser = None

    def connect(self, port=None, baudrate=9600, gpib_addr=15):
        if port:
            self.port = port

        self.ser = serial.Serial(self.port, baudrate, timeout=2)
        time.sleep(0.5)

        # Prologix setup
        self.write("++mode 1")
        self.write("++auto 0")
        self.write(f"++addr {gpib_addr}")
        self.write("++eoi 1")
        self.write("++eos 1")

    def write(self, cmd):
        if not self.ser:
            raise RuntimeError("DG535 serial not open")
        self.ser.write((cmd + "\r").encode())
        time.sleep(0.05)

    def send_gpib(self, cmd):
        self.write(cmd)

    # ==== Restore MATLAB-equivalent functions ====

    def configure_pulse_A(self, delay_a, width_a):
        self.send_gpib("C L")
        time.sleep(0.05)

        # A = T0 + delay
        self.send_gpib(f"D T 2 , 1 , {delay_a:.6E}")
        time.sleep(0.05)

        # B = A + width
        self.send_gpib(f"D T 3 , 2 , {delay_a + width_a:.6E}")
        time.sleep(0.05)

        # Output A settings
        self.send_gpib("T Z 2 , 0")
        self.send_gpib("O M 2 , 0")
        self.send_gpib("O P 2 , 1")
        time.sleep(0.1)

    def set_single_shot(self):
        self.send_gpib("T M 2")
        time.sleep(0.1)

    def fire(self):
        self.send_gpib("S S")
        time.sleep(0.05)

    def close(self):
        if self.ser:
            self.ser.close()
            self.ser = None
