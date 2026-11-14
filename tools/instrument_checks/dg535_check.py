import time
import serial

class DG535Test:
    def __init__(self, port="COM4", addr=15):
        self.port = port
        self.addr = addr
        self.ser = None

    def open(self):
        print(f"\nOpening Prologix on {self.port}...")
        self.ser = serial.Serial(self.port, baudrate=9600, timeout=1)
        time.sleep(0.5)

        def send(cmd):
            print(f"→ {cmd}")
            self.ser.write((cmd + '\r').encode())
            time.sleep(0.05)

        # -------------------------
        # Prologix initialization
        # -------------------------
        send("++mode 1")     # CONTROLLER MODE
        send("++auto 0")     # NO AUTO READ
        send(f"++addr {self.addr}")
        send("++eoi 1")
        send("++eos 1")

        print("Prologix initialized.\n")

    def gpib(self, cmd):
        """Send GPIB command and show what was sent."""
        if not self.ser:
            raise RuntimeError("Serial not open")
        print(f"GPIB → {cmd}")
        self.ser.write((cmd + '\r').encode())
        time.sleep(0.05)

    def query(self, cmd):
        """Query DG535 and print the result."""
        print(f"GPIB ? {cmd}")
        self.ser.write((cmd + '\r').encode())
        time.sleep(0.05)

        # tell prologix to read
        self.ser.write(b"++read eoi\r")
        time.sleep(0.1)

        ans = self.ser.read(200).decode(errors='ignore').strip()
        print(f"← {ans}")
        return ans

    # -------------------------------
    # SIMPLE TESTS
    # -------------------------------
    def test_idn(self):
        print("\n=== IDENTIFICATION TEST ===")
        return self.query("ID?")  # DG535 responds to “ID?”

    def test_timing(self):
        print("\n=== PULSE A SETUP TEST ===")

        # Unlock
        self.gpib("C L")

        # Delay A = 100 ns
        self.gpib("D T 2 , 1 , 1.00E-7")
        # Width A = 20 ns
        self.gpib("D T 3 , 2 , 1.20E-7")

        # Route output A
        self.gpib("T Z 2 , 0")  # High impedance off
        self.gpib("O M 2 , 0")  # Normal mode
        self.gpib("O P 2 , 1")  # Positive polarity

        print("Pulse A configured.\n")

    def test_single(self):
        print("\n=== SINGLE SHOT FIRE TEST ===")
        self.gpib("T M 2")  # single shot mode
        time.sleep(0.1)
        self.gpib("S S")    # FIRE
        print("DG535 should have fired a pulse.\n")

    def close(self):
        if self.ser:
            print("Closing COM port...")
            self.ser.close()


# -------------- MAIN --------------
if __name__ == "__main__":
    dg = DG535Test(port="COM4", addr=15)

    dg.open()

    print("\n\n******** RUNNING DG535 TEST ********")
    time.sleep(0.5)

    dg.test_idn()
    time.sleep(0.5)

    dg.test_timing()
    time.sleep(0.5)

    dg.test_single()
    time.sleep(0.5)

    dg.close()
    print("\nDone.\n")
