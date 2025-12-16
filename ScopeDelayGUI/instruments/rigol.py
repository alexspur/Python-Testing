"""
Rigol DS7000/MSO7000 Series Oscilloscope Driver

Based on Rigol DS7000-MSO7000 Programming Guide.

This driver captures up to 4 channels of waveform data from a Rigol oscilloscope
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
        
        results = []
        for ch in [ch1, ch2, ch3, ch4]:
            try:
                # Check if channel is displayed before trying to read
                if self.is_channel_displayed(ch):
                    t, v = self._read_channel_data_raw(ch)
                    results.append((t, v))
                else:
                    # Channel not displayed, return empty arrays
                    results.append((np.array([]), np.array([])))
            except Exception as e:
                # If channel read fails, return empty arrays
                print(f"[RIGOL] Warning: Could not read channel {ch}: {e}")
                results.append((np.array([]), np.array([])))
        
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
