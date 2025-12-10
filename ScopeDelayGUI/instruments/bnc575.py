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

This driver implements the complete SCPI command set for the BNC 575 series
pulse generator, supporting RS232, USB, GPIB, and Ethernet interfaces.

Features:
- 2, 4, or 8 independent output channels (model dependent)
- 250 ps delay and width resolution
- 0.0002 Hz to 20 MHz internal rate
- Multiple trigger modes: Internal, External, Single Shot, Burst, Duty Cycle
- Channel linking and multiplexing
- Store/Recall for 12 user configurations
- Counter function for trigger counting

Communication:
- RS232: 4800-115200 baud (default 115200)
- USB: Virtual COM port (default 38400 baud)
- GPIB: Address 1-15 (optional)
- Ethernet: TCP/IP via Digi module (optional)

Author: Generated based on BNC 575 Manual
"""

import serial
import time
from enum import Enum, IntEnum
from dataclasses import dataclass, field
from typing import Optional, Union, List, Dict, Tuple


class TriggerMode(Enum):
    """System trigger modes"""
    DISABLED = "DIS"
    TRIGGERED = "TRIG"
    DUAL = "DUAL"  # Requires DT15 option


class SystemMode(Enum):
    """System T0 modes"""
    NORMAL = "NORM"       # Continuous
    SINGLE = "SING"       # Single shot
    BURST = "BURS"        # Burst mode
    DCYCLE = "DCYC"       # Duty cycle
    BURST_INC = "BINC"    # Burst increment (requires option)
    DC_INC = "DINC"       # DC increment (requires option)


class ChannelMode(Enum):
    """Individual channel modes"""
    NORMAL = "NORM"
    SINGLE = "SING"
    BURST = "BURS"
    DCYCLE = "DCYC"


class OutputMode(Enum):
    """Output type modes"""
    TTL = "TTL"
    ADJUSTABLE = "ADJ"


class Polarity(Enum):
    """Output polarity"""
    NORMAL = "NORM"       # Active high
    COMPLEMENT = "COMP"   # Active low (inverted)
    INVERTED = "INV"      # Alias for complement


class GateMode(Enum):
    """Gate input modes"""
    DISABLED = "DIS"
    PULSE_INHIBIT = "PULS"
    OUTPUT_INHIBIT = "OUTP"
    CHANNEL = "CHAN"      # Per-channel control


class GateLogic(Enum):
    """Gate logic level"""
    LOW = "LOW"           # Active low
    HIGH = "HIGH"         # Active high


class TriggerEdge(Enum):
    """Trigger edge selection"""
    RISING = "RIS"
    FALLING = "FALL"


class ClockSource(Enum):
    """Internal clock source"""
    SYSTEM = "SYS"
    EXT_10MHZ = "EXT10"
    EXT_20MHZ = "EXT20"
    EXT_25MHZ = "EXT25"
    EXT_40MHZ = "EXT40"
    EXT_50MHZ = "EXT50"
    EXT_80MHZ = "EXT80"
    EXT_100MHZ = "EXT100"


class RefOutput(Enum):
    """Reference output frequencies"""
    T0_PULSE = "T0"
    MHZ_100 = "100"
    MHZ_50 = "50"
    MHZ_33 = "33"
    MHZ_25 = "25"
    MHZ_20 = "20"
    MHZ_16 = "16"
    MHZ_14 = "14"
    MHZ_12 = "12"
    MHZ_11 = "11"
    MHZ_10 = "10"


class Channel(IntEnum):
    """Channel indices"""
    T0 = 0
    A = 1
    B = 2
    C = 3
    D = 4
    E = 5
    F = 6
    G = 7
    H = 8


@dataclass
class ChannelConfig:
    """Configuration for a single channel"""
    enabled: bool = False
    width: float = 10e-9          # Pulse width in seconds (10ns - 999.999s)
    delay: float = 0.0            # Delay in seconds (0 - 999.999s)
    sync_source: str = "T0"       # Sync source (T0, CHA, CHB, etc.)
    mode: ChannelMode = ChannelMode.NORMAL
    polarity: Polarity = Polarity.NORMAL
    output_mode: OutputMode = OutputMode.TTL
    amplitude: float = 4.0        # For adjustable mode (2-20V into 1k, 1-10V into 50Ω)
    burst_count: int = 1          # Pulses in burst mode
    on_count: int = 1             # On pulses in duty cycle mode
    off_count: int = 1            # Off pulses in duty cycle mode
    wait_count: int = 0           # T0 pulses to wait before enabling
    mux: int = 0                  # Multiplexer bit field
    gate_mode: GateMode = GateMode.DISABLED
    gate_logic: GateLogic = GateLogic.HIGH


@dataclass
class TriggerConfig:
    """Trigger configuration"""
    mode: TriggerMode = TriggerMode.DISABLED
    edge: TriggerEdge = TriggerEdge.RISING
    level: float = 2.5            # 0.20V - 15V


@dataclass
class GateConfig:
    """Gate configuration"""
    mode: GateMode = GateMode.DISABLED
    logic: GateLogic = GateLogic.HIGH
    level: float = 2.5            # 0.20V - 15V


@dataclass
class SystemConfig:
    """System-level configuration"""
    mode: SystemMode = SystemMode.NORMAL
    period: float = 0.001         # T0 period in seconds (50ns - 5000s)
    burst_count: int = 1          # Pulses in burst mode
    on_count: int = 1             # On pulses in duty cycle mode
    off_count: int = 1            # Off pulses in duty cycle mode
    clock_source: ClockSource = ClockSource.SYSTEM
    ref_output: RefOutput = RefOutput.T0_PULSE


@dataclass
class BNC575State:
    """Complete instrument state"""
    running: bool = False
    system: SystemConfig = field(default_factory=SystemConfig)
    trigger: TriggerConfig = field(default_factory=TriggerConfig)
    gate: GateConfig = field(default_factory=GateConfig)
    channels: Dict[Channel, ChannelConfig] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.channels:
            # Initialize channels A-H (model may have 2, 4, or 8)
            for ch in [Channel.A, Channel.B, Channel.C, Channel.D,
                      Channel.E, Channel.F, Channel.G, Channel.H]:
                self.channels[ch] = ChannelConfig()


class BNC575Controller:
    """
    Controller for BNC 575 Series Digital Delay/Pulse Generator
    
    Supports communication via:
    - RS232 serial port
    - USB (virtual COM port)
    - GPIB (with Prologix adapter or native interface)
    - Ethernet (optional COM module)
    
    Example usage:
        # RS232/USB connection
        bnc = BNC575Controller(port='COM3', baudrate=115200)
        bnc.connect()
        
        # Configure channel A
        bnc.set_channel_width(Channel.A, 1e-6)    # 1 µs pulse
        bnc.set_channel_delay(Channel.A, 10e-6)  # 10 µs delay
        bnc.set_channel_state(Channel.A, True)
        
        # Set period and run
        bnc.set_period(0.001)  # 1 ms period = 1 kHz
        bnc.run()
        
        bnc.disconnect()
    """
    
    # Line termination
    TERMINATOR = "\r\n"
    
    # Response timeout
    TIMEOUT = 1.0
    
    # Command delay (some units need time between commands)
    CMD_DELAY = 0.01
    
    def __init__(self, port: str = 'COM1', baudrate: int = 115200,
                 gpib_address: Optional[int] = None,
                 use_prologix: bool = False):
        """
        Initialize BNC575 controller
        
        Args:
            port: Serial port name (e.g., 'COM3', '/dev/ttyUSB0')
            baudrate: Baud rate (4800, 9600, 19200, 38400, 57600, 115200)
            gpib_address: GPIB address if using GPIB interface
            use_prologix: True if using Prologix GPIB-USB adapter
        """
        self.port = port
        self.baudrate = baudrate
        self.gpib_address = gpib_address
        self.use_prologix = use_prologix
        self.serial: Optional[serial.Serial] = None
        self.state = BNC575State()
        self._connected = False
        self._num_channels = 8  # Will be detected on connect
        
    def connect(self) -> bool:
        """
        Connect to the BNC575
        
        Returns:
            True if connection successful
        """
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.TIMEOUT
            )
            time.sleep(0.5)  # Allow connection to stabilize
            
            # Configure Prologix if used
            if self.use_prologix and self.gpib_address is not None:
                self._setup_prologix()
            
            # Clear input buffer
            self.serial.reset_input_buffer()
            
            # Test connection by querying ID
            idn = self.get_identification()
            if idn:
                self._connected = True
                # Detect number of channels
                self._detect_channels()
                return True
            return False
            
        except Exception as e:
            print(f"Connection error: {e}")
            return False
    
    def _setup_prologix(self):
        """Configure Prologix GPIB-USB adapter"""
        # Set to controller mode
        self._write_raw("++mode 1")
        time.sleep(0.05)
        # Set GPIB address
        self._write_raw(f"++addr {self.gpib_address}")
        time.sleep(0.05)
        # Auto-read after write
        self._write_raw("++auto 1")
        time.sleep(0.05)
        # Set EOI assertion
        self._write_raw("++eoi 1")
        time.sleep(0.05)
    
    def _detect_channels(self):
        """Detect number of available channels"""
        try:
            catalog = self.query(":INST:CAT?")
            if catalog:
                channels = catalog.split(',')
                # Count channels (excluding T0)
                self._num_channels = len([c for c in channels if c.strip().startswith('CH')])
        except:
            self._num_channels = 8  # Default to 8
    
    def disconnect(self):
        """Disconnect from the BNC575"""
        if self.serial and self.serial.is_open:
            self.serial.close()
        self._connected = False
    
    def is_connected(self) -> bool:
        """Check if connected"""
        return self._connected and self.serial and self.serial.is_open
    
    def _write_raw(self, command: str):
        """Write raw command without processing"""
        if self.serial and self.serial.is_open:
            self.serial.write((command + self.TERMINATOR).encode())
            time.sleep(self.CMD_DELAY)
    
    def write(self, command: str) -> bool:
        """
        Send command to the BNC575
        
        Args:
            command: SCPI command string
            
        Returns:
            True if command acknowledged
        """
        if not self.is_connected():
            return False
        
        try:
            self._write_raw(command)
            # Read response (BNC575 responds to every command)
            response = self._read_response()
            return response.lower().strip() == "ok"
        except Exception as e:
            print(f"Write error: {e}")
            return False
    
    def query(self, command: str) -> Optional[str]:
        """
        Send query and return response
        
        Args:
            command: SCPI query string (should end with ?)
            
        Returns:
            Response string or None on error
        """
        if not self.is_connected():
            return None
        
        try:
            self._write_raw(command)
            return self._read_response()
        except Exception as e:
            print(f"Query error: {e}")
            return None
    
    def _read_response(self) -> str:
        """Read response from instrument"""
        response = ""
        while True:
            char = self.serial.read(1)
            if not char:
                break
            response += char.decode('ascii', errors='ignore')
            if response.endswith('\r\n') or response.endswith('\n'):
                break
        return response.strip()
    
    # ========== Identification Commands ==========
    
    def get_identification(self) -> Optional[str]:
        """Query instrument identification (*IDN?)"""
        return self.query("*IDN?")
    
    def reset(self) -> bool:
        """Reset instrument to default state (*RST)"""
        return self.write("*RST")
    
    # ========== System Control ==========
    
    def run(self) -> bool:
        """Start pulse generation (equivalent to RUN/STOP button)"""
        result = self.write(":PULSE0:STATE ON")
        if result:
            self.state.running = True
        return result
    
    def stop(self) -> bool:
        """Stop pulse generation"""
        result = self.write(":PULSE0:STATE OFF")
        if result:
            self.state.running = False
        return result
    
    def is_running(self) -> bool:
        """Check if instrument is generating pulses"""
        response = self.query(":SYST:STAT?")
        if response:
            return response.strip() == "1"
        return False
    
    def trigger(self) -> bool:
        """Generate software trigger (*TRG)"""
        return self.write("*TRG")
    
    def arm(self) -> bool:
        """Arm single shot/burst channels (*ARM)"""
        return self.write("*ARM")
    
    # ========== System Mode Configuration ==========
    
    def set_system_mode(self, mode: SystemMode) -> bool:
        """Set system T0 mode"""
        result = self.write(f":PULSE0:MODE {mode.value}")
        if result:
            self.state.system.mode = mode
        return result
    
    def get_system_mode(self) -> Optional[SystemMode]:
        """Get current system mode"""
        response = self.query(":PULSE0:MODE?")
        if response:
            for mode in SystemMode:
                if response.strip().upper().startswith(mode.value):
                    return mode
        return None
    
    def set_period(self, period: float) -> bool:
        """
        Set T0 period (determines fundamental output frequency)
        
        Args:
            period: Period in seconds (100ns to 5000s)
        """
        result = self.write(f":PULSE0:PER {period:.11f}")
        if result:
            self.state.system.period = period
        return result
    
    def get_period(self) -> Optional[float]:
        """Get T0 period in seconds"""
        response = self.query(":PULSE0:PER?")
        if response:
            try:
                return float(response.strip())
            except ValueError:
                pass
        return None
    
    def set_frequency(self, frequency: float) -> bool:
        """
        Set output frequency (convenience method)
        
        Args:
            frequency: Frequency in Hz (0.0002 Hz to 20 MHz)
        """
        if frequency > 0:
            return self.set_period(1.0 / frequency)
        return False
    
    def get_frequency(self) -> Optional[float]:
        """Get output frequency in Hz"""
        period = self.get_period()
        if period and period > 0:
            return 1.0 / period
        return None
    
    def set_burst_count(self, count: int) -> bool:
        """Set system burst count (1 to 9,999,999)"""
        result = self.write(f":PULSE0:BCOU {count}")
        if result:
            self.state.system.burst_count = count
        return result
    
    def set_duty_cycle_counts(self, on_count: int, off_count: int) -> bool:
        """Set system duty cycle on/off counts"""
        result1 = self.write(f":PULSE0:PCOU {on_count}")
        result2 = self.write(f":PULSE0:OCOU {off_count}")
        if result1 and result2:
            self.state.system.on_count = on_count
            self.state.system.off_count = off_count
        return result1 and result2
    
    # ========== Clock/Rate Configuration ==========
    
    def set_clock_source(self, source: ClockSource) -> bool:
        """Set internal clock source"""
        result = self.write(f":PULSE0:ICL {source.value}")
        if result:
            self.state.system.clock_source = source
        return result
    
    def set_ref_output(self, ref: RefOutput) -> bool:
        """Set reference output frequency"""
        result = self.write(f":PULSE0:OCL {ref.value}")
        if result:
            self.state.system.ref_output = ref
        return result
    
    # ========== Trigger Configuration ==========
    
    def set_trigger_mode(self, mode: TriggerMode) -> bool:
        """Set trigger mode (Disabled, Triggered, or Dual)"""
        result = self.write(f":PULSE0:TRIG:MODE {mode.value}")
        if result:
            self.state.trigger.mode = mode
        return result
    
    def set_trigger_edge(self, edge: TriggerEdge) -> bool:
        """Set trigger edge (Rising or Falling)"""
        result = self.write(f":PULSE0:TRIG:LOG {edge.value}")
        if result:
            self.state.trigger.edge = edge
        return result
    
    def set_trigger_level(self, level: float) -> bool:
        """Set trigger threshold level (0.20V to 15V)"""
        level = max(0.20, min(15.0, level))
        result = self.write(f":PULSE0:TRIG:LEV {level:.3f}")
        if result:
            self.state.trigger.level = level
        return result
    
    def get_trigger_level(self) -> Optional[float]:
        """Get trigger threshold level"""
        response = self.query(":PULSE0:TRIG:LEV?")
        if response:
            try:
                return float(response.strip())
            except ValueError:
                pass
        return None
    
    # ========== Gate Configuration ==========
    
    def set_gate_mode(self, mode: GateMode) -> bool:
        """Set global gate mode"""
        result = self.write(f":PULSE0:GATE:MODE {mode.value}")
        if result:
            self.state.gate.mode = mode
        return result
    
    def set_gate_logic(self, logic: GateLogic) -> bool:
        """Set gate logic level"""
        result = self.write(f":PULSE0:GATE:LOG {logic.value}")
        if result:
            self.state.gate.logic = logic
        return result
    
    def set_gate_level(self, level: float) -> bool:
        """Set gate threshold level (0.20V to 15V)"""
        level = max(0.20, min(15.0, level))
        result = self.write(f":PULSE0:GATE:LEV {level:.3f}")
        if result:
            self.state.gate.level = level
        return result
    
    # ========== Channel Configuration ==========
    
    def set_channel_state(self, channel: Channel, enabled: bool) -> bool:
        """Enable or disable a channel"""
        state = "ON" if enabled else "OFF"
        result = self.write(f":PULSE{channel.value}:STATE {state}")
        if result and channel in self.state.channels:
            self.state.channels[channel].enabled = enabled
        return result
    
    def get_channel_state(self, channel: Channel) -> Optional[bool]:
        """Get channel enabled state"""
        response = self.query(f":PULSE{channel.value}:STATE?")
        if response:
            return response.strip() == "1" or response.strip().upper() == "ON"
        return None
    
    def set_channel_width(self, channel: Channel, width: float) -> bool:
        """
        Set channel pulse width
        
        Args:
            channel: Channel (A-H)
            width: Width in seconds (10ns to 999.999s)
        """
        result = self.write(f":PULSE{channel.value}:WIDT {width:.11f}")
        if result and channel in self.state.channels:
            self.state.channels[channel].width = width
        return result
    
    def get_channel_width(self, channel: Channel) -> Optional[float]:
        """Get channel pulse width in seconds"""
        response = self.query(f":PULSE{channel.value}:WIDT?")
        if response:
            try:
                return float(response.strip())
            except ValueError:
                pass
        return None
    
    def set_channel_delay(self, channel: Channel, delay: float) -> bool:
        """
        Set channel delay
        
        Args:
            channel: Channel (A-H)
            delay: Delay in seconds (0 to 999.999s, can be negative for channel sync)
        """
        result = self.write(f":PULSE{channel.value}:DEL {delay:.11f}")
        if result and channel in self.state.channels:
            self.state.channels[channel].delay = delay
        return result
    
    def get_channel_delay(self, channel: Channel) -> Optional[float]:
        """Get channel delay in seconds"""
        response = self.query(f":PULSE{channel.value}:DEL?")
        if response:
            try:
                return float(response.strip())
            except ValueError:
                pass
        return None
    
    def set_channel_sync(self, channel: Channel, sync_source: str) -> bool:
        """
        Set channel sync source
        
        Args:
            channel: Channel to configure
            sync_source: Sync source ("T0", "CHA", "CHB", etc.)
        """
        result = self.write(f":PULSE{channel.value}:SYNC {sync_source}")
        if result and channel in self.state.channels:
            self.state.channels[channel].sync_source = sync_source
        return result
    
    def set_channel_polarity(self, channel: Channel, polarity: Polarity) -> bool:
        """Set channel output polarity"""
        result = self.write(f":PULSE{channel.value}:POL {polarity.value}")
        if result and channel in self.state.channels:
            self.state.channels[channel].polarity = polarity
        return result
    
    def set_channel_output_mode(self, channel: Channel, mode: OutputMode) -> bool:
        """Set channel output mode (TTL or Adjustable)"""
        result = self.write(f":PULSE{channel.value}:OUTP:MODE {mode.value}")
        if result and channel in self.state.channels:
            self.state.channels[channel].output_mode = mode
        return result
    
    def set_channel_amplitude(self, channel: Channel, amplitude: float) -> bool:
        """
        Set channel output amplitude (for adjustable mode)
        
        Args:
            channel: Channel
            amplitude: Amplitude in volts (2-20V into 1kΩ, 1-10V into 50Ω)
        """
        amplitude = max(2.0, min(20.0, amplitude))
        result = self.write(f":PULSE{channel.value}:OUTP:AMP {amplitude:.3f}")
        if result and channel in self.state.channels:
            self.state.channels[channel].amplitude = amplitude
        return result
    
    def set_channel_mode(self, channel: Channel, mode: ChannelMode) -> bool:
        """Set channel operating mode"""
        result = self.write(f":PULSE{channel.value}:CMOD {mode.value}")
        if result and channel in self.state.channels:
            self.state.channels[channel].mode = mode
        return result
    
    def set_channel_burst_count(self, channel: Channel, count: int) -> bool:
        """Set channel burst count"""
        result = self.write(f":PULSE{channel.value}:BCOU {count}")
        if result and channel in self.state.channels:
            self.state.channels[channel].burst_count = count
        return result
    
    def set_channel_duty_cycle(self, channel: Channel, on_count: int, off_count: int) -> bool:
        """Set channel duty cycle on/off counts"""
        result1 = self.write(f":PULSE{channel.value}:PCOU {on_count}")
        result2 = self.write(f":PULSE{channel.value}:OCOU {off_count}")
        if result1 and result2 and channel in self.state.channels:
            self.state.channels[channel].on_count = on_count
            self.state.channels[channel].off_count = off_count
        return result1 and result2
    
    def set_channel_wait(self, channel: Channel, wait_count: int) -> bool:
        """Set channel wait count (T0 pulses to wait before enabling)"""
        result = self.write(f":PULSE{channel.value}:WCOU {wait_count}")
        if result and channel in self.state.channels:
            self.state.channels[channel].wait_count = wait_count
        return result
    
    def set_channel_mux(self, channel: Channel, mux_bits: int) -> bool:
        """
        Set channel multiplexer
        
        Args:
            channel: Output channel
            mux_bits: Bit field selecting which timers to combine
                      (bit 0 = ChA, bit 1 = ChB, etc.)
        """
        result = self.write(f":PULSE{channel.value}:MUX {mux_bits}")
        if result and channel in self.state.channels:
            self.state.channels[channel].mux = mux_bits
        return result
    
    def set_channel_gate(self, channel: Channel, mode: GateMode, logic: GateLogic = GateLogic.HIGH) -> bool:
        """Set channel-specific gate control (requires global gate mode = CHANNEL)"""
        result1 = self.write(f":PULSE{channel.value}:CGAT {mode.value}")
        result2 = self.write(f":PULSE{channel.value}:CLOG {logic.value}")
        if result1 and result2 and channel in self.state.channels:
            self.state.channels[channel].gate_mode = mode
            self.state.channels[channel].gate_logic = logic
        return result1 and result2
    
    # ========== Counter Function ==========
    
    def set_counter_state(self, enabled: bool) -> bool:
        """Enable or disable counter function"""
        state = "ON" if enabled else "OFF"
        return self.write(f":PULSE0:COUN:STAT {state}")
    
    def clear_counter(self, counter: str = "TCNTS") -> bool:
        """Clear counter (TCNTS for trigger counter, GCNTS for gate counter)"""
        return self.write(f":PULSE0:COUN:CLE {counter}")
    
    def get_counter(self, counter: str = "TCNTS") -> Optional[int]:
        """Get counter value"""
        response = self.query(f":PULSE0:COUN:COUN? {counter}")
        if response:
            try:
                return int(response.strip())
            except ValueError:
                pass
        return None
    
    # ========== Store/Recall ==========
    
    def store_config(self, location: int, label: str = "") -> bool:
        """
        Store current configuration to memory
        
        Args:
            location: Memory location (1-12, 0 is factory default)
            label: Optional label (max 14 characters)
        """
        if location < 1 or location > 12:
            return False
        if label:
            self.write(f'*LBL "{label[:14]}"')
        return self.write(f"*SAV {location}")
    
    def recall_config(self, location: int) -> bool:
        """
        Recall configuration from memory
        
        Args:
            location: Memory location (0-12, 0 is factory default)
        """
        if location < 0 or location > 12:
            return False
        return self.write(f"*RCL {location}")
    
    def recall_defaults(self) -> bool:
        """Recall factory default configuration"""
        return self.recall_config(0)
    
    def get_config_label(self) -> Optional[str]:
        """Get label of last saved/recalled configuration"""
        return self.query("*LBL?")
    
    # ========== Display Control ==========
    
    def set_display_mode(self, auto_update: bool) -> bool:
        """Set display auto-update mode"""
        state = "ON" if auto_update else "OFF"
        return self.write(f":DISP:MODE {state}")
    
    def update_display(self) -> bool:
        """Force display update"""
        return self.write(":DISP:UPD")
    
    def set_display_brightness(self, level: int) -> bool:
        """Set display brightness (0-4, where 0 is off)"""
        level = max(0, min(4, level))
        return self.write(f":DISP:BRIG {level}")
    
    def set_display_enable(self, enabled: bool) -> bool:
        """Enable or disable display and front panel"""
        state = "ON" if enabled else "OFF"
        return self.write(f":DISP:ENAB {state}")
    
    # ========== System Configuration ==========
    
    def set_keylock(self, locked: bool) -> bool:
        """Lock or unlock front panel keypad"""
        state = "ON" if locked else "OFF"
        return self.write(f":SYST:KLOC {state}")
    
    def set_beeper(self, enabled: bool) -> bool:
        """Enable or disable beeper"""
        state = "ON" if enabled else "OFF"
        return self.write(f":SYST:BEEP:STAT {state}")
    
    def set_beeper_volume(self, volume: int) -> bool:
        """Set beeper volume (0-100)"""
        volume = max(0, min(100, volume))
        return self.write(f":SYST:BEEP:VOL {volume}")
    
    def set_autorun(self, enabled: bool) -> bool:
        """Set auto-run on power-up"""
        state = "ON" if enabled else "OFF"
        return self.write(f":SYST:AUT {state}")
    
    def get_serial_number(self) -> Optional[str]:
        """Get instrument serial number"""
        return self.query(":SYST:SERN?")
    
    def get_version(self) -> Optional[str]:
        """Get SCPI version"""
        return self.query(":SYST:VERS?")
    
    def get_info(self) -> Optional[str]:
        """Get instrument information"""
        return self.query(":SYST:INF?")
    
    # ========== Instrument Selection (for multi-channel queries) ==========
    
    def select_channel(self, channel: Channel) -> bool:
        """Select channel for subsequent commands without suffix"""
        return self.write(f":INST:SEL {channel.name if channel != Channel.T0 else 'T0'}")
    
    def select_channel_by_number(self, number: int) -> bool:
        """Select channel by numeric value"""
        return self.write(f":INST:NSEL {number}")
    
    def get_channel_catalog(self) -> Optional[str]:
        """Get list of available channels"""
        return self.query(":INST:CAT?")
    
    def get_commands(self) -> Optional[str]:
        """Get list of all SCPI commands"""
        return self.query(":INST:COMM?")
    
    # ========== Convenience Methods ==========
    
    def configure_pulse(self, channel: Channel, delay: float, width: float,
                       polarity: Polarity = Polarity.NORMAL,
                       enabled: bool = True) -> bool:
        """
        Configure a complete pulse in one call
        
        Args:
            channel: Channel to configure
            delay: Delay in seconds
            width: Pulse width in seconds
            polarity: Output polarity
            enabled: Enable channel after configuration
        """
        results = [
            self.set_channel_delay(channel, delay),
            self.set_channel_width(channel, width),
            self.set_channel_polarity(channel, polarity),
            self.set_channel_state(channel, enabled)
        ]
        return all(results)
    
    def configure_continuous(self, frequency: float) -> bool:
        """Configure for continuous mode at given frequency"""
        results = [
            self.set_system_mode(SystemMode.NORMAL),
            self.set_trigger_mode(TriggerMode.DISABLED),
            self.set_frequency(frequency)
        ]
        return all(results)
    
    def configure_external_trigger(self, level: float = 2.5,
                                   edge: TriggerEdge = TriggerEdge.RISING,
                                   single_shot: bool = True) -> bool:
        """Configure for external trigger operation"""
        mode = SystemMode.SINGLE if single_shot else SystemMode.NORMAL
        results = [
            self.set_system_mode(mode),
            self.set_trigger_mode(TriggerMode.TRIGGERED),
            self.set_trigger_level(level),
            self.set_trigger_edge(edge)
        ]
        return all(results)
    
    def configure_burst(self, count: int, frequency: float) -> bool:
        """Configure for burst mode"""
        results = [
            self.set_system_mode(SystemMode.BURST),
            self.set_burst_count(count),
            self.set_frequency(frequency)
        ]
        return all(results)
    
    def read_all_channel_settings(self, channel: Channel) -> Optional[ChannelConfig]:
        """Read all settings for a channel from the instrument"""
        config = ChannelConfig()
        
        state = self.get_channel_state(channel)
        if state is not None:
            config.enabled = state
        
        width = self.get_channel_width(channel)
        if width is not None:
            config.width = width
        
        delay = self.get_channel_delay(channel)
        if delay is not None:
            config.delay = delay
        
        # Update state cache
        if channel in self.state.channels:
            self.state.channels[channel] = config
        
        return config
    
    def sync_state(self):
        """Synchronize internal state with instrument"""
        self.state.running = self.is_running()
        
        # Read system settings
        mode = self.get_system_mode()
        if mode:
            self.state.system.mode = mode
        
        period = self.get_period()
        if period:
            self.state.system.period = period
        
        # Read channel settings
        for ch in Channel:
            if ch == Channel.T0:
                continue
            if ch.value <= self._num_channels:
                self.read_all_channel_settings(ch)


# Example usage and testing
if __name__ == "__main__":
    # Example: Create controller and demonstrate usage
    print("BNC 575 Series Controller")
    print("=" * 50)
    
    # Simulated usage (would need actual hardware to test)
    print("\nExample usage:")
    print("""
    # Connect to BNC575 via USB
    bnc = BNC575Controller(port='COM3', baudrate=38400)
    bnc.connect()
    
    # Get instrument info
    print(bnc.get_identification())
    
    # Configure for 1 kHz continuous operation
    bnc.configure_continuous(frequency=1000)
    
    # Set up Channel A: 10 µs delay, 1 µs pulse
    bnc.configure_pulse(Channel.A, delay=10e-6, width=1e-6)
    
    # Set up Channel B: 20 µs delay, 2 µs pulse
    bnc.configure_pulse(Channel.B, delay=20e-6, width=2e-6)
    
    # Start pulses
    bnc.run()
    
    # Stop after some time
    time.sleep(5)
    bnc.stop()
    
    # Store configuration
    bnc.store_config(1, "My Config")
    
    # Disconnect
    bnc.disconnect()
    """)
        