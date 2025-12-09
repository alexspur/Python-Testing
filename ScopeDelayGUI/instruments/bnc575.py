# import serial
# import time

# class BNC575Controller:
#     def __init__(self):
#         self.ser: serial.Serial | None = None

#     def connect(self, port: str, baudrate: int = 115200):
#         if self.ser and self.ser.is_open:
#             self.ser.close()

#         self.ser = serial.Serial(
#             port=port,
#             baudrate=baudrate,
#             timeout=2
#         )
#         time.sleep(1.0)

#         self.ser.reset_input_buffer()
#         self.write(":ABOR")
#         time.sleep(0.1)
#         self.write("*RST")
#         time.sleep(1.0)

#         # Ensure master timing engine is in a sane state
#         self.write(":PULSE0:MODE SING")
#         self.write(":PULSE0:TRIG:MODE DIS")

#     def write(self, cmd: str):
#         if not self.ser or not self.ser.is_open:
#             raise RuntimeError("BNC575 serial not open")
#         self.ser.write((cmd + "\n").encode("ascii"))

#     def query(self, cmd: str) -> str:
#         self.write(cmd)
#         return self.ser.readline().decode("ascii", errors="ignore").strip()

#     def identify(self):
#         return self.query("*IDN?")

#     # -------------------------------------------------------------
#     #  APPLY settings for CH A–D (PULSE1–PULSE4)
#     # -------------------------------------------------------------
#     def apply_settings(self, wA, dA, wB, dB, wC, dC, wD, dD):

#         # --- Required: force all channels into PULSE mode ---
#         self.write(":PULSE1:MODE PULSE")
#         self.write(":PULSE2:MODE PULSE")
#         self.write(":PULSE3:MODE PULSE")
#         self.write(":PULSE4:MODE PULSE")
#         time.sleep(0.05)

#         # --- Required: master timing engine FIRST ---
#         self.write(":PULSE0:MODE SING")
#         self.write(":PULSE0:TRIG:MODE DIS")
#         time.sleep(0.05)

#         # ---------- CHANNEL A (PULSE1) ----------
#         self.write(":PULSE1:STATE ON")
#         self.write(":PULSE1:POL NORM")
#         self.write(f":PULSE1:WIDT {wA:.6E}")
#         self.write(f":PULSE1:DEL  {dA:.6E}")
#         time.sleep(0.02)

#         # ---------- CHANNEL B (PULSE2) ----------
#         self.write(":PULSE2:STATE ON")
#         self.write(":PULSE2:POL NORM")
#         self.write(f":PULSE2:WIDT {wB:.6E}")
#         self.write(f":PULSE2:DEL  {dB:.6E}")
#         time.sleep(0.02)

#         # ---------- CHANNEL C (PULSE3) ----------
#         self.write(":PULSE3:STATE ON")
#         self.write(":PULSE3:POL NORM")
#         self.write(f":PULSE3:WIDT {wC:.6E}")
#         self.write(f":PULSE3:DEL  {dC:.6E}")
#         time.sleep(0.02)

#         # ---------- CHANNEL D (PULSE4) ----------
#         self.write(":PULSE4:STATE ON")
#         self.write(":PULSE4:POL NORM")
#         self.write(f":PULSE4:WIDT {wD:.6E}")
#         self.write(f":PULSE4:DEL  {dD:.6E}")
#         time.sleep(0.02)

#     # -------------------------------------------------------------
#     #  READBACK settings for CH A–D
#     # -------------------------------------------------------------
#     def read_settings(self):

#         def f(x):
#             try:
#                 return float(x)
#             except:
#                 return float("nan")

#         # Stop timing engine (required before reading)
#         self.write(":ABOR")
#         time.sleep(0.05)

#         # Ensure channels are in PULSE mode (manual requirement)
#         self.write(":PULSE1:MODE PULSE")
#         self.write(":PULSE2:MODE PULSE")
#         self.write(":PULSE3:MODE PULSE")
#         self.write(":PULSE4:MODE PULSE")
#         time.sleep(0.05)

#         # Ensure outputs are ON (otherwise queries return blanks)
#         self.write(":PULSE1:STATE ON")
#         self.write(":PULSE2:STATE ON")
#         self.write(":PULSE3:STATE ON")
#         self.write(":PULSE4:STATE ON")
#         time.sleep(0.05)

#         # Now safe to query
#         wA = f(self.query(":PULSE1:WIDT?"))
#         dA = f(self.query(":PULSE1:DEL?"))
#         wB = f(self.query(":PULSE2:WIDT?"))
#         dB = f(self.query(":PULSE2:DEL?"))
#         wC = f(self.query(":PULSE3:WIDT?"))
#         dC = f(self.query(":PULSE3:DEL?"))
#         wD = f(self.query(":PULSE4:WIDT?"))
#         dD = f(self.query(":PULSE4:DEL?"))

#         # Guarantee 8 outputs
#         return (
#             wA if wA is not None else float("nan"),
#             dA if dA is not None else float("nan"),
#             wB if wB is not None else float("nan"),
#             dB if dB is not None else float("nan"),
#             wC if wC is not None else float("nan"),
#             dC if dC is not None else float("nan"),
#             wD if wD is not None else float("nan"),
#             dD if dD is not None else float("nan")
#         )


#     # External trigger arm
#     def arm_external_trigger(self, level: float = 1.0):
#         self.write(":PULSE0:TRIG:MODE EXT")
#         self.write(":PULSE0:TRIG:SLOP POS")
#         self.write(f":PULSE0:TRIG:LEV {level:.3f}")
#         self.write(":PULSE0:MODE SING")
#         self.write(":RUN")

#     def fire_internal(self):
#         self.write(":PULSE0:STAT ON")
#         time.sleep(0.2)
#         self.write(":PULSE0:STAT OFF")

#     def close(self):
#         if self.ser and self.ser.is_open:
#             self.ser.close()
#             self.ser = None
import serial
import time

class BNC575Controller:
    def __init__(self):
        self.ser: serial.Serial | None = None

    # -------------------------------------------------------------------------
    # CONNECT
    # -------------------------------------------------------------------------
    def connect(self, port: str, baudrate: int = 115200):
        if self.ser and self.ser.is_open:
            self.ser.close()

        self.ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=2
        )
        time.sleep(1.0)

        self.ser.reset_input_buffer()

        # Full reset on connect
        self.write("*RST")
        time.sleep(0.5)

        # Disable trigger during setup
        self.write(":PULSE0:TRIG:MODE DIS")
        self.write(":ABOR")   # abort timing engine
        time.sleep(0.1)

        # Apply your desired default configuration
        self.configure_default_pulses()

    # -------------------------------------------------------------------------
    # LOW-LEVEL SEND ROUTINES
    # -------------------------------------------------------------------------
    def write(self, cmd: str):
        if not self.ser or not self.ser.is_open:
            raise RuntimeError("BNC575 serial not open")
        self.ser.write((cmd + "\n").encode("ascii"))

    def query(self, cmd: str) -> str:
        self.write(cmd)
        return self.ser.readline().decode("ascii", errors="ignore").strip()

    # -------------------------------------------------------------------------
    # IDENTIFY
    # -------------------------------------------------------------------------
    def identify(self):
        return self.query("*IDN?")

    # -------------------------------------------------------------------------
    # DEFAULT PULSE CONFIGURATION
    # -------------------------------------------------------------------------
    def configure_default_pulses(self):
        """
        Configures:
          Channel A: 1us width, 0 delay
          Channel B: 1us width, 0 delay
          Channel C: 40us width, 0 delay
          Channel D: 40us width, 0 delay

          Trigger: external, rising-edge, 3.0V threshold
        """

        # ---------------------------------------------------------------------
        # Stop timing engine
        # ---------------------------------------------------------------------
        self.write(":ABOR")
        time.sleep(0.1)

        # ---------------------------------------------------------------------
        # Set channels A–D to NORMAL mode, ON, normal polarity, sync'd to T0
        # ---------------------------------------------------------------------
        for ch in (1, 2, 3, 4):
            self.write(f":PULSE{ch}:MODE NORM")
            self.write(f":PULSE{ch}:STATE ON")
            self.write(f":PULSE{ch}:POL NORM")
            self.write(f":PULSE{ch}:SYNC T0")

        time.sleep(0.05)

        # ---------------------------------------------------------------------
        # Apply widths & delays
        # ---------------------------------------------------------------------
        # A = 1 µs
        self.write(":PULSE1:WIDT 1E-6")
        self.write(":PULSE1:DEL 0")

        # B = 1 µs
        self.write(":PULSE2:WIDT 1E-6")
        self.write(":PULSE2:DEL 0")

        # C = 40 µs
        self.write(":PULSE3:WIDT 40E-6")
        self.write(":PULSE3:DEL 0")

        # D = 40 µs
        self.write(":PULSE4:WIDT 40E-6")
        self.write(":PULSE4:DEL 0")

        time.sleep(0.05)

        # ---------------------------------------------------------------------
        # Configure external trigger
        # ---------------------------------------------------------------------
        self.write(":PULSE0:TRIG:MODE TRIG")     # enable external trigger mode
        self.write(":PULSE0:TRIG:EDGE RIS")      # rising edge
        self.write(":PULSE0:TRIG:LEV 3.0")       # threshold = 3.0 V
        self.write(":PULSE0:MODE SING")          # one pulse per trigger

        time.sleep(0.05)

        # ---------------------------------------------------------------------
        # ARM system (wait for external trigger)
        # ---------------------------------------------------------------------
        self.write(":PULSE0:STATE ON")           # equivalent to RUN/STOP (ARM)
        time.sleep(0.05)

    # -------------------------------------------------------------------------
    # APPLY MANUAL CUSTOM SETTINGS (if GUI passes values)
    # -------------------------------------------------------------------------
    def apply_settings(self, wA, dA, wB, dB, wC, dC, wD, dD):
        """
        GUI version of setting widths/delays manually.
        """

        self.write(":ABOR")
        time.sleep(0.05)

        # Put channels in NORMAL mode
        for ch in (1, 2, 3, 4):
            self.write(f":PULSE{ch}:MODE NORM")
            self.write(f":PULSE{ch}:STATE ON")
            self.write(f":PULSE{ch}:POL NORM")
            self.write(f":PULSE{ch}:SYNC T0")

        time.sleep(0.05)

        # Channel A
        self.write(f":PULSE1:WIDT {wA:.6E}")
        self.write(f":PULSE1:DEL  {dA:.6E}")

        # Channel B
        self.write(f":PULSE2:WIDT {wB:.6E}")
        self.write(f":PULSE2:DEL  {dB:.6E}")

        # Channel C
        self.write(f":PULSE3:WIDT {wC:.6E}")
        self.write(f":PULSE3:DEL  {dC:.6E}")

        # Channel D
        self.write(f":PULSE4:WIDT {wD:.6E}")
        self.write(f":PULSE4:DEL  {dD:.6E}")

        time.sleep(0.05)

    # -------------------------------------------------------------------------
    # READBACK (not reliable on 575 firmware but included anyway)
    # -------------------------------------------------------------------------
    def read_settings(self):
        def f(x):
            try:
                return float(x)
            except:
                return float("nan")

        self.write(":ABOR")
        time.sleep(0.05)

        # Force channels ON before reading
        for ch in (1, 2, 3, 4):
            self.write(f":PULSE{ch}:STATE ON")

        time.sleep(0.05)

        wA = f(self.query(":PULSE1:WIDT?"))
        dA = f(self.query(":PULSE1:DEL?"))
        wB = f(self.query(":PULSE2:WIDT?"))
        dB = f(self.query(":PULSE2:DEL?"))
        wC = f(self.query(":PULSE3:WIDT?"))
        dC = f(self.query(":PULSE3:DEL?"))
        wD = f(self.query(":PULSE4:WIDT?"))
        dD = f(self.query(":PULSE4:DEL?"))

        return (wA, dA, wB, dB, wC, dC, wD, dD)

    # -------------------------------------------------------------------------
    # EXTERNAL TRIGGER ARM (alternative)
    # -------------------------------------------------------------------------
    def arm_external_trigger(self, level: float = 3.0):
        self.write(":PULSE0:TRIG:MODE TRIG")
        self.write(":PULSE0:TRIG:EDGE RIS")
        self.write(f":PULSE0:TRIG:LEV {level:.3f}")
        self.write(":PULSE0:MODE SING")
        self.write(":PULSE0:STATE ON")  # arm

    # -------------------------------------------------------------------------
    # INTERNAL FIRE (software trigger)
    # -------------------------------------------------------------------------
    def fire_internal(self):
        self.write("*TRG")

    # -------------------------------------------------------------------------
    # CLOSE PORT
    # -------------------------------------------------------------------------
    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            self.ser = None
