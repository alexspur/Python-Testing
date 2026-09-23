"""
Rigol DS7000/MSO7000 Series Oscilloscope Driver

Based on Rigol DS7000-MSO7000 Programming Guide.

This driver captures up to 4 channels of waveform data from a Rigol oscilloscope
and returns properly scaled voltage/time arrays.
"""

import pyvisa
import numpy as np
import re
import time


# ':ACQuire:MDEPth?' answers with an SI suffix ('1M', '125M') as readily as a
# plain integer, and int(float(...)) raises on the suffixed form - which sent
# the capture into the preamble fallback with whatever STARt/STOP window was
# last left behind. Same parsing as bench_scope_link.py, which reads these
# scopes correctly today.
_SI = {"": 1, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9}


def parse_points(text):
    """Parse ':ACQuire:MDEPth?' replies: '1M', '125M', '1000000', 'AUTO'.

    Returns None for AUTO or anything unparseable, so the caller can fall
    back rather than treating a bad reply as zero points.
    """
    text = (text or "").strip()
    if not text or text.upper() == "AUTO":
        return None
    m = re.fullmatch(r"([0-9.]+(?:[eE][+-]?\d+)?)\s*([kKMG]?)(?:pts)?", text)
    return int(float(m.group(1)) * _SI[m.group(2)]) if m else None


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
        # Called as hook(channel_or_None, message) when a read fails, so the
        # GUI can put it in the session log. Without it these were print()ed
        # and left no durable record of a failed capture anywhere.
        self.error_hook = None
        # Per-channel outcome of the last capture_four_channels() call:
        # {channel: {"state": ok|short|failed|not_displayed, "points": int, ...}}
        self.last_capture_status = {}

    def _report(self, message: str, channel: int = None):
        """Surface a driver-level problem through the GUI logger if wired."""
        hook = getattr(self, "error_hook", None)
        if hook is not None:
            try:
                hook(channel, message)
                return
            except Exception:
                pass
        print(f"[RIGOL] {message}")

    def connect(self, resource_name: str = None):
        """
        Connect to the oscilloscope.
        
        Args:
            resource_name: VISA resource string. Uses stored name if not provided.
        """
        # What the live session (if any) was actually opened with. Captured
        # before resource_name is overwritten below, or the guard further
        # down would compare the new address against itself and keep the old
        # session open while believing it had switched scopes.
        open_resource_name = self.resource_name if self.instr is not None else None

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

        # A second Connect press must not leak a session. Port 5555 accepts
        # one raw-socket client, so an orphaned session locks the scope out
        # until it is power cycled.
        if self.instr is not None:
            if self.resource_name == open_resource_name:
                return                      # already connected to this scope
            self.disconnect()               # moving to a different resource

        self.instr = self.rm.open_resource(self.resource_name)
        self.instr.timeout = 30000  # 30 second timeout for large transfers
        self.instr.read_termination = '\n'
        self.instr.write_termination = '\n'

        # A raw socket has no keepalive by default, so a scope that reboots or
        # a link that flaps leaves a half-open session that still reports
        # connected and costs a full 30 s timeout on every read. VXI-11 fails
        # faster on its own; the socket needs to be told.
        if '::SOCKET' in self.resource_name.upper():
            try:
                self.instr.set_visa_attribute(
                    pyvisa.constants.ResourceAttribute.tcpip_keepalive, True)
            except Exception as e:
                self._report(f"TCP keepalive not set on {self.resource_name}: {e}")

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
        """Send a query and read one TMC block by its declared length.

        Do not use read_raw() here. A raw TCP socket is an undelimited byte
        stream, so read_raw() has no stop condition and blocks until the
        timeout. Reading the declared byte count works on every transport,
        and a short transfer raises instead of returning truncated data.
        """
        old_term = self.instr.read_termination
        self.instr.read_termination = None
        try:
            self.instr.write(cmd)
            head = self.instr.read_bytes(2)
            if head[0:1] != b'#':
                raise ValueError(f"Invalid TMC header, expected '#', got {head[0:1]!r}")
            n_digits = int(head[1:2])
            length = int(self.instr.read_bytes(n_digits))
            data = self.instr.read_bytes(length)
            if len(data) != length:
                raise IOError(f"TMC block declared {length} bytes, got {len(data)}")
            # Trailing newline. Short timeout so a missing byte never costs the
            # full 30 s driver timeout.
            old_timeout = self.instr.timeout
            self.instr.timeout = 200
            try:
                self.instr.read_bytes(1)
            except Exception:
                pass
            finally:
                self.instr.timeout = old_timeout
            return data
        except Exception:
            # Resync before anything else is asked of this session. A failed
            # block read leaves the rest of that block in the socket, and the
            # next ASCII query reads those bytes as its reply: ':CHANnel2:
            # DISPlay?' comes back as garbage, the channel is taken for "not
            # displayed", and it is dropped with no warning. That is why only
            # channel 1 ever reported an error.
            self._drain()
            raise
        finally:
            self.instr.read_termination = old_term

    def _drain(self, settle_ms: int = 300) -> int:
        """Discard whatever is still in flight after a failed transfer.

        Deliberately not flush() or clear(): discard_read_buffer_no_io does no
        I/O so it leaves the queued bytes exactly where they are, and
        discard_read_buffer reads until an END indicator a raw socket never
        sends. A timed read is transport-agnostic and costs settle_ms once.
        """
        dropped = 0
        old_timeout = self.instr.timeout
        old_term = self.instr.read_termination
        self.instr.timeout = settle_ms
        self.instr.read_termination = None
        try:
            while True:
                try:
                    chunk = self.instr.read_bytes(self.instr.chunk_size)
                except Exception:
                    break               # nothing left within settle_ms
                if not chunk:
                    break
                dropped += len(chunk)
        finally:
            self.instr.timeout = old_timeout
            self.instr.read_termination = old_term
        if dropped:
            self._report(f"drained {dropped} stale bytes after a failed read")
        return dropped

    @staticmethod
    def parse_points(text):
        """Kept as a method for callers that already hold a scope."""
        return parse_points(text)

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
        
    def is_channel_displayed(self, channel: int) -> bool:
        """
        Check if a channel is currently displayed/enabled.
        
        Args:
            channel: Channel number (1-4)
            
        Returns:
            True if channel is displayed, False otherwise
        """
        try:
            resp = self._query(f':CHANnel{channel}:DISPlay?')
            return resp in ('1', 'ON')
        except:
            return False
    
    def _query_channel_displayed(self, channel: int) -> bool:
        """Strict display query: a transport failure raises.

        is_channel_displayed() answers False for both "the operator turned
        this channel off" and "the query failed", which made a desynced socket
        look like three disabled channels. The capture path needs to tell
        those apart, so it uses this instead.
        """
        resp = self._query(f':CHANnel{channel}:DISPlay?')
        return resp.strip() in ('1', 'ON')

    def get_displayed_channels(self) -> list:
        """
        Get list of currently displayed channel numbers.
        
        Returns:
            List of channel numbers that are displayed (e.g., [1, 2, 3])
        """
        displayed = []
        for ch in range(1, 5):
            if self.is_channel_displayed(ch):
                displayed.append(ch)
        return displayed
        
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
        
    def _get_memory_depth(self) -> int:
        """Return the acquisition memory depth (total RAW points available).

        Falls back to the preamble's point count if :ACQuire:MDEPth? is 'AUTO'
        or unparseable. The reply may be SI-suffixed ('1M', '125M'), which
        int(float(...)) cannot parse - it raised and silently dropped the
        capture into the preamble fallback."""
        try:
            depth = parse_points(self._query(':ACQuire:MDEPth?'))
            if depth:
                return depth
            raise ValueError("AUTO or unparseable memory depth")
        except Exception:
            try:
                return int(self._get_waveform_preamble()['points'])
            except Exception:
                return 0

    def _read_channel_data_raw(self, channel: int, chunk_size: int = 250000) -> tuple:
        """
        Read the full internal memory for a channel (RAW mode), in chunks.

        Rigol scopes cap how many points a single :WAVeform:DATA? returns, and a
        too-large single transfer times out mid-read and yields TRUNCATED data
        (e.g. 552950/143350 points instead of 1,000,000). So we walk the memory
        with explicit STARt/STOP windows and concatenate until every point is in.

        Note: the oscilloscope must be stopped before reading RAW data.

        Args:
            channel: Channel number (1-4)
            chunk_size: Points to request per transfer (Rigol BYTE-mode safe max)

        Returns:
            Tuple of (time_array, voltage_array) as numpy arrays
        """
        # Set waveform source, RAW mode (internal memory), BYTE format.
        self._write(f':WAVeform:SOURce CHANnel{channel}')
        self._write(':WAVeform:MODE RAW')
        self._write(':WAVeform:FORMat BYTE')

        # Total points to read out of memory.
        total = self._get_memory_depth()
        if total <= 0:
            return np.array([]), np.array([])

        # Read the scaling preamble once (yinc/xinc are constant across chunks).
        self._write(':WAVeform:STARt 1')
        self._write(f':WAVeform:STOP {min(chunk_size, total)}')
        preamble = self._get_waveform_preamble()

        # Walk the memory in chunks. Advance by the number of points actually
        # returned so a short read can't desync the window.
        chunks = []
        start = 1
        while start <= total:
            stop = min(start + chunk_size - 1, total)
            self._write(f':WAVeform:STARt {start}')
            self._write(f':WAVeform:STOP {stop}')
            raw = self._query_binary(':WAVeform:DATA?')
            vals = np.frombuffer(raw, dtype=np.uint8)
            if vals.size == 0:
                break  # nothing came back — avoid an infinite loop
            chunks.append(vals)
            start += vals.size

        if chunks:
            raw_values = np.concatenate(chunks)
        else:
            raw_values = np.array([], dtype=np.uint8)

        # Convert ADC counts to voltage using preamble parameters.
        yinc = preamble['yincrement']
        yorig = preamble['yorigin']
        yref = preamble['yreference']
        voltage = (raw_values.astype(float) - yref - yorig) * yinc

        # Generate the time array from the timebase.
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
    
    # def capture_four_channels(self, ch1: int = 1, ch2: int = 2, 
    #                            ch3: int = 3, ch4: int = 4) -> tuple:
    #     """
    #     Capture waveform data from four channels.
        
    #     This reads the currently displayed waveform data (NORMAL mode).
    #     The scope should already be stopped with data on screen.
    #     If a channel is not displayed, returns empty arrays for that channel.
        
    #     Args:
    #         ch1: First channel number (default: 1)
    #         ch2: Second channel number (default: 2)
    #         ch3: Third channel number (default: 3)
    #         ch4: Fourth channel number (default: 4)
            
    #     Returns:
    #         Tuple of ((t1, v1), (t2, v2), (t3, v3), (t4, v4)) where each is numpy arrays
    #     """
    #     results = []
    #     for ch in [ch1, ch2, ch3, ch4]:
    #         try:
    #             # Check if channel is displayed before trying to read
    #             if self.is_channel_displayed(ch):
    #                 t, v = self._read_channel_data(ch)
    #                 results.append((t, v))
    #             else:
    #                 # Channel not displayed, return empty arrays
    #                 results.append((np.array([]), np.array([])))
    #         except Exception as e:
    #             # If channel read fails, return empty arrays
    #             print(f"[RIGOL] Warning: Could not read channel {ch}: {e}")
    #             results.append((np.array([]), np.array([])))
        
    #     return tuple(results)
    
    # def capture_channels(self, channels: list = None) -> tuple:
    #     """
    #     Capture waveform data from specified channels.
        
    #     Args:
    #         channels: List of channel numbers to capture (default: [1, 2, 3, 4])
            
    #     Returns:
    #         Tuple of (t, v) pairs for each channel
    #     """
    #     if channels is None:
    #         channels = [1, 2, 3, 4]
        
    #     results = []
    #     for ch in channels:
    #         try:
    #             if self.is_channel_displayed(ch):
    #                 t, v = self._read_channel_data(ch)
    #                 results.append((t, v))
    #             else:
    #                 results.append((np.array([]), np.array([])))
    #         except Exception as e:
    #             print(f"[RIGOL] Warning: Could not read channel {ch}: {e}")
    #             results.append((np.array([]), np.array([])))
        
    #     return tuple(results)
    def capture_four_channels(self, ch1: int = 1, ch2: int = 2, 
                            ch3: int = 3, ch4: int = 4) -> tuple:
        """
        Capture full memory waveform data from four channels.
        
        Reads the full memory depth (RAW mode) from all specified channels.
        The scope will be stopped before reading to ensure data stability.
        If a channel is not displayed, returns empty arrays for that channel.
        
        Args:
            ch1: First channel number (default: 1)
            ch2: Second channel number (default: 2)
            ch3: Third channel number (default: 3)
            ch4: Fourth channel number (default: 4)
            
        Returns:
            Tuple of ((t1, v1), (t2, v2), (t3, v3), (t4, v4)) where each is numpy arrays
        """
        # Stop acquisition to ensure data is stable for RAW mode reading
        self.stop()

        try:
            expected = self._get_memory_depth()
        except Exception:
            expected = 0

        empty = (np.array([]), np.array([]))
        results = []
        status = {}

        for ch in [ch1, ch2, ch3, ch4]:
            # A failed display query is a failure, not a disabled channel.
            try:
                displayed = self._query_channel_displayed(ch)
            except Exception as e:
                status[ch] = {"state": "failed", "points": 0,
                              "expected": expected, "error": f"display query failed: {e}"}
                self._report(f"channel {ch}: display query failed: {e}", channel=ch)
                results.append(empty)
                continue

            if not displayed:
                status[ch] = {"state": "not_displayed", "points": 0,
                              "expected": expected, "error": ""}
                results.append(empty)
                continue

            try:
                t, v = self._read_channel_data_raw(ch)
                n = len(v)
                short = bool(expected) and n < expected
                status[ch] = {"state": "short" if short else "ok", "points": n,
                              "expected": expected, "error": ""}
                if short:
                    self._report(f"channel {ch}: short read, {n} of {expected} points",
                                 channel=ch)
                results.append((t, v))
            except Exception as e:
                status[ch] = {"state": "failed", "points": 0,
                              "expected": expected, "error": str(e)}
                self._report(f"channel {ch}: read failed: {e}", channel=ch)
                results.append(empty)

        self.last_capture_status = status
        return tuple(results)
    def capture_channels(self, channels: list = None) -> tuple:
        """
        Capture full memory waveform data from specified channels.
        
        Reads the full memory depth (RAW mode) from all specified channels.
        The scope will be stopped before reading to ensure data stability.
        
        Args:
            channels: List of channel numbers to capture (default: [1, 2, 3, 4])
            
        Returns:
            Tuple of (t, v) pairs for each channel
        """
        if channels is None:
            channels = [1, 2, 3, 4]
        
        # Stop acquisition to ensure data is stable for RAW mode reading
        self.stop()
        
        results = []
        for ch in channels:
            try:
                if self.is_channel_displayed(ch):
                    t, v = self._read_channel_data_raw(ch)
                    results.append((t, v))
                else:
                    results.append((np.array([]), np.array([])))
            except Exception as e:
                print(f"[RIGOL] Warning: Could not read channel {ch}: {e}")
                results.append((np.array([]), np.array([])))
        
        return tuple(results)
        
    def wait_and_capture(self, ch1: int = 1, ch2: int = 2,
                         timeout: float = 300.0) -> tuple:
        """
        Arm single trigger, wait for acquisition, then capture two channels.
        
        This is the main method for triggered acquisition (legacy 2-channel).
        
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
    
    def wait_and_capture_four(self, ch1: int = 1, ch2: int = 2,
                               ch3: int = 3, ch4: int = 4,
                               timeout: float = 300.0) -> tuple:
        """
        Arm single trigger, wait for acquisition, then capture four channels.
        
        Args:
            ch1-ch4: Channel numbers (default: 1, 2, 3, 4)
            timeout: Maximum time to wait for trigger in seconds
            
        Returns:
            Tuple of ((t1, v1), (t2, v2), (t3, v3), (t4, v4)) where each is numpy arrays
            
        Raises:
            TimeoutError: If trigger doesn't occur within timeout
        """
        # Arm single trigger
        self.single()
        
        # Wait for trigger and acquisition to complete
        if not self.wait_for_trigger(timeout=timeout):
            raise TimeoutError(f"Trigger timeout after {timeout} seconds")
            
        # Capture all four channels
        return self.capture_four_channels(ch1, ch2, ch3, ch4)


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
        
        # Show which channels are displayed
        displayed = scope.get_displayed_channels()
        print(f"Displayed channels: {displayed}")
        
        return True
    except Exception as e:
        print(f"Connection failed: {e}")
        return False
    finally:
        scope.disconnect()


if __name__ == '__main__':
    # Quick test
    test_connection()
