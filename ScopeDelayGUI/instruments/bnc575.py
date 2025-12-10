# import time
# from dataclasses import dataclass, field
# from typing import Dict, Tuple

# import serial

# # Static capability map (no device queries)
# capabilities: Dict[str, Dict[str, bool]] = {
#     "CHA": {"delay": True, "width": True, "polarity": True},
#     "CHB": {"delay": True, "width": True, "polarity": True},
#     "CHC": {"delay": True, "width": True, "polarity": True},
#     "CHD": {"delay": True, "width": True, "polarity": True},
#     "T0": {"trigger": True, "source_select": True},
# }


# @dataclass
# class ChannelState:
#     delay: float = 0.0
#     width: float = 1e-6
#     polarity: str = "POS"  # POS or NEG
#     enabled: bool = True


# @dataclass
# class TriggerState:
#     source: str = "EXT"  # EXT, INT (cached only)
#     enabled: bool = False
#     level: float = 3.0
#     slope: str = "POS"  # POS / NEG
#     mode: str = "TRIG"  # TRIG, DUAL, DIS


# @dataclass
# class BNC575Model:
#     channels: Dict[str, ChannelState] = field(default_factory=dict)
#     trigger: TriggerState = field(default_factory=TriggerState)

#     def __post_init__(self) -> None:
#         for name in ["CHA", "CHB", "CHC", "CHD"]:
#             self.channels.setdefault(name, ChannelState())

#     # Channel setters
#     def set_delay(self, channel: str, value: float) -> None:
#         self.channels[channel].delay = value

#     def set_width(self, channel: str, value: float) -> None:
#         self.channels[channel].width = value

#     def set_polarity(self, channel: str, value: str) -> None:
#         self.channels[channel].polarity = value.upper()

#     def set_enabled(self, channel: str, enabled: bool) -> None:
#         self.channels[channel].enabled = enabled

#     # Trigger setters
#     def set_trigger_source(self, source: str) -> None:
#         self.trigger.source = source.upper()

#     def set_trigger_output(self, enabled: bool) -> None:
#         self.trigger.enabled = enabled

#     def set_trigger_level(self, level: float) -> None:
#         self.trigger.level = level

#     def set_trigger_slope(self, slope: str) -> None:
#         self.trigger.slope = slope.upper()

#     def set_trigger_mode(self, mode: str) -> None:
#         self.trigger.mode = mode.upper()

#     def snapshot(self) -> Dict[str, Dict]:
#         return {
#             "channels": {
#                 k: {
#                     "delay": v.delay,
#                     "width": v.width,
#                     "polarity": v.polarity,
#                     "enabled": v.enabled,
#                 }
#                 for k, v in self.channels.items()
#             },
#             "trigger": {
#                 "source": self.trigger.source,
#                 "enabled": self.trigger.enabled,
#                 "level": self.trigger.level,
#                 "slope": self.trigger.slope,
#             },
#         }


# class BNC575Controller:
#     """
#     Write-only controller for the BNC575.
#     - No reads/queries are performed (device is unreliable).
#     - Public API remains compatible with existing GUI calls.
#     - All getters return cached model values.
#     """

#     def __init__(self) -> None:
#         self.ser: serial.Serial | None = None
#         self.model = BNC575Model()

#     # ------------------------------------------------------------------
#     # Connection / teardown
#     # ------------------------------------------------------------------
#     def connect(self, port: str, baudrate: int = 115200) -> None:
#         """Open the serial port and apply a safe default configuration."""
#         if self.ser and self.ser.is_open:
#             self.ser.close()

#         self.ser = serial.Serial(
#             port=port,
#             baudrate=baudrate,
#             timeout=0.2,
#             write_timeout=0.2,
#         )
#         time.sleep(0.2)

#         if self.ser:
#             self.ser.reset_input_buffer()
#             self.ser.reset_output_buffer()

#         # Default model values (matches GUI defaults)
#         self.model.channels["CHA"].width = 1e-6
#         self.model.channels["CHA"].delay = 0.0
#         self.model.channels["CHB"].width = 1e-6
#         self.model.channels["CHB"].delay = 0.0
#         self.model.channels["CHC"].width = 40e-6
#         self.model.channels["CHC"].delay = 0.0
#         self.model.channels["CHD"].width = 40e-6
#         self.model.channels["CHD"].delay = 0.0
#         self.model.trigger.source = "EXT"
#         self.model.trigger.enabled = False
#         self.model.trigger.level = 3.0
#         self.model.trigger.slope = "POS"

#         # Apply a clean reset and commit defaults
#         self._write_scpi("*RST")
#         self._write_scpi(":ABOR")
#         self._initialize_engine()
#         self.commit_all_channels()
#         self._arm_trigger_state()

#     def close(self) -> None:
#         if self.ser and self.ser.is_open:
#             self.ser.close()
#             self.ser = None

#     # ------------------------------------------------------------------
#     # Public API (compatibility)
#     # ------------------------------------------------------------------
#     def identify(self) -> str:
#         """Return a cached identifier (no device read)."""
#         return "BNC575 (write-only mode)"

#     def apply_settings(
#         self,
#         wA: float,
#         dA: float,
#         wB: float,
#         dB: float,
#         wC: float,
#         dC: float,
#         wD: float,
#         dD: float,
#     ) -> None:
#         """Apply widths/delays for channels A–D, updating model then committing."""
#         self.model.set_width("CHA", wA)
#         self.model.set_delay("CHA", dA)
#         self.model.set_width("CHB", wB)
#         self.model.set_delay("CHB", dB)
#         self.model.set_width("CHC", wC)
#         self.model.set_delay("CHC", dC)
#         self.model.set_width("CHD", wD)
#         self.model.set_delay("CHD", dD)

#         self.commit_all_channels()

#     def read_settings(self) -> Tuple[float, float, float, float, float, float, float, float]:
#         """Return cached model settings (no instrument read)."""
#         c = self.model.channels
#         return (
#             c["CHA"].width,
#             c["CHA"].delay,
#             c["CHB"].width,
#             c["CHB"].delay,
#             c["CHC"].width,
#             c["CHC"].delay,
#             c["CHD"].width,
#             c["CHD"].delay,
#         )

#     def arm_external_trigger(self, level: float = 3.0, slope: str = "RIS") -> bool:
#         """Configure and arm for external trigger (cached + write-only)."""
#         self.set_trigger_settings(source="EXT", slope=slope, level=level)
#         return self.arm_trigger()

#     def fire_internal(self) -> None:
#         """Software trigger (no readback)."""
#         # Ensure trigger engine is in a runnable state and ON
#         self._arm_trigger_state()
#         self._write_scpi("*TRG")

#     def arm_trigger(self) -> bool:
#         """Enable trigger using cached settings (no GUI read)."""
#         self.model.set_trigger_mode("TRIG")
#         self.model.set_trigger_output(True)
#         self._arm_trigger_state()
#         return True

#     def disarm_trigger(self) -> bool:
#         """Disable trigger (stops waiting)."""
#         self.model.set_trigger_output(False)
#         self._arm_trigger_state()
#         return True

#     def enable_trigger(self, enabled: bool = True) -> bool:
#         """
#         Explicit enable/disable trigger. Enabling arms with current settings;
#         disabling turns trigger off.
#         """
#         self.model.set_trigger_output(enabled)
#         if enabled and self.model.trigger.mode == "DIS":
#             self.model.set_trigger_mode("TRIG")
#         self._arm_trigger_state()
#         return True

#     # ------------------------------------------------------------------
#     # Trigger helpers
#     # ------------------------------------------------------------------
#     def set_trigger_output(self, channel: str, state: bool) -> None:
#         # Alias to enable_output for compatibility
#         self.enable_output(channel, state)

#     def set_trigger_source(self, source: str) -> None:
#         self.model.set_trigger_source(source)
#         self._arm_trigger_state()

#     def set_trigger_settings(self, source: str = "EXT", slope: str = "RIS", level: float = 2.50) -> bool:
#         """
#         Apply trigger edge/level and cache source.
#         Firmware often ignores explicit source selection; we still cache it.
#         """
#         source = source.upper()
#         slope = slope.upper()

#         if slope not in ("RIS", "FALL"):
#             raise ValueError("Slope must be RIS or FALL")
#         if source not in ("EXT", "INT"):
#             raise ValueError("Source must be EXT or INT")

#         self.model.set_trigger_source(source)
#         self.model.set_trigger_slope("POS" if slope == "RIS" else "NEG")
#         self.model.set_trigger_level(level)
#         self.model.set_trigger_mode("TRIG")

#         self._write_scpi(":ABOR")
#         self._write_scpi(f":PULSE0:TRIG:EDGE {slope}")
#         self._write_scpi(f":PULSE0:TRIG:LEV {level:.3f}")
#         # Mode selection handled in _arm_trigger_state
#         return True

#     # ------------------------------------------------------------------
#     # Channel helpers
#     # ------------------------------------------------------------------
#     def set_delay(self, channel: str, value: float) -> None:
#         self.model.set_delay(channel, value)
#         self.commit_settings(channel)

#     def set_width(self, channel: str, value: float) -> None:
#         self.model.set_width(channel, value)
#         self.commit_settings(channel)

#     def set_polarity(self, channel: str, polarity: str) -> None:
#         p = polarity.upper()
#         if p not in ("POS", "NEG"):
#             raise ValueError("Polarity must be POS or NEG")
#         self.model.set_polarity(channel, p)
#         self.commit_settings(channel)

#     def enable_output(self, channel: str, enabled: bool) -> None:
#         self.model.set_enabled(channel, enabled)
#         self.commit_settings(channel)

#     # ------------------------------------------------------------------
#     # Commit logic
#     # ------------------------------------------------------------------
#     def commit_settings(self, channel: str) -> None:
#         ch_id = self._channel_to_number(channel)
#         st = self.model.channels[channel.upper()]
#         self._write_scpi(f":PULSE{ch_id}:MODE NORM")
#         self._write_scpi(f":PULSE{ch_id}:STATE {'ON' if st.enabled else 'OFF'}")
#         self._write_scpi(f":PULSE{ch_id}:POL {'NORM' if st.polarity == 'POS' else 'INVT'}")
#         self._write_scpi(f":PULSE{ch_id}:WIDT {st.width:.6E}")
#         self._write_scpi(f":PULSE{ch_id}:DEL {st.delay:.6E}")
#         self._write_scpi(f":PULSE{ch_id}:SYNC T0")

#     def commit_all_channels(self) -> None:
#         for ch in ["CHA", "CHB", "CHC", "CHD"]:
#             self.commit_settings(ch)

#     # ------------------------------------------------------------------
#     # Internal helpers
#     # ------------------------------------------------------------------
#     def _initialize_engine(self) -> None:
#         """Set up master timing engine in a known state."""
#         self._write_scpi(":PULSE0:TRIG:MODE DIS")
#         self._write_scpi(":PULSE0:MODE SING")

#     def _arm_trigger_state(self) -> None:
#         """Apply trigger settings from the model."""
#         trig = self.model.trigger
#         mode = trig.mode if trig.enabled else "DIS"
#         self._write_scpi(f":PULSE0:TRIG:MODE {mode}")
#         self._write_scpi(f":PULSE0:TRIG:LEV {trig.level:.3f}")
#         self._write_scpi(f":PULSE0:TRIG:EDGE {'RIS' if trig.slope == 'POS' else 'FALL'}")
#         self._write_scpi(f":PULSE0:MODE SING")
#         self._write_scpi(":PULSE0:STATE ON")

#     def _channel_to_number(self, channel: str) -> int:
#         mapping = {"CHA": 1, "CHB": 2, "CHC": 3, "CHD": 4}
#         key = channel.upper()
#         if key not in mapping:
#             raise ValueError(f"Unknown channel: {channel}")
#         return mapping[key]

#     def _write_scpi(self, cmd: str, retries: int = 3, delay_s: float = 0.015) -> None:
#         """
#         Robust, write-only SCPI sender.
#         - Flush buffers
#         - Write with newline
#         - Sleep briefly
#         - Retry on serial errors
#         """
#         if not self.ser or not self.ser.is_open:
#             raise RuntimeError("BNC575 serial not open")

#         for attempt in range(retries):
#             try:
#                 self.ser.reset_input_buffer()
#                 self.ser.reset_output_buffer()
#                 self.ser.write((cmd + "\n").encode("ascii"))
#                 self.ser.flush()
#                 time.sleep(delay_s)
#                 return
#             except serial.SerialException:
#                 if attempt == retries - 1:
#                     raise
#                 time.sleep(0.05)

#     # ------------------------------------------------------------------
#     # Disabled query (no reads)
#     # ------------------------------------------------------------------
#     def query(self, cmd: str) -> str:
#         return ""
"""
BNC 575 Series Digital Delay/Pulse Generator Driver
Based on BNC 575 Series Operating Manual Version 5.6
Validated against actual hardware probe results

Firmware: 2.4.2-2.0.11 (as reported by *IDN?)

WORKING COMMANDS (from probe):
- :PULSE<n>:DEL, :PULSE<n>:WIDT, :PULSE<n>:POL, :PULSE<n>:STATE
- :PULSE0:TRIG:LEV, :PULSE0:TRIG:EDGE, :PULSE0:MODE
- :PULSE0:PER (period)
- *TRG, *IDN?, *RST, *SAV, *RCL

NOT WORKING on this firmware:
- :PULSE0:TRIG:SOUR (use :PULSE0:TRIG:MODE instead)
- :SYST:ERR? (not implemented)
- Channel name style (CHA:, CHB:)
"""

import serial
import time
from typing import Optional, Tuple, List, Dict, Any
from enum import Enum


class SystemMode(Enum):
    """System T0 modes - from manual page 8-38"""
    CONTINUOUS = "NORM"    # Normal - continuous
    SINGLE = "SING"        # Single shot
    BURST = "BURS"         # Burst mode  
    DUTY_CYCLE = "DCYC"    # Duty cycle


class TriggerMode(Enum):
    """Trigger modes - from manual page 8-38"""
    DISABLED = "DIS"       # Internal only
    TRIGGERED = "TRIG"     # External trigger enabled
    DUAL = "DUAL"          # Dual trigger (requires DT15 option)


class TriggerEdge(Enum):
    """Trigger edge - from manual page 8-38"""
    RISING = "RIS"
    FALLING = "FALL"


class GateMode(Enum):
    """Gate modes - from manual page 8-38"""
    DISABLED = "DIS"
    PULSE_INHIBIT = "PULS"
    OUTPUT_INHIBIT = "OUTP"
    CHANNEL = "CHAN"       # Per-channel control


class GateLogic(Enum):
    """Gate logic level"""
    LOW = "LOW"
    HIGH = "HIGH"


class ChannelMode(Enum):
    """Channel modes - from manual page 8-39"""
    NORMAL = "NORM"
    SINGLE = "SING"
    BURST = "BURS"
    DUTY_CYCLE = "DCYC"


class Polarity(Enum):
    """Output polarity - from manual page 8-39"""
    NORMAL = "NORM"        # Active high
    COMPLEMENT = "COMP"    # Active low
    INVERTED = "INV"       # Alias for complement


class OutputMode(Enum):
    """Output type - from manual page 8-39"""
    TTL = "TTL"
    ADJUSTABLE = "ADJ"


class ClockSource(Enum):
    """Clock source - from manual page 8-38"""
    SYSTEM = "SYS"
    EXT_10MHZ = "EXT10"
    EXT_20MHZ = "EXT20"
    EXT_25MHZ = "EXT25"
    EXT_40MHZ = "EXT40"
    EXT_50MHZ = "EXT50"
    EXT_80MHZ = "EXT80"
    EXT_100MHZ = "EXT100"


class BNC575Controller:
    """
    Controller for BNC 575 Series Digital Delay/Pulse Generator
    
    Based on manual SCPI command reference (pages 8-37 to 8-41)
    and validated against actual hardware.
    
    Usage:
        bnc = BNC575Controller()
        bnc.connect("COM5")
        
        # Configure channels
        bnc.set_channel_delay(1, 10e-6)   # Channel A, 10 µs delay
        bnc.set_channel_width(1, 1e-6)    # Channel A, 1 µs width
        bnc.set_channel_state(1, True)    # Enable channel A
        
        # Set period and run
        bnc.set_period(1e-3)              # 1 ms period (1 kHz)
        bnc.set_system_mode(SystemMode.CONTINUOUS)
        bnc.run()
    """
    
    TERMINATOR = "\n"
    TIMEOUT = 1.0
    CMD_DELAY = 0.05  # 50ms between commands (was 20ms)
    
    # Channel mapping: index -> channel number
    # 0 = T0 (system), 1 = A, 2 = B, 3 = C, 4 = D, 5 = E, 6 = F, 7 = G, 8 = H
    CHANNEL_MAP = {
        'T0': 0, 'A': 1, 'B': 2, 'C': 3, 'D': 4,
        'E': 5, 'F': 6, 'G': 7, 'H': 8,
        'CHA': 1, 'CHB': 2, 'CHC': 3, 'CHD': 4,
        'CHE': 5, 'CHF': 6, 'CHG': 7, 'CHH': 8,
    }
    
    def __init__(self, port: str = None, baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self.serial: Optional[serial.Serial] = None
        self._connected = False
        self._num_channels = 4  # Will detect on connect
        self._firmware_version = ""
    
    # ==================== CONNECTION ====================
    
    def connect(self, port: str = None, baudrate: int = None) -> bool:
        """Connect to BNC575"""
        if port:
            self.port = port
        if baudrate:
            self.baudrate = baudrate
        
        if not self.port:
            raise ValueError("No port specified")
        
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.TIMEOUT
            )
            time.sleep(0.5)
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()
            
            # Test connection and get info
            idn = self.identify()
            if idn:
                self._connected = True
                self._parse_idn(idn)
                return True
            else:
                # Even if no IDN response, try to proceed if port opened
                self._connected = True
                return True
                
        except Exception as e:
            self._connected = False
            if self.serial:
                self.serial.close()
            raise ConnectionError(f"Failed to connect: {e}")
    
    def _parse_idn(self, idn: str):
        """Parse IDN response: BNC,575-4,31707,2.4.2-2.0.11"""
        try:
            parts = idn.split(',')
            if len(parts) >= 2:
                model = parts[1]  # e.g., "575-4"
                if '-' in model:
                    num_ch = int(model.split('-')[1])
                    self._num_channels = num_ch
            if len(parts) >= 4:
                self._firmware_version = parts[3]
        except:
            pass
    
    def close(self):
        """Disconnect"""
        if self.serial and self.serial.is_open:
            try:
                self.serial.close()
            except:
                pass
        self._connected = False
    
    def is_connected(self) -> bool:
        return self._connected and self.serial and self.serial.is_open
    
    # ==================== LOW-LEVEL COMMUNICATION ====================
    
    def _write_raw(self, command: str):
        """Write command without reading response"""
        if not self.is_connected():
            raise ConnectionError("Not connected")
        self.serial.reset_input_buffer()
        self.serial.write((command + self.TERMINATOR).encode('ascii'))
        self.serial.flush()
        time.sleep(self.CMD_DELAY)
    
    def _read_response(self) -> str:
        """Read response until terminator or timeout"""
        response = ""
        start = time.time()
        while (time.time() - start) < self.TIMEOUT:
            if self.serial.in_waiting > 0:
                chunk = self.serial.read(self.serial.in_waiting)
                response += chunk.decode('ascii', errors='ignore')
                if '\n' in response or '\r' in response:
                    break
            time.sleep(0.005)
        return response.strip()
    
    def _command(self, cmd: str) -> bool:
        """Send command, expect 'ok' response"""
        self._write_raw(cmd)
        resp = self._read_response()
        if resp.lower() == "ok":
            return True
        elif resp.startswith("?"):
            # Error code
            return False
        return True  # Some commands may not respond
    
    def _query(self, cmd: str) -> str:
        """Send query, return response"""
        self._write_raw(cmd)
        return self._read_response()
    
    # ==================== IDENTIFICATION ====================
    
    def identify(self) -> str:
        """Get instrument ID (*IDN?)"""
        try:
            return self._query("*IDN?")
        except:
            return ""
    
    def reset(self) -> bool:
        """Reset to defaults (*RST)"""
        return self._command("*RST")
    
    def get_firmware_version(self) -> str:
        """Get firmware version from last IDN"""
        return self._firmware_version
    
    def get_num_channels(self) -> int:
        """Get number of channels (2, 4, or 8)"""
        return self._num_channels
    
    # ==================== SYSTEM CONTROL ====================
    
    def run(self) -> bool:
        """Start pulse generation (like pressing RUN)"""
        return self._command(":PULSE0:STATE ON")
    
    def stop(self) -> bool:
        """Stop pulse generation"""
        return self._command(":PULSE0:STATE OFF")
    
    def is_running(self) -> bool:
        """Check if running"""
        resp = self._query(":PULSE0:STATE?")
        return resp in ("1", "ON")
    
    def trigger(self) -> bool:
        """Software trigger (*TRG)"""
        return self._command("*TRG")
    
    # ==================== SYSTEM MODE (T0) ====================
    
    def set_system_mode(self, mode: SystemMode) -> bool:
        """Set system mode: NORM, SING, BURS, DCYC"""
        return self._command(f":PULSE0:MODE {mode.value}")
    
    def get_system_mode(self) -> Optional[SystemMode]:
        """Get current system mode"""
        resp = self._query(":PULSE0:MODE?")
        for m in SystemMode:
            if resp.upper().startswith(m.value):
                return m
        return None
    
    def set_period(self, period: float) -> bool:
        """Set T0 period in seconds (100ns to 5000s)"""
        return self._command(f":PULSE0:PER {period:.11e}")
    
    def get_period(self) -> float:
        """Get T0 period in seconds"""
        resp = self._query(":PULSE0:PER?")
        try:
            return float(resp)
        except:
            return 0.001
    
    def set_frequency(self, freq: float) -> bool:
        """Set frequency in Hz (convenience method)"""
        if freq > 0:
            return self.set_period(1.0 / freq)
        return False
    
    def get_frequency(self) -> float:
        """Get frequency in Hz"""
        p = self.get_period()
        return 1.0 / p if p > 0 else 0
    
    def set_burst_count(self, count: int) -> bool:
        """Set burst count (1 to 9,999,999)"""
        return self._command(f":PULSE0:BCOU {count}")
    
    def get_burst_count(self) -> int:
        """Get burst count"""
        resp = self._query(":PULSE0:BCOU?")
        try:
            return int(resp)
        except:
            return 1
    
    def set_duty_cycle(self, on_count: int, off_count: int) -> bool:
        """Set duty cycle on/off counts"""
        r1 = self._command(f":PULSE0:PCOU {on_count}")
        r2 = self._command(f":PULSE0:OCOU {off_count}")
        return r1 and r2
    
    # ==================== CLOCK SOURCE ====================
    
    def set_clock_source(self, source: ClockSource) -> bool:
        """Set internal clock source"""
        return self._command(f":PULSE0:ICL {source.value}")
    
    def set_clock_output(self, divider: int) -> bool:
        """Set clock output (T0 or divided: 10, 11, 12, 14, 16, 20, 25, 33, 50, 100)"""
        return self._command(f":PULSE0:OCL {divider}")
    
    # ==================== TRIGGER ====================
    
    def set_trigger_mode(self, mode: TriggerMode) -> bool:
        """Set trigger mode: DIS, TRIG, DUAL"""
        return self._command(f":PULSE0:TRIG:MODE {mode.value}")
    
    def get_trigger_mode(self) -> Optional[TriggerMode]:
        """Get trigger mode"""
        resp = self._query(":PULSE0:TRIG:MODE?")
        for m in TriggerMode:
            if resp.upper().startswith(m.value):
                return m
        return None
    
    def set_trigger_level(self, level: float) -> bool:
        """Set trigger level (0.20V to 15V)"""
        level = max(0.20, min(15.0, level))
        return self._command(f":PULSE0:TRIG:LEV {level:.3f}")
    
    def get_trigger_level(self) -> float:
        """Get trigger level"""
        resp = self._query(":PULSE0:TRIG:LEV?")
        try:
            return float(resp)
        except:
            return 2.5
    
    def set_trigger_edge(self, edge: TriggerEdge) -> bool:
        """Set trigger edge: RIS or FALL"""
        return self._command(f":PULSE0:TRIG:LOG {edge.value}")
    
    def get_trigger_edge(self) -> Optional[TriggerEdge]:
        """Get trigger edge"""
        resp = self._query(":PULSE0:TRIG:LOG?")
        for e in TriggerEdge:
            if resp.upper().startswith(e.value):
                return e
        return None
    
    # ==================== GATE ====================
    
    def set_gate_mode(self, mode: GateMode) -> bool:
        """Set gate mode"""
        return self._command(f":PULSE0:GATE:MODE {mode.value}")
    
    def set_gate_level(self, level: float) -> bool:
        """Set gate level (0.20V to 15V)"""
        level = max(0.20, min(15.0, level))
        return self._command(f":PULSE0:GATE:LEV {level:.3f}")
    
    def set_gate_logic(self, logic: GateLogic) -> bool:
        """Set gate logic: LOW or HIGH"""
        return self._command(f":PULSE0:GATE:LOG {logic.value}")
    
    # ==================== CHANNEL CONFIGURATION ====================
    
    def _resolve_channel(self, channel) -> int:
        """Convert channel name/number to PULSE index"""
        if isinstance(channel, int):
            return channel
        if isinstance(channel, str):
            return self.CHANNEL_MAP.get(channel.upper(), 1)
        return 1
    
    def set_channel_state(self, channel, enabled: bool) -> bool:
        """Enable/disable channel"""
        ch = self._resolve_channel(channel)
        state = "ON" if enabled else "OFF"
        return self._command(f":PULSE{ch}:STATE {state}")
    
    def get_channel_state(self, channel) -> bool:
        """Get channel enabled state"""
        ch = self._resolve_channel(channel)
        resp = self._query(f":PULSE{ch}:STATE?")
        return resp in ("1", "ON")
    
    def set_channel_width(self, channel, width: float) -> bool:
        """Set channel width in seconds (10ns to 999.999s)"""
        ch = self._resolve_channel(channel)
        return self._command(f":PULSE{ch}:WIDT {width:.11e}")
    
    def get_channel_width(self, channel) -> float:
        """Get channel width in seconds"""
        ch = self._resolve_channel(channel)
        resp = self._query(f":PULSE{ch}:WIDT?")
        try:
            return float(resp)
        except:
            return 1e-6
    
    def set_channel_delay(self, channel, delay: float) -> bool:
        """Set channel delay in seconds (-999.999s to 999.999s)"""
        ch = self._resolve_channel(channel)
        return self._command(f":PULSE{ch}:DEL {delay:.11e}")
    
    def get_channel_delay(self, channel) -> float:
        """Get channel delay in seconds"""
        ch = self._resolve_channel(channel)
        resp = self._query(f":PULSE{ch}:DEL?")
        try:
            return float(resp)
        except:
            return 0.0
    
    def set_channel_polarity(self, channel, polarity: Polarity) -> bool:
        """Set channel polarity"""
        ch = self._resolve_channel(channel)
        return self._command(f":PULSE{ch}:POL {polarity.value}")
    
    def get_channel_polarity(self, channel) -> Optional[Polarity]:
        """Get channel polarity"""
        ch = self._resolve_channel(channel)
        resp = self._query(f":PULSE{ch}:POL?")
        for p in Polarity:
            if resp.upper().startswith(p.value):
                return p
        return None
    
    def set_channel_sync(self, channel, sync_source: str) -> bool:
        """Set channel sync source (T0, CHA, CHB, etc.)"""
        ch = self._resolve_channel(channel)
        return self._command(f":PULSE{ch}:SYNC {sync_source}")
    
    def get_channel_sync(self, channel) -> str:
        """Get channel sync source"""
        ch = self._resolve_channel(channel)
        return self._query(f":PULSE{ch}:SYNC?")
    
    def set_channel_output_mode(self, channel, mode: OutputMode) -> bool:
        """Set output mode (TTL or ADJ)"""
        ch = self._resolve_channel(channel)
        return self._command(f":PULSE{ch}:OUTP:MODE {mode.value}")
    
    def set_channel_amplitude(self, channel, amplitude: float) -> bool:
        """Set output amplitude in V (for adjustable mode)"""
        ch = self._resolve_channel(channel)
        return self._command(f":PULSE{ch}:OUTP:AMP {amplitude:.3f}")
    
    def get_channel_amplitude(self, channel) -> float:
        """Get output amplitude"""
        ch = self._resolve_channel(channel)
        resp = self._query(f":PULSE{ch}:OUTP:AMP?")
        try:
            return float(resp)
        except:
            return 4.0
    
    def set_channel_mode(self, channel, mode: ChannelMode) -> bool:
        """Set channel mode"""
        ch = self._resolve_channel(channel)
        return self._command(f":PULSE{ch}:CMOD {mode.value}")
    
    def set_channel_burst_count(self, channel, count: int) -> bool:
        """Set channel burst count"""
        ch = self._resolve_channel(channel)
        return self._command(f":PULSE{ch}:BCOU {count}")
    
    def set_channel_duty_cycle(self, channel, on: int, off: int) -> bool:
        """Set channel duty cycle counts"""
        ch = self._resolve_channel(channel)
        r1 = self._command(f":PULSE{ch}:PCOU {on}")
        r2 = self._command(f":PULSE{ch}:OCOU {off}")
        return r1 and r2
    
    def set_channel_wait(self, channel, count: int) -> bool:
        """Set channel wait count (T0 pulses before enabling)"""
        ch = self._resolve_channel(channel)
        return self._command(f":PULSE{ch}:WCOU {count}")
    
    def set_channel_mux(self, channel, mux_bits: int) -> bool:
        """Set channel multiplexer (bit field)"""
        ch = self._resolve_channel(channel)
        return self._command(f":PULSE{ch}:MUX {mux_bits}")
    
    def set_channel_gate(self, channel, mode: GateMode) -> bool:
        """Set channel-specific gate mode"""
        ch = self._resolve_channel(channel)
        return self._command(f":PULSE{ch}:CGAT {mode.value}")
    
    def set_channel_gate_logic(self, channel, logic: GateLogic) -> bool:
        """Set channel gate logic"""
        ch = self._resolve_channel(channel)
        return self._command(f":PULSE{ch}:CLOG {logic.value}")
    
    # ==================== COUNTER ====================
    
    def set_counter_state(self, enabled: bool) -> bool:
        """Enable/disable counter"""
        state = "ON" if enabled else "OFF"
        return self._command(f":PULSE0:COUN:STAT {state}")
    
    def clear_counter(self, counter: str = "TCNTS") -> bool:
        """Clear counter (TCNTS or GCNTS)"""
        return self._command(f":PULSE0:COUN:CLE {counter}")
    
    def get_counter(self, counter: str = "TCNTS") -> int:
        """Get counter value"""
        resp = self._query(f":PULSE0:COUN:COUN? {counter}")
        try:
            return int(resp)
        except:
            return 0
    
    # ==================== STORE/RECALL ====================
    
    def store_config(self, location: int, label: str = "") -> bool:
        """Store config to memory (1-12)"""
        if not 1 <= location <= 12:
            return False
        if label:
            self._command(f'*LBL "{label[:14]}"')
        return self._command(f"*SAV {location}")
    
    def recall_config(self, location: int) -> bool:
        """Recall config from memory (0-12, 0=factory)"""
        if not 0 <= location <= 12:
            return False
        return self._command(f"*RCL {location}")
    
    def recall_defaults(self) -> bool:
        """Recall factory defaults"""
        return self.recall_config(0)
    
    # ==================== DISPLAY ====================
    
    def set_display_mode(self, auto_update: bool) -> bool:
        """Set display auto-update"""
        state = "ON" if auto_update else "OFF"
        return self._command(f":DISP:MODE {state}")
    
    def set_display_brightness(self, level: int) -> bool:
        """Set display brightness (0-4)"""
        level = max(0, min(4, level))
        return self._command(f":DISP:BRIG {level}")
    
    def set_display_enable(self, enabled: bool) -> bool:
        """Enable/disable display"""
        state = "ON" if enabled else "OFF"
        return self._command(f":DISP:ENAB {state}")
    
    # ==================== SYSTEM ====================
    
    def set_keylock(self, locked: bool) -> bool:
        """Lock/unlock front panel"""
        state = "ON" if locked else "OFF"
        return self._command(f":SYST:KLOC {state}")
    
    def set_beeper(self, enabled: bool) -> bool:
        """Enable/disable beeper"""
        state = "ON" if enabled else "OFF"
        return self._command(f":SYST:BEEP:STAT {state}")
    
    def set_autorun(self, enabled: bool) -> bool:
        """Set auto-run on power-up"""
        state = "ON" if enabled else "OFF"
        return self._command(f":SYST:AUT {state}")
    
    # ==================== INSTRUMENT SELECTION ====================
    
    def select_channel(self, channel) -> bool:
        """Select channel for subsequent commands"""
        ch = self._resolve_channel(channel)
        names = {0: "T0", 1: "CHA", 2: "CHB", 3: "CHC", 4: "CHD",
                 5: "CHE", 6: "CHF", 7: "CHG", 8: "CHH"}
        return self._command(f":INST:SEL {names.get(ch, 'CHA')}")
    
    def get_channel_catalog(self) -> str:
        """Get list of available channels"""
        return self._query(":INST:CAT?")
    
    # ==================== CONVENIENCE METHODS FOR MAIN_WINDOW.PY ====================
    
    def apply_settings(self, wA: float, dA: float, wB: float, dB: float,
                       wC: float, dC: float, wD: float, dD: float) -> bool:
        """Apply width/delay for channels A-D (main_window.py compatible)"""
        success = True
        success &= self.set_channel_delay(1, dA)
        success &= self.set_channel_width(1, wA)
        success &= self.set_channel_delay(2, dB)
        success &= self.set_channel_width(2, wB)
        success &= self.set_channel_delay(3, dC)
        success &= self.set_channel_width(3, wC)
        success &= self.set_channel_delay(4, dD)
        success &= self.set_channel_width(4, wD)
        return success
    
    def read_settings(self) -> Tuple[float, float, float, float, float, float, float, float]:
        """Read width/delay for channels A-D (main_window.py compatible)"""
        wA = self.get_channel_width(1)
        dA = self.get_channel_delay(1)
        wB = self.get_channel_width(2)
        dB = self.get_channel_delay(2)
        wC = self.get_channel_width(3)
        dC = self.get_channel_delay(3)
        wD = self.get_channel_width(4)
        dD = self.get_channel_delay(4)
        return (wA, dA, wB, dB, wC, dC, wD, dD)
    
    def fire_internal(self) -> bool:
        """Fire single internal pulse"""
        self.set_system_mode(SystemMode.SINGLE)
        time.sleep(0.01)
        return self.run()
    
    def arm_trigger(self) -> bool:
        """Arm for external trigger"""
        self.set_trigger_mode(TriggerMode.TRIGGERED)
        return self.run()
    
    def arm_external_trigger(self, level: float = 2.5) -> bool:
        """Arm for external trigger with level"""
        self.set_trigger_mode(TriggerMode.TRIGGERED)
        self.set_trigger_level(level)
        self.set_trigger_edge(TriggerEdge.RISING)
        return self.run()
    
    def disarm_trigger(self) -> bool:
        """Disarm trigger"""
        self.stop()
        return self.set_trigger_mode(TriggerMode.DISABLED)
    
    def enable_trigger(self, enabled: bool) -> bool:
        """Enable/disable external trigger mode"""
        mode = TriggerMode.TRIGGERED if enabled else TriggerMode.DISABLED
        return self.set_trigger_mode(mode)
    
    def enable_output(self, channel: str, enabled: bool) -> bool:
        """Enable/disable channel (accepts 'CHA', 'CHB', 'A', 'B', etc.)"""
        return self.set_channel_state(channel, enabled)
    
    def set_trigger_settings(self, source: str, slope: str, level: float) -> bool:
        """Configure trigger (main_window.py compatible)"""
        # Source: INT or EXT
        if source.upper() in ("EXT", "EXTERNAL", "TRIG"):
            self.set_trigger_mode(TriggerMode.TRIGGERED)
        else:
            self.set_trigger_mode(TriggerMode.DISABLED)
        
        # Slope: POS or NEG
        rising = slope.upper() in ("POS", "POSITIVE", "RIS", "RISING")
        self.set_trigger_edge(TriggerEdge.RISING if rising else TriggerEdge.FALLING)
        
        # Level
        self.set_trigger_level(level)
        return True
    
    def configure_pulse(self, channel, delay: float, width: float,
                        polarity: Polarity = Polarity.NORMAL, enabled: bool = True) -> bool:
        """Configure complete pulse"""
        ch = self._resolve_channel(channel)
        success = True
        success &= self.set_channel_delay(ch, delay)
        success &= self.set_channel_width(ch, width)
        success &= self.set_channel_polarity(ch, polarity)
        success &= self.set_channel_state(ch, enabled)
        return success
    
    def configure_continuous(self, frequency: float) -> bool:
        """Configure continuous mode at frequency"""
        self.set_system_mode(SystemMode.CONTINUOUS)
        self.set_trigger_mode(TriggerMode.DISABLED)
        return self.set_frequency(frequency)
    
    def configure_burst(self, count: int, frequency: float) -> bool:
        """Configure burst mode"""
        self.set_system_mode(SystemMode.BURST)
        self.set_burst_count(count)
        return self.set_frequency(frequency)


# Test if run directly
if __name__ == "__main__":
    print("BNC575 Controller Test")
    print("=" * 40)
    
    bnc = BNC575Controller()
    try:
        bnc.connect("COM5")
        print(f"Connected: {bnc.identify()}")
        print(f"Channels: {bnc.get_num_channels()}")
        print(f"Period: {bnc.get_period()}")
        print(f"Mode: {bnc.get_system_mode()}")
        
        # Test channel read
        for ch in [1, 2, 3, 4]:
            w = bnc.get_channel_width(ch)
            d = bnc.get_channel_delay(ch)
            print(f"Ch {ch}: width={w:.3e}, delay={d:.3e}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        bnc.close()
