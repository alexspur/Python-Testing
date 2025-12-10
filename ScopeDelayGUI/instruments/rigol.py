import pyvisa
import numpy as np
import time


class RigolScope:
    """
    Waveform capture helper for Rigol DS7000/MSO7000 series.
    Uses binary block reads (WAV:FORM BYTE) and provides
    arm()/wait_and_capture() helpers for the GUI.
    """

    def __init__(self, resource_str: str):
        self.resource_str = resource_str
        self.rm = None
        self.inst = None

    # ---------------------------------------------------------
    # Connect
    # ---------------------------------------------------------
    def connect(self):
        self.rm = pyvisa.ResourceManager()
        self.inst = self.rm.open_resource(self.resource_str)

        self.inst.timeout = 15000
        self.inst.chunk_size = 2_000_000  # 2 MB for long memory

        self.inst.write("*CLS")
        time.sleep(0.1)

    def identify(self) -> str:
        return self.inst.query("*IDN?").strip()

    # ---------------------------------------------------------
    # Arm + wait helpers (for GUI capture button)
    # ---------------------------------------------------------
    def arm(self):
        """
        Put scope into SINGLE mode and wait for trigger.
        """
        self.inst.write(":STOP")
        time.sleep(0.05)
        self.inst.write(":SINGLE")
        time.sleep(0.1)

    # ---------------------------------------------------------
    # Capture two channels (ORIGINAL WORKING CODE)
    # ---------------------------------------------------------
    def capture_two_channels(self, ch1="CHAN1", ch2="CHAN2"):
        """
        Correct method for DS7000 dual-channel capture.
        Must use RAW mode and set WAV:SOUR only AFTER acquisition.
        """

        # ------------------------------
        # Read CH1
        # ------------------------------
        self.inst.write(":WAV:MODE RAW")
        self.inst.write(":WAV:FORM BYTE")
        self.inst.write(f":WAV:SOUR {ch1}")
        pre1 = self.inst.query(":WAV:PRE?").split(',')
        yinc1 = float(pre1[7])
        yorig1 = float(pre1[8])
        yref1 = float(pre1[9])
        xinc1 = float(pre1[4])
        xorig1 = float(pre1[5])

        yraw1 = self.inst.query_binary_values(":WAV:DATA?", datatype='B')
        v1 = (np.array(yraw1) - yorig1 - yref1) * yinc1
        t1 = xorig1 + np.arange(len(v1)) * xinc1

        # ------------------------------
        # Read CH2
        # ------------------------------
        self.inst.write(f":WAV:SOUR {ch2}")
        pre2 = self.inst.query(":WAV:PRE?").split(',')
        yinc2 = float(pre2[7])
        yorig2 = float(pre2[8])
        yref2 = float(pre2[9])
        xinc2 = float(pre2[4])
        xorig2 = float(pre2[5])

        yraw2 = self.inst.query_binary_values(":WAV:DATA?", datatype='B')
        v2 = (np.array(yraw2) - yorig2 - yref2) * yinc2
        t2 = xorig2 + np.arange(len(v2)) * xinc2

        return (t1, v1), (t2, v2)

    # ---------------------------------------------------------
    # Wait and capture
    # ---------------------------------------------------------
    def wait_and_capture(self, ch1="CHAN1", ch2="CHAN2", timeout=30.0):
        """
        Wait for trigger and capture two channels.

        Args:
            ch1: First channel to capture (default CHAN1)
            ch2: Second channel to capture (default CHAN2)
            timeout: Timeout in seconds (default 30.0)

        Returns:
            Tuple of ((t1,v1), (t2,v2)) or None on timeout.
        """
        start = time.time()

        # Wait for acquisition to finish
        while (time.time() - start) < timeout:
            try:
                st = self.inst.query(":TRIGger:STATus?").strip().upper()
            except:
                time.sleep(0.05)
                continue

            if st == "STOP":
                break

            time.sleep(0.02)
        else:
            return None

        time.sleep(0.05)
        return self.capture_two_channels(ch1, ch2)

    # ---------------------------------------------------------
    # Export to CSV
    # ---------------------------------------------------------
    def export_csv(self, filename_prefix="rigol"):
        """
        Captures CH1 and CH2 and exports them to CSV.
        Output format:
            time(s), ch1(V), ch2(V)
        """
        import csv
        from datetime import datetime

        # Capture
        (t1, v1), (t2, v2) = self.capture_two_channels()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename_prefix}_{timestamp}.csv"

        # Save combined 3-column CSV
        rows = zip(t1, v1, v2)

        with open(filename, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["time_s", "ch1_v", "ch2_v"])
            writer.writerows(rows)

        return filename

    # ---------------------------------------------------------
    # Cleanup
    # ---------------------------------------------------------
    def close(self):
        if self.inst:
            self.inst.close()
            self.inst = None
        if self.rm:
            self.rm.close()
            self.rm = None
