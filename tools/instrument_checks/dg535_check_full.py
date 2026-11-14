import time
import serial

class DG535:
    def __init__(self, port="COM4", gpib=15):
        self.port = port
        self.addr = gpib
        self.ser = None

    def open(self):
        print(f"Opening Prologix on {self.port}...")
        self.ser = serial.Serial(self.port, 9600, timeout=2)
        time.sleep(0.4)

        self.send("++mode 1")
        self.send("++auto 0")
        self.send("++eoi 1")
        self.send("++eos 1")
        self.send(f"++addr {self.addr}")
        print("Prologix initialized.\n")

    def send(self, cmd):
        print(f"→ {cmd}")
        self.ser.write((cmd + "\r").encode())
        time.sleep(0.05)

    def query(self, cmd):
        self.send(cmd)
        self.send("++read eoi")
        time.sleep(0.1)
        ans = self.ser.read(200).decode(errors='ignore')
        return ans.strip()

    def close(self):
        if self.ser:
            print("Closing COM port...")
            self.ser.close()


def main():
    dg = DG535()
    dg.open()

    print("\n******** DG535 FULL TEST ********\n")

    # ================================
    #  IDENTIFICATION
    # ================================
    print("=== ID TEST ===")
    idn = dg.query("ID?")
    print("IDN →", idn, "\n")

    # ================================
    #  READ CURRENT MODE
    # ================================
    print("=== MODE TEST ===")
    mode = dg.query("T M?")
    print("Mode →", mode, "\n")

    # ================================
    #  READ TIMING OF CHANNEL A
    # ================================
    print("=== TIMING TEST (T0, A, B) ===")
    print("T0  →", dg.query("D T 1?"))
    print("A   →", dg.query("D T 2?"))
    print("B   →", dg.query("D T 3?"))
    print()

    # ================================
    #  TRIGGER LEVEL & MODE
    # ================================
    print("=== TRIGGER TEST ===")
    print("Trigger Mode →", dg.query("T T?"))
    print("Trigger Src  →", dg.query("T S?"))
    print("Trigger Rate →", dg.query("T R?"))
    print()

    # ================================
    #  PULSE TEST
    # ================================
    print("=== PROGRAM + FIRE TEST ===")
    dg.send("C L")   # local mode
    dg.send("D T 2 , 1 , 1E-6")
    dg.send("D T 3 , 2 , 2E-6")
    dg.send("T M 2")  # single shot
    dg.send("S S")    # fire
    print("→ Fired 1 µs pulse.\n")

    dg.close()
    print("\nDone.\n")


if __name__ == "__main__":
    main()
