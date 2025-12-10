# import pyvisa
# import numpy as np
# import time


# class RigolScope:
#     """
#     Waveform capture helper for Rigol DS7000/MSO7000 series.
#     Uses binary block reads (WAV:FORM BYTE) and provides
#     arm()/wait_and_capture() helpers for the GUI.
#     """

#     def __init__(self, resource_str: str):
#         self.resource_str = resource_str
#         self.rm = None
#         self.inst = None

#     # ---------------------------------------------------------
#     # Connect
#     # ---------------------------------------------------------
#     def connect(self):  
#         self.rm = pyvisa.ResourceManager()
#         self.inst = self.rm.open_resource(self.resource_str)

#         self.inst.timeout = 15000
#         self.inst.chunk_size = 2_000_000  # 2 MB for long memory

#         self.inst.write("*CLS")
#         time.sleep(0.1)

#     def identify(self) -> str:
#         return self.inst.query("*IDN?").strip()

#     # ----------------------------------------------- ----------
#     # Prepare waveform for a single channel
#     # ---------------------------------------------------------
#     # def _setup_waveform(self, ch: str):
#     #     """
#     #     SETUP USED IN INDUSTRY SCRIPTS FOR DS7000.
#     #     """
#     #     # Stop acquisition so we can safely configure waveform readout
#     #     self.inst.write(":STOP")
#     #     time.sleep(0.05)

#     #     # Ensure channel is ON
#     #     self.inst.write(f":{ch}:DISP ON")
#     #     time.sleep(0.02)

#     #     # Set waveform extraction settings
#     #     self.inst.write(":WAV:MODE NORM")
#     #     self.inst.write(":WAV:FORM BYTE")
#     #     self.inst.write(f":WAV:SOUR {ch}")
#     #     time.sleep(0.05)

#     #     # Ask for full memory depth
#     #     self.inst.write(":WAV:STAR 1")
#     #     mdep = int(float(self.inst.query(":ACQ:MDEP?")))
#     #     self.inst.write(f":WAV:STOP {mdep}")

#     #     # Read preamble
#     #     pre = self.inst.query(":WAV:PRE?").split(',')
#     #     # fmt = int(pre[0])        # not used but kept for reference
#     #     npts = int(pre[2])
#     #     xinc = float(pre[4])
#     #     xorig = float(pre[5])
#     #     yinc = float(pre[7])
#     #     yorig = float(pre[8])
#     #     yref = float(pre[9])

#     #     return npts, xinc, xorig, yinc, yorig, yref
#     def _setup_waveform(self, ch: str):
#         """
#         Prepare waveform extraction for channel `ch`.
#         IMPORTANT: DO NOT STOP THE SCOPE HERE.
#         Stopping should only happen in wait_and_capture().
#         """

#         # Ensure channel is ON
#         self.inst.write(f":{ch}:DISP ON")
#         time.sleep(0.02)

#         # Set waveform extraction settings
#         self.inst.write(":WAV:MODE NORM")
#         self.inst.write(":WAV:FORM BYTE")
#         self.inst.write(f":WAV:SOUR {ch}")
#         time.sleep(0.05)

#         # Ask for full memory depth
#         self.inst.write(":WAV:STAR 1")
#         mdep = int(float(self.inst.query(":ACQ:MDEP?")))
#         self.inst.write(f":WAV:STOP {mdep}")

#         # Read preamble
#         pre = self.inst.query(":WAV:PRE?").split(',')
#         npts = int(pre[2])
#         xinc = float(pre[4])
#         xorig = float(pre[5])
#         yinc = float(pre[7])
#         yorig = float(pre[8])
#         yref = float(pre[9])

#         return npts, xinc, xorig, yinc, yorig, yref


#     # ---------------------------------------------------------
#     # Read SCPI block safely
#     # ---------------------------------------------------------
#     def _read_block(self) -> np.ndarray:
#         raw = self.inst.read_raw()

#         if raw[0:1] != b'#':
#             raise RuntimeError("Invalid Rigol block header")

#         num_digits = int(raw[1:2])
#         size = int(raw[2:2 + num_digits])
#         start = 2 + num_digits
#         end = start + size

#         data = raw[start:end]
#         return np.frombuffer(data, dtype=np.uint8)

#     # ---------------------------------------------------------
#     # Capture a single channel
#     # ---------------------------------------------------------
#     def capture_channel(self, ch: str = "CHAN1"):
#         npts, xinc, xorig, yinc, yorig, yref = self._setup_waveform(ch)

#         # Request data block
#         self.inst.write(":WAV:DATA?")
#         time.sleep(0.05)
#         yraw = self._read_block()

#         # Convert to volts
#         volts = (yraw - yref) * yinc + yorig

#         # Time array
#         t = xorig + np.arange(len(volts)) * xinc
#         return t, volts

#     # ---------------------------------------------------------
#     # Capture two channels as a tuple
#     # ---------------------------------------------------------
#     # def capture_two_channels(self, ch1: str = "CHAN1", ch2: str = "CHAN2"):
#     #     t1, v1 = self.capture_channel(ch1)
#     #     time.sleep(0.05)
#     #     t2, v2 = self.capture_channel(ch2)
#     #     return (t1, v1), (t2, v2)
#     def capture_two_channels(self, ch1="CHAN1", ch2="CHAN2"):
#         """
#         Correct method for DS7000 dual-channel capture.
#         Must use RAW mode and set WAV:SOUR only AFTER acquisition.
#         """

#         # ------------------------------
#         # Read CH1
#         # ------------------------------
#         self.inst.write(":WAV:MODE RAW")
#         self.inst.write(":WAV:FORM BYTE")
#         self.inst.write(f":WAV:SOUR {ch1}")
#         pre1 = self.inst.query(":WAV:PRE?").split(',')
#         yinc1 = float(pre1[7])
#         yorig1 = float(pre1[8])
#         yref1 = float(pre1[9])
#         xinc1 = float(pre1[4])
#         xorig1 = float(pre1[5])

#         yraw1 = self.inst.query_binary_values(":WAV:DATA?", datatype='B')
#         v1 = (np.array(yraw1) - yorig1 - yref1) * yinc1
#         t1 = xorig1 + np.arange(len(v1)) * xinc1

#         # ------------------------------
#         # Read CH2
#         # ------------------------------
#         self.inst.write(f":WAV:SOUR {ch2}")
#         pre2 = self.inst.query(":WAV:PRE?").split(',')
#         yinc2 = float(pre2[7])
#         yorig2 = float(pre2[8])
#         yref2 = float(pre2[9])
#         xinc2 = float(pre2[4])
#         xorig2 = float(pre2[5])

#         yraw2 = self.inst.query_binary_values(":WAV:DATA?", datatype='B')
#         v2 = (np.array(yraw2) - yorig2 - yref2) * yinc2
#         t2 = xorig2 + np.arange(len(v2)) * xinc2

#         return (t1, v1), (t2, v2)



#     # ---------------------------------------------------------
#     # Arm + wait helpers (for GUI capture button)
#     # ---------------------------------------------------------
#     def arm(self):
#         """
#         Put scope into SINGLE mode and wait for trigger.
#         """
#         self.inst.write(":STOP")
#         time.sleep(0.05)
#         self.inst.write(":SINGLE")
#         time.sleep(0.1)

    
#     # def wait_and_capture(self, ch1="CHAN1", ch2="CHAN2"):
#     #     """
#     #     Wait indefinitely (or until acquisition completes), then capture both channels.
#     #     Uses trigger state polling per Rigol DS7000 programming guide.
#     #     """

#     #     # Poll trigger state
#     #     while True:
#     #         st = self.inst.query(":TRIG:STAT?").strip()
#     #         # print("DEBUG TRIG:", st)

#     #         # WAIT  = waiting for trigger
#     #         # TD    = triggered
#     #         # STOP  = done
#     #         if st not in ("WAIT", "RUN"):
#     #             break

#     #         time.sleep(0.01)   # 10 ms polling

#     #     # Trigger occurred → now fetch waveforms
#     #     (t1, v1) = self.capture_channel(ch1)
#     #     (t2, v2) = self.capture_channel(ch2)

#     #     return (t1, v1), (t2, v2)
#     def wait_and_capture(self, ch1="CHAN1", ch2="CHAN2", timeout=None):
#         """
#         Correct trigger-wait logic for Rigol DS7000/MSO7000.
#         Supports:
#         - timeout = None → wait forever for trigger
#         - timeout = float → wait up to N seconds
#         """

#         # Arm the scope
#         self.inst.write(":STOP")
#         time.sleep(0.05)
#         self.inst.write(":SINGLE")
#         time.sleep(0.1)

#         start = time.time()

#         # -----------------------------------------
#         # 1. Wait for scope to leave initial STOP
#         # -----------------------------------------
#         while True:
#             st = self.inst.query(":TRIGger:STATus?").strip()

#             if st != "STOP":
#                 break

#             # If user set a finite timeout
#             if timeout is not None and (time.time() - start > timeout):
#                 return None  # never armed properly

#             time.sleep(0.01)

#         # -----------------------------------------
#         # 2. Wait for acquisition to finish
#         # -----------------------------------------
#         while True:
#             st = self.inst.query(":TRIGger:STATus?").strip()

#             # STOP now means acquisition is complete
#             if st == "STOP":
#                 break

#             if timeout is not None and (time.time() - start > timeout):
#                 return None  # no trigger detected

#             time.sleep(0.01)

#         # -----------------------------------------
#         # 3. Get waveform data
#         # -----------------------------------------
#         return self.capture_two_channels(ch1, ch2)







#     def export_csv(self, filename_prefix="rigol"):
#         """
#         Captures CH1 and CH2 and exports them to CSV.
#         Output format:
#             time(s), ch1(V), ch2(V)
#         """
#         # Capture (no rearm arg!)
#         (t1, v1), (t2, v2) = self.capture_two_channels()

#         import numpy as np
#         import csv
#         from datetime import datetime

#         timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
#         filename = f"{filename_prefix}_{timestamp}.csv"

#         # Save combined 3-column CSV
#         rows = zip(t1, v1, v2)

#         with open(filename, "w", newline="") as f:
#             writer = csv.writer(f)
#             writer.writerow(["time_s", "ch1_v", "ch2_v"])
#             writer.writerows(rows)

#         return filename


#     # ---------------------------------------------------------
#     # Cleanup
#     # ---------------------------------------------------------
#     def close(self):
#         if self.inst:
#             self.inst.close()
#             self.inst = None
#         if self.rm:
#             self.rm.close()
#             self.rm = None
import pyvisa
import numpy as np
import time
from typing import List, Tuple, Optional, Dict


class RigolScope:
    """
    Waveform capture helper for Rigol DS7000/MSO7000 series.
    Uses binary block reads (WAV:FORM BYTE) and provides
    arm()/wait_and_capture() helpers for the GUI.
    
    Supports configurable number of channels (default 4 for DS7504).
    """

    def __init__(self, resource_str: str, num_channels: int = 4):
        """
        Initialize RigolScope.
        
        Args:
            resource_str: VISA resource string
            num_channels: Number of channels to capture (1-4, default 4)
        """
        self.resource_str = resource_str
        self.rm = None
        self.inst = None
        self.num_channels = min(4, max(1, num_channels))  # Clamp to 1-4
        
        # Channel names for easy reference
        self.channel_names = [f"CHAN{i+1}" for i in range(self.num_channels)]
        
        # Store last captured data for each channel
        self.last_capture: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}

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

    def set_num_channels(self, num_channels: int):
        """Change the number of channels to capture."""
        self.num_channels = min(4, max(1, num_channels))
        self.channel_names = [f"CHAN{i+1}" for i in range(self.num_channels)]

    # ---------------------------------------------------------
    # Prepare waveform for a single channel
    # ---------------------------------------------------------
    def _setup_waveform(self, ch: str):
        """
        Prepare waveform extraction for channel `ch`.
        IMPORTANT: DO NOT STOP THE SCOPE HERE.
        Stopping should only happen in wait_and_capture().
        """

        # Ensure channel is ON
        self.inst.write(f":{ch}:DISP ON")
        time.sleep(0.02)

        # Set waveform extraction settings
        self.inst.write(":WAV:MODE NORM")
        self.inst.write(":WAV:FORM BYTE")
        self.inst.write(f":WAV:SOUR {ch}")
        time.sleep(0.05)

        # Ask for full memory depth
        self.inst.write(":WAV:STAR 1")
        mdep = int(float(self.inst.query(":ACQ:MDEP?")))
        self.inst.write(f":WAV:STOP {mdep}")

        # Read preamble
        pre = self.inst.query(":WAV:PRE?").split(',')
        npts = int(pre[2])
        xinc = float(pre[4])
        xorig = float(pre[5])
        yinc = float(pre[7])
        yorig = float(pre[8])
        yref = float(pre[9])

        return npts, xinc, xorig, yinc, yorig, yref

    # ---------------------------------------------------------
    # Read SCPI block safely
    # ---------------------------------------------------------
    def _read_block(self) -> np.ndarray:
        raw = self.inst.read_raw()

        if raw[0:1] != b'#':
            raise RuntimeError("Invalid Rigol block header")

        num_digits = int(raw[1:2])
        size = int(raw[2:2 + num_digits])
        start = 2 + num_digits
        end = start + size

        data = raw[start:end]
        return np.frombuffer(data, dtype=np.uint8)

    # ---------------------------------------------------------
    # Capture a single channel
    # ---------------------------------------------------------
    def capture_channel(self, ch: str = "CHAN1") -> Tuple[np.ndarray, np.ndarray]:
        """
        Capture a single channel.
        
        Args:
            ch: Channel name (e.g., "CHAN1", "CHAN2", etc.)
            
        Returns:
            Tuple of (time_array, voltage_array)
        """
        npts, xinc, xorig, yinc, yorig, yref = self._setup_waveform(ch)

        # Request data block
        self.inst.write(":WAV:DATA?")
        time.sleep(0.05)
        yraw = self._read_block()

        # Convert to volts
        volts = (yraw - yref) * yinc + yorig

        # Time array
        t = xorig + np.arange(len(volts)) * xinc
        return t, volts

    # ---------------------------------------------------------
    # Capture two channels as a tuple (legacy compatibility)
    # ---------------------------------------------------------
    def capture_two_channels(self, ch1="CHAN1", ch2="CHAN2"):
        """
        Capture two channels. Legacy method for backward compatibility.
        
        Returns:
            Tuple of ((t1, v1), (t2, v2))
        """
        result = self.capture_n_channels([ch1, ch2])
        return result[ch1], result[ch2]

    # ---------------------------------------------------------
    # Capture N channels
    # ---------------------------------------------------------
    def capture_n_channels(self, channels: Optional[List[str]] = None) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
        """
        Capture multiple channels.
        
        Args:
            channels: List of channel names to capture. If None, uses self.channel_names.
            
        Returns:
            Dict mapping channel name to (time_array, voltage_array)
        """
        if channels is None:
            channels = self.channel_names
            
        result = {}
        
        # Use RAW mode for multi-channel capture
        self.inst.write(":WAV:MODE RAW")
        self.inst.write(":WAV:FORM BYTE")
        
        for ch in channels:
            try:
                self.inst.write(f":WAV:SOUR {ch}")
                time.sleep(0.02)
                
                # Get preamble
                pre = self.inst.query(":WAV:PRE?").split(',')
                yinc = float(pre[7])
                yorig = float(pre[8])
                yref = float(pre[9])
                xinc = float(pre[4])
                xorig = float(pre[5])

                # Get waveform data
                yraw = self.inst.query_binary_values(":WAV:DATA?", datatype='B')
                v = (np.array(yraw) - yorig - yref) * yinc
                t = xorig + np.arange(len(v)) * xinc
                
                result[ch] = (t, v)
                
            except Exception as e:
                print(f"Warning: Failed to capture {ch}: {e}")
                # Return empty arrays on failure
                result[ch] = (np.array([]), np.array([]))
        
        # Store last capture
        self.last_capture = result
        return result

    # ---------------------------------------------------------
    # Capture all configured channels
    # ---------------------------------------------------------
    def capture_all_channels(self) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
        """
        Capture all configured channels.
        
        Returns:
            Dict mapping channel name to (time_array, voltage_array)
        """
        return self.capture_n_channels(self.channel_names)

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

    def wait_and_capture(self, channels: Optional[List[str]] = None, timeout=None) -> Optional[Dict[str, Tuple[np.ndarray, np.ndarray]]]:
        """
        Wait for trigger and capture specified channels.
        
        Args:
            channels: List of channel names to capture. If None, uses configured channels.
            timeout: Optional timeout in seconds. None = wait forever.
            
        Returns:
            Dict mapping channel name to (time_array, voltage_array), or None on timeout.
        """
        if channels is None:
            channels = self.channel_names

        # Arm the scope
        self.inst.write(":STOP")
        time.sleep(0.05)
        self.inst.write(":SINGLE")
        time.sleep(0.1)

        start = time.time()

        # Wait for scope to leave initial STOP
        while True:
            st = self.inst.query(":TRIGger:STATus?").strip()

            if st != "STOP":
                break

            if timeout is not None and (time.time() - start > timeout):
                return None

            time.sleep(0.01)

        # Wait for acquisition to finish
        while True:
            st = self.inst.query(":TRIGger:STATus?").strip()

            if st == "STOP":
                break

            if timeout is not None and (time.time() - start > timeout):
                return None

            time.sleep(0.01)

        # Get waveform data for all channels
        return self.capture_n_channels(channels)

    def wait_and_capture_two(self, ch1="CHAN1", ch2="CHAN2", timeout=None):
        """
        Legacy method: Wait and capture two channels.
        
        Returns:
            Tuple of ((t1, v1), (t2, v2)) or None on timeout.
        """
        result = self.wait_and_capture([ch1, ch2], timeout)
        if result is None:
            return None
        return result[ch1], result[ch2]

    def export_csv(self, filename_prefix="rigol"):
        """
        Captures all configured channels and exports them to CSV.
        """
        import csv
        from datetime import datetime

        # Capture all channels
        data = self.capture_all_channels()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename_prefix}_{timestamp}.csv"

        # Build header and data rows
        header = ["time_s"]
        for ch in self.channel_names:
            header.append(f"{ch.lower()}_v")

        # Get time array from first channel
        first_ch = self.channel_names[0]
        time_array = data[first_ch][0]
        
        # Build rows
        rows = []
        for i in range(len(time_array)):
            row = [time_array[i]]
            for ch in self.channel_names:
                if i < len(data[ch][1]):
                    row.append(data[ch][1][i])
                else:
                    row.append(0)
            rows.append(row)

        with open(filename, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
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
