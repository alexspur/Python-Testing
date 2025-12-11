# # import pyvisa
# # import numpy as np
# # import time


# # class RigolScope:
# #     """
# #     Waveform capture helper for Rigol DS7000/MSO7000 series.
# #     Uses binary block reads (WAV:FORM BYTE) and provides
# #     arm()/wait_and_capture() helpers for the GUI.
# #     """

# #     def __init__(self, resource_str: str):
# #         self.resource_str = resource_str
# #         self.rm = None
# #         self.inst = None

# #     # ---------------------------------------------------------
# #     # Connect
# #     # ---------------------------------------------------------
# #     def connect(self):
# #         self.rm = pyvisa.ResourceManager()
# #         self.inst = self.rm.open_resource(self.resource_str)

# #         # Increase timeout for slow data transfers
# #         self.inst.timeout = 30000  # 30 seconds (was 15s)
# #         self.inst.chunk_size = 20_000_000  # 20 MB for long memory (was 2MB)

# #         self.inst.write("*CLS")
# #         time.sleep(0.1)

# #         print(f"[RIGOL] Connected: {self.resource_str}")
# #         print(f"[RIGOL] Timeout: {self.inst.timeout}ms, Chunk size: {self.inst.chunk_size} bytes")

# #     def identify(self) -> str:
# #         return self.inst.query("*IDN?").strip()

# #     # ---------------------------------------------------------
# #     # Arm + wait helpers (for GUI capture button)
# #     # ---------------------------------------------------------
# #     def arm(self):
# #         """
# #         Put scope into SINGLE mode and wait for trigger.
# #         """
# #         print(f"[RIGOL] Arming scope (STOP -> SINGLE)...")
# #         self.inst.write(":STOP")
# #         time.sleep(0.1)
# #         self.inst.write(":SINGLE")
# #         time.sleep(0.2)

# #         # Verify scope is armed
# #         try:
# #             status = self.inst.query(":TRIGger:STATus?").strip().upper()
# #             print(f"[RIGOL] Arm complete, status: {status}")
# #         except:
# #             print(f"[RIGOL] WARNING: Could not verify arm status")

# #     # ---------------------------------------------------------
# #     # Capture two channels (ORIGINAL WORKING CODE)
# #     # ---------------------------------------------------------
# #     def capture_two_channels(self, ch1="CHAN1", ch2="CHAN2"):
# #         """
# #         Correct method for DS7000 dual-channel capture.
# #         Must use RAW mode and set WAV:SOUR only AFTER acquisition.
# #         """

# #         try:
# #             # Check if scope has stopped (data available)
# #             status = self.inst.query(":TRIGger:STATus?").strip().upper()
# #             print(f"[RIGOL] Current status before capture: {status}")

# #             if status != "STOP":
# #                 print(f"[RIGOL] WARNING: Scope not in STOP state, capture may fail")

# #             # ------------------------------
# #             # Read CH1
# #             # ------------------------------
# #             print(f"[RIGOL] Setting up waveform mode...")
# #             self.inst.write(":WAV:MODE RAW")
# #             time.sleep(0.05)
# #             self.inst.write(":WAV:FORM BYTE")
# #             time.sleep(0.05)
# #             self.inst.write(f":WAV:SOUR {ch1}")
# #             time.sleep(0.05)

# #             print(f"[RIGOL] Reading {ch1} preamble...")
# #             pre1 = self.inst.query(":WAV:PRE?").split(',')
# #             yinc1 = float(pre1[7])
# #             yorig1 = float(pre1[8])
# #             yref1 = float(pre1[9])
# #             xinc1 = float(pre1[4])
# #             xorig1 = float(pre1[5])

# #             print(f"[RIGOL] Reading {ch1} waveform data (this may take time)...")
# #             yraw1 = self.inst.query_binary_values(":WAV:DATA?", datatype='B', container=list)
# #             v1 = (np.array(yraw1) - yorig1 - yref1) * yinc1
# #             t1 = xorig1 + np.arange(len(v1)) * xinc1
# #             print(f"[RIGOL] {ch1}: {len(v1)} points captured")

# #             # ------------------------------
# #             # Read CH2
# #             # ------------------------------
# #             print(f"[RIGOL] Reading {ch2}...")
# #             self.inst.write(f":WAV:SOUR {ch2}")
# #             time.sleep(0.05)

# #             print(f"[RIGOL] Reading {ch2} preamble...")
# #             pre2 = self.inst.query(":WAV:PRE?").split(',')
# #             yinc2 = float(pre2[7])
# #             yorig2 = float(pre2[8])
# #             yref2 = float(pre2[9])
# #             xinc2 = float(pre2[4])
# #             xorig2 = float(pre2[5])

# #             print(f"[RIGOL] Reading {ch2} waveform data (this may take time)...")
# #             yraw2 = self.inst.query_binary_values(":WAV:DATA?", datatype='B', container=list)
# #             v2 = (np.array(yraw2) - yorig2 - yref2) * yinc2
# #             t2 = xorig2 + np.arange(len(v2)) * xinc2
# #             print(f"[RIGOL] {ch2}: {len(v2)} points captured")

# #             print(f"[RIGOL] Capture successful!")
# #             return (t1, v1), (t2, v2)

# #         except Exception as e:
# #             print(f"[RIGOL] ERROR in capture_two_channels: {e}")
# #             raise

# #     # ---------------------------------------------------------
# #     # Wait and capture
# #     # ---------------------------------------------------------
# #     def wait_and_capture(self, ch1="CHAN1", ch2="CHAN2", timeout=30.0):
# #         """
# #         Wait for trigger and capture two channels.

# #         Args:
# #             ch1: First channel to capture (default CHAN1)
# #             ch2: Second channel to capture (default CHAN2)
# #             timeout: Timeout in seconds (default 30.0)

# #         Returns:
# #             Tuple of ((t1,v1), (t2,v2)) or None on timeout.
# #         """
# #         start = time.time()

# #         print(f"[RIGOL] Waiting for trigger... (timeout={timeout}s)")

# #         # Wait for acquisition to finish
# #         triggered = False
# #         saw_wait = False

# #         while (time.time() - start) < timeout:
# #             try:
# #                 st = self.inst.query(":TRIGger:STATus?").strip().upper()

# #                 # Print status for debugging (only first occurrence)
# #                 if st == "WAIT" and not saw_wait:
# #                     print(f"[RIGOL] Status: WAIT (waiting for trigger)")
# #                     saw_wait = True
# #                 elif st == "TD" and not triggered:
# #                     print(f"[RIGOL] Status: TD (triggered, acquiring)")
# #                     triggered = True
# #                 elif st == "STOP" and not triggered and not saw_wait:
# #                     # Scope is already stopped - never armed or trigger already happened
# #                     print(f"[RIGOL] Status: STOP (already stopped - scope may not be armed)")
# #                     # Try to capture anyway - data might be from previous trigger
# #                     triggered = True
# #                     break

# #                 # Track if we've seen trigger
# #                 if st == "TD":
# #                     triggered = True

# #                 # STOP means acquisition complete
# #                 if st == "STOP" and (triggered or saw_wait):
# #                     print(f"[RIGOL] Status: STOP (acquisition complete)")
# #                     break

# #             except Exception as e:
# #                 print(f"[RIGOL] Error checking status: {e}")
# #                 time.sleep(0.05)
# #                 continue

# #             time.sleep(0.02)
# #         else:
# #             # Timeout occurred
# #             elapsed = time.time() - start
# #             print(f"[RIGOL] TIMEOUT after {elapsed:.1f}s - never triggered")
# #             return None

# #         # Check if we actually have valid data to capture
# #         if not triggered and not saw_wait:
# #             print(f"[RIGOL] WARNING: Scope never triggered, but will try to capture existing data")

# #         # Give scope time to settle before reading data
# #         time.sleep(0.1)

# #         print(f"[RIGOL] Capturing waveforms from {ch1} and {ch2}...")
# #         return self.capture_two_channels(ch1, ch2)

# #     # ---------------------------------------------------------
# #     # Export to CSV
# #     # ---------------------------------------------------------
# #     def export_csv(self, filename_prefix="rigol"):
# #         """
# #         Captures CH1 and CH2 and exports them to CSV.
# #         Output format:
# #             time(s), ch1(V), ch2(V)
# #         """
# #         import csv
# #         from datetime import datetime

# #         # Capture
# #         (t1, v1), (t2, v2) = self.capture_two_channels()

# #         timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
# #         filename = f"{filename_prefix}_{timestamp}.csv"

# #         # Save combined 3-column CSV
# #         rows = zip(t1, v1, v2)

# #         with open(filename, "w", newline="") as f:
# #             writer = csv.writer(f)
# #             writer.writerow(["time_s", "ch1_v", "ch2_v"])
# #             writer.writerows(rows)

# #         return filename

# #     # ---------------------------------------------------------
# #     # Cleanup
# #     # ---------------------------------------------------------
# #     def close(self):
# #         if self.inst:
# #             self.inst.close()
# #             self.inst = None
# #         if self.rm:
# #             self.rm.close()
# #             self.rm = None
# import pyvisa
# import numpy as np
# import time


# class RigolScope:
#     """
#     Waveform capture helper for Rigol DS7000/MSO7000 series.
#     Uses binary block reads (WAV:FORM BYTE) and provides
#     arm()/wait_and_capture() helpers for the GUI.
#     """

#     def __init__(self, resource_str: str, **kwargs):
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

#     # ---------------------------------------------------------
#     # Prepare waveform for a single channel
#     # ---------------------------------------------------------
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

"""
Rigol DS7000/MSO7000 Series Oscilloscope Driver

Based on Rigol DS7000-MSO7000 Programming Guide.

This driver captures 2 channels of waveform data from a Rigol oscilloscope
and returns properly scaled voltage/time arrays.
"""

import pyvisa
import numpy as np
import time


class RigolScope:
    """Driver for Rigol DS7000/MSO7000 series oscilloscopes."""
    
    def __init__(self, resource_name: str = None):
        """
        Initialize connection to oscilloscope.
        
        Args:
            resource_name: VISA resource string (e.g., 'USB0::0x1AB1::0x0514::DS7...::INSTR')
                          If None, will try to find first available Rigol scope.
        """
        self.rm = pyvisa.ResourceManager()
        self.instr = None
        self.resource_name = resource_name
        
    def connect(self, resource_name: str = None):
        """
        Connect to the oscilloscope.
        
        Args:
            resource_name: VISA resource string. Uses stored name if not provided.
        """
        if resource_name:
            self.resource_name = resource_name
            
        if not self.resource_name:
            # Try to find a Rigol scope
            resources = self.rm.list_resources()
            for res in resources:
                if '1AB1' in res:  # Rigol vendor ID
                    self.resource_name = res
                    break
                    
        if not self.resource_name:
            raise RuntimeError("No Rigol oscilloscope found")
            
        self.instr = self.rm.open_resource(self.resource_name)
        self.instr.timeout = 30000  # 30 second timeout for large transfers
        self.instr.read_termination = '\n'
        self.instr.write_termination = '\n'
        
        # Verify connection
        idn = self.instr.query('*IDN?')
        print(f"Connected to: {idn.strip()}")
        
    def disconnect(self):
        """Disconnect from the oscilloscope."""
        if self.instr:
            self.instr.close()
            self.instr = None
            
    def is_connected(self) -> bool:
        """Check if connected to oscilloscope."""
        return self.instr is not None
        
    def _write(self, cmd: str):
        """Send command to oscilloscope."""
        self.instr.write(cmd)
        
    def _query(self, cmd: str) -> str:
        """Query oscilloscope and return response."""
        return self.instr.query(cmd).strip()
        
    def _query_binary(self, cmd: str) -> bytes:
        """Query oscilloscope and return binary data with TMC header parsing."""
        # Temporarily disable read termination for binary data
        old_term = self.instr.read_termination
        self.instr.read_termination = None
        try:
            self.instr.write(cmd)
            # Read raw bytes - the scope returns TMC format: #NXXXXXX<data>
            raw = self.instr.read_raw()
            return self._parse_tmc_data(raw)
        finally:
            self.instr.read_termination = old_term
        
    def _parse_tmc_data(self, raw: bytes) -> bytes:
        """
        Parse TMC block data format.
        
        Format: #NXXXXXX<data><terminator>
        Where:
            # is the header identifier
            N is number of digits describing data length
            XXXXXX is the data length in ASCII
            <data> is the actual binary data
            <terminator> is usually \n
        """
        if raw[0:1] != b'#':
            raise ValueError(f"Invalid TMC header, expected '#', got {raw[0:1]}")
            
        # Get number of length digits
        n_digits = int(raw[1:2])
        
        # Get data length
        data_length = int(raw[2:2+n_digits])
        
        # Extract data (skip header, take data_length bytes)
        header_length = 2 + n_digits
        data = raw[header_length:header_length + data_length]
        
        return data
        
    def get_trigger_status(self) -> str:
        """
        Query current trigger status.
        
        Returns:
            One of: 'TD' (triggered), 'WAIT', 'RUN', 'AUTO', 'STOP'
        """
        return self._query(':TRIGger:STATus?')
        
    def single(self):
        """Set oscilloscope to single trigger mode and arm."""
        self._write(':SINGle')
        
    def stop(self):
        """Stop acquisition."""
        self._write(':STOP')
        
    def run(self):
        """Start continuous acquisition."""
        self._write(':RUN')
        
    def force_trigger(self):
        """Force a trigger event."""
        self._write(':TFORce')
        
    def wait_for_trigger(self, timeout: float = 10.0, poll_interval: float = 0.1) -> bool:
        """
        Wait for the oscilloscope to trigger and stop.
        
        Per the programming guide, :TRIGger:STATus? returns:
            TD    - Triggered (data acquired)
            WAIT  - Waiting for trigger
            RUN   - Running (auto trigger mode acquiring)
            AUTO  - Auto triggered
            STOP  - Stopped
            
        Args:
            timeout: Maximum time to wait in seconds
            poll_interval: Time between status checks in seconds
            
        Returns:
            True if triggered successfully, False if timeout
        """
        start_time = time.time()
        
        while (time.time() - start_time) < timeout:
            status = self.get_trigger_status()
            
            # STOP or TD means acquisition is complete and ready to read
            if status in ('STOP', 'TD'):
                return True
                
            time.sleep(poll_interval)
            
        return False
        
    def _get_waveform_preamble(self) -> dict:
        """
        Get waveform preamble containing scaling parameters.
        
        Returns dict with:
            format: 0=BYTE, 1=WORD, 2=ASC
            type: 0=NORMal, 1=MAXimum, 2=RAW
            points: number of data points
            count: number of averages
            xincrement: time between points (seconds)
            xorigin: start time (seconds)
            xreference: reference time point
            yincrement: voltage per LSB
            yorigin: vertical offset in ADC counts
            yreference: ADC reference value (128 for NORMAL mode)
        """
        response = self._query(':WAVeform:PREamble?')
        parts = response.split(',')
        
        return {
            'format': int(parts[0]),
            'type': int(parts[1]),
            'points': int(parts[2]),
            'count': int(parts[3]),
            'xincrement': float(parts[4]),
            'xorigin': float(parts[5]),
            'xreference': float(parts[6]),
            'yincrement': float(parts[7]),
            'yorigin': float(parts[8]),
            'yreference': float(parts[9]),
        }
        
    def _read_channel_data(self, channel: int) -> tuple:
        """
        Read waveform data from a single channel.
        
        Args:
            channel: Channel number (1-4)
            
        Returns:
            Tuple of (time_array, voltage_array) as numpy arrays
        """
        # Set waveform source to the specified channel
        self._write(f':WAVeform:SOURce CHANnel{channel}')
        
        # Set to NORMAL mode (read screen data) 
        # Use RAW mode if you need full memory depth
        self._write(':WAVeform:MODE NORMal')
        
        # Set byte format for data transfer
        self._write(':WAVeform:FORMat BYTE')
        
        # Get the preamble with scaling factors
        preamble = self._get_waveform_preamble()
        
        # Read the waveform data
        raw_data = self._query_binary(':WAVeform:DATA?')
        
        # Convert bytes to numpy array
        raw_values = np.frombuffer(raw_data, dtype=np.uint8)
        
        # Convert to voltage using preamble parameters
        # Formula: voltage = (raw_value - yreference - yorigin) * yincrement
        yinc = preamble['yincrement']
        yorig = preamble['yorigin']
        yref = preamble['yreference']
        
        voltage = (raw_values.astype(float) - yref - yorig) * yinc
        
        # Generate time array
        # Formula: time = xorigin + index * xincrement
        xinc = preamble['xincrement']
        xorig = preamble['xorigin']
        
        time_array = xorig + np.arange(len(voltage)) * xinc
        
        return time_array, voltage
        
    def _read_channel_data_raw(self, channel: int, start: int = 1, stop: int = None) -> tuple:
        """
        Read waveform data from internal memory (RAW mode).
        
        Note: Oscilloscope must be stopped before reading RAW data.
        
        Args:
            channel: Channel number (1-4)
            start: Start point (1-based index)
            stop: Stop point (if None, reads all available)
            
        Returns:
            Tuple of (time_array, voltage_array) as numpy arrays
        """
        # Set waveform source to the specified channel
        self._write(f':WAVeform:SOURce CHANnel{channel}')
        
        # Set to RAW mode (read internal memory)
        self._write(':WAVeform:MODE RAW')
        
        # Set byte format for data transfer
        self._write(':WAVeform:FORMat BYTE')
        
        # Set start and stop points if specified
        self._write(f':WAVeform:STARt {start}')
        if stop is not None:
            self._write(f':WAVeform:STOP {stop}')
            
        # Get the preamble with scaling factors
        preamble = self._get_waveform_preamble()
        
        # Read the waveform data
        raw_data = self._query_binary(':WAVeform:DATA?')
        
        # Convert bytes to numpy array
        raw_values = np.frombuffer(raw_data, dtype=np.uint8)
        
        # Convert to voltage using preamble parameters
        yinc = preamble['yincrement']
        yorig = preamble['yorigin']
        yref = preamble['yreference']
        
        voltage = (raw_values.astype(float) - yref - yorig) * yinc
        
        # Generate time array
        xinc = preamble['xincrement']
        xorig = preamble['xorigin']
        
        time_array = xorig + np.arange(len(voltage)) * xinc
        
        return time_array, voltage
        
    def capture_two_channels(self, ch1: int = 1, ch2: int = 2) -> tuple:
        """
        Capture waveform data from two channels.
        
        This reads the currently displayed waveform data (NORMAL mode).
        The scope should already be stopped with data on screen.
        
        Args:
            ch1: First channel number (default: 1)
            ch2: Second channel number (default: 2)
            
        Returns:
            Tuple of ((t1, v1), (t2, v2)) where each is numpy arrays
        """
        # Read channel 1
        t1, v1 = self._read_channel_data(ch1)
        
        # Read channel 2
        t2, v2 = self._read_channel_data(ch2)
        
        return (t1, v1), (t2, v2)
        
    def wait_and_capture(self, ch1: int = 1, ch2: int = 2,
                         timeout: float = 300.0) -> tuple:
        """
        Arm single trigger, wait for acquisition, then capture two channels.
        
        This is the main method for triggered acquisition.
        
        Args:
            ch1: First channel number (default: 1)
            ch2: Second channel number (default: 2)
            timeout: Maximum time to wait for trigger in seconds
            
        Returns:
            Tuple of ((t1, v1), (t2, v2)) where each is numpy arrays
            
        Raises:
            TimeoutError: If trigger doesn't occur within timeout
        """
        # Arm single trigger
        self.single()
        
        # Wait for trigger and acquisition to complete
        if not self.wait_for_trigger(timeout=timeout):
            raise TimeoutError(f"Trigger timeout after {timeout} seconds")
            
        # Capture both channels
        return self.capture_two_channels(ch1, ch2)


# Convenience function for quick testing
def test_connection(resource_name: str = None):
    """Test connection to a Rigol oscilloscope."""
    scope = RigolScope(resource_name)
    try:
        scope.connect()
        print("Connection successful!")
        
        # Try to read trigger status
        status = scope.get_trigger_status()
        print(f"Trigger status: {status}")
        
        return True
    except Exception as e:
        print(f"Connection failed: {e}")
        return False
    finally:
        scope.disconnect()


if __name__ == '__main__':
    # Quick test
    test_connection()
