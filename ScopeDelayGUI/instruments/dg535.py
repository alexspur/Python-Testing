# import time
# import serial

# class DG535Controller:
#     def __init__(self, port="COM4"):
#         self.port = port
#         self.ser = None

#     def connect(self, port=None, baudrate=9600, gpib_addr=15):
#         if port:
#             self.port = port

#         self.ser = serial.Serial(self.port, baudrate, timeout=2)
#         time.sleep(0.5)

#         # Prologix setup
#         self.write("++mode 1")
#         self.write("++auto 0")
#         self.write(f"++addr {gpib_addr}")
#         self.write("++eoi 1")
#         self.write("++eos 1")

#     def write(self, cmd):
#         if not self.ser:
#             raise RuntimeError("DG535 serial not open")
#         self.ser.write((cmd + "\r").encode())
#         time.sleep(0.05)

#     def send_gpib(self, cmd):
#         self.write(cmd)

#     # ==== Restore MATLAB-equivalent functions ====

#     def configure_pulse_A(self, delay_a, width_a):
#         self.send_gpib("C L")
#         time.sleep(0.05)

#         # A = T0 + delay
#         self.send_gpib(f"D T 2 , 1 , {delay_a:.6E}")
#         time.sleep(0.05)

#         # B = A + width
#         self.send_gpib(f"D T 3 , 2 , {delay_a + width_a:.6E}")
#         time.sleep(0.05)

#         # Output A settings
#         self.send_gpib("T Z 2 , 0")
#         self.send_gpib("O M 2 , 0")
#         self.send_gpib("O P 2 , 1")
#         time.sleep(0.1)

#     def set_single_shot(self):
#         self.send_gpib("T M 2")
#         time.sleep(0.1)

#     def fire(self):
#         self.send_gpib("S S")
#         time.sleep(0.05)

#     def close(self):
#         if self.ser:
#             self.ser.close()
#             self.ser = None
# instruments/dg535.py
"""
Stanford Research Systems DG535 Digital Delay/Pulse Generator Driver

Full-featured driver implementing all GPIB commands from the DG535 manual.
Supports all trigger modes, delay channels, output configurations, and store/recall.

Channel Assignments (per manual):
    0 = Trigger Input
    1 = T0 Output
    2 = A Output
    3 = B Output
    4 = AB and -AB Outputs
    5 = C Output
    6 = D Output
    7 = CD and -CD Outputs

Trigger Modes:
    0 = Internal
    1 = External
    2 = Single-Shot
    3 = Burst
    4 = Line (60Hz)

Output Modes:
    0 = TTL
    1 = NIM
    2 = ECL
    3 = VAR (Variable)
"""

import time
import serial
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
from enum import IntEnum


class Channel(IntEnum):
    """DG535 Channel assignments per manual page viii"""
    TRIGGER = 0
    T0 = 1
    A = 2
    B = 3
    AB = 4
    C = 5
    D = 6
    CD = 7


class TriggerMode(IntEnum):
    """Trigger mode codes"""
    INTERNAL = 0
    EXTERNAL = 1
    SINGLE_SHOT = 2
    BURST = 3
    LINE = 4


class OutputMode(IntEnum):
    """Output logic level modes"""
    TTL = 0
    NIM = 1
    ECL = 2
    VAR = 3


class TriggerSlope(IntEnum):
    """Trigger slope settings"""
    FALLING = 0
    RISING = 1


class Polarity(IntEnum):
    """Output polarity"""
    INVERTED = 0
    NORMAL = 1


class Impedance(IntEnum):
    """Load/termination impedance"""
    OHM_50 = 0
    HIGH_Z = 1


@dataclass
class DelayChannel:
    """State for a single delay channel"""
    reference: int = Channel.T0  # Which channel this is linked to
    delay: float = 0.0  # Delay in seconds


@dataclass
class OutputChannel:
    """State for a single output channel"""
    impedance: Impedance = Impedance.HIGH_Z
    mode: OutputMode = OutputMode.TTL
    polarity: Polarity = Polarity.NORMAL
    amplitude: float = 4.0  # For VAR mode, in Volts
    offset: float = 0.0  # For VAR mode, in Volts


@dataclass
class TriggerSettings:
    """Trigger configuration state"""
    mode: TriggerMode = TriggerMode.SINGLE_SHOT
    # Internal mode
    internal_rate: float = 10000.0  # Hz
    # External mode
    threshold: float = 1.0  # Volts
    slope: TriggerSlope = TriggerSlope.RISING
    impedance: Impedance = Impedance.HIGH_Z
    # Burst mode
    burst_rate: float = 10000.0  # Hz
    burst_count: int = 10  # Pulses per burst
    burst_period: int = 20  # Periods between bursts


@dataclass
class DG535State:
    """Complete instrument state"""
    delays: Dict[int, DelayChannel] = field(default_factory=dict)
    outputs: Dict[int, OutputChannel] = field(default_factory=dict)
    trigger: TriggerSettings = field(default_factory=TriggerSettings)

    def __post_init__(self):
        # Initialize delay channels A, B, C, D
        for ch in [Channel.A, Channel.B, Channel.C, Channel.D]:
            if ch not in self.delays:
                self.delays[ch] = DelayChannel()

        # Initialize output channels
        for ch in [Channel.T0, Channel.A, Channel.B, Channel.AB,
                   Channel.C, Channel.D, Channel.CD]:
            if ch not in self.outputs:
                self.outputs[ch] = OutputChannel()


class DG535Controller:
    """
    Full-featured controller for Stanford Research DG535 Digital Delay Generator.

    Communicates via serial port through a Prologix GPIB-USB adapter.
    Implements all commands from the DG535 programming manual.

    Usage:
        dg = DG535Controller()
        dg.connect(port="COM4", gpib_addr=15)

        # Configure trigger
        dg.set_trigger_mode(TriggerMode.INTERNAL)
        dg.set_internal_rate(1000.0)

        # Set delays
        dg.set_delay(Channel.A, Channel.T0, 100e-9)  # A = T0 + 100ns
        dg.set_delay(Channel.B, Channel.A, 1e-6)    # B = A + 1µs (pulse width)

        # Configure outputs
        dg.set_output_mode(Channel.A, OutputMode.TTL)
        dg.set_output_impedance(Channel.A, Impedance.OHM_50)

        # Fire single shot
        dg.set_trigger_mode(TriggerMode.SINGLE_SHOT)
        dg.fire()

        dg.close()
    """

    # Max delay: 999.999,999,999,995 seconds
    MAX_DELAY = 999.999999999995
    MIN_DELAY = 0.0
    DELAY_RESOLUTION = 5e-12  # 5 ps

    def __init__(self, port: str = "COM4"):
        self.port = port
        self.ser: Optional[serial.Serial] = None
        self.gpib_addr = 15
        self.state = DG535State()

    # =========================================================================
    # CONNECTION
    # =========================================================================

    def connect(self, port: Optional[str] = None, baudrate: int = 9600,
                gpib_addr: int = 15, timeout: float = 2.0):
        """
        Connect to DG535 via Prologix GPIB-USB adapter.

        Args:
            port: Serial port (e.g., "COM4" or "/dev/ttyUSB0")
            baudrate: Serial baud rate (default 9600)
            gpib_addr: GPIB address of DG535 (default 15)
            timeout: Serial timeout in seconds
        """
        if port:
            self.port = port
        self.gpib_addr = gpib_addr

        if self.ser and self.ser.is_open:
            self.ser.close()

        self.ser = serial.Serial(
            port=self.port,
            baudrate=baudrate,
            timeout=timeout
        )
        time.sleep(0.5)  # Allow serial to stabilize

        # Configure Prologix adapter
        self._write_raw("++mode 1")      # Controller mode
        self._write_raw("++auto 0")      # No auto-read
        self._write_raw(f"++addr {gpib_addr}")  # Set GPIB address
        self._write_raw("++eoi 1")       # Enable EOI
        self._write_raw("++eos 1")       # LF terminator

        time.sleep(0.2)

    def close(self):
        """Close serial connection."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            self.ser = None

    def is_connected(self) -> bool:
        """Check if serial port is open."""
        return self.ser is not None and self.ser.is_open

    # =========================================================================
    # LOW-LEVEL COMMUNICATION
    # =========================================================================

    def _write_raw(self, cmd: str):
        """Write raw command to serial port."""
        if not self.ser:
            raise RuntimeError("DG535 not connected")
        self.ser.write((cmd + "\r").encode())
        time.sleep(0.05)

    def _send_gpib(self, cmd: str):
        """
        Send GPIB command to DG535.

        Note: Per MATLAB Central discussion, commands require spaces between
        each character for some firmware versions. This implementation uses
        spaced format: "C L" instead of "CL".
        """
        # Insert spaces between characters as some firmware requires it
        spaced_cmd = " ".join(cmd)
        self._write_raw(spaced_cmd)

    def _query_gpib(self, cmd: str) -> str:
        """Send query and read response."""
        self._send_gpib(cmd)
        self._write_raw("++read eoi")
        time.sleep(0.1)

        if self.ser:
            response = self.ser.readline().decode(errors="ignore").strip()
            return response
        return ""

    # =========================================================================
    # INITIALIZATION COMMANDS
    # =========================================================================

    def clear(self):
        """
        Clear instrument (CL command).

        Resets to default settings:
        - Trigger mode: Single-Shot
        - All delays: 0, linked to T0
        - All outputs: High-Z, TTL
        """
        self._send_gpib("CL")
        time.sleep(0.3)
        self.state = DG535State()

    def recall_defaults(self):
        """Recall factory default settings (RC 0)."""
        self._send_gpib("RC 0")
        time.sleep(0.2)
        self.state = DG535State()

    # =========================================================================
    # STATUS COMMANDS
    # =========================================================================

    def get_error_status(self) -> int:
        """
        Get error status byte (ES command).

        Returns:
            Error status byte. Bits:
                7: Always zero
                6: Recalled data corrupt
                5: Delay range error
                4: Delay linkage error
                3: Wrong mode for command
                2: Value outside range
                1: Wrong number of parameters
                0: Unrecognized command
        """
        resp = self._query_gpib("ES")
        try:
            return int(resp)
        except ValueError:
            return 0

    def get_instrument_status(self) -> int:
        """
        Get instrument status byte (IS command).

        Returns:
            Instrument status byte. Bits:
                7: Memory contents corrupted
                6: Service request
                5: Always zero
                4: Trigger rate too high
                3: 80MHz PLL unlocked
                2: Trigger occurred
                1: Busy with timing cycle
                0: Command error detected
        """
        resp = self._query_gpib("IS")
        try:
            return int(resp)
        except ValueError:
            return 0

    def is_busy(self) -> bool:
        """Check if unit is busy with a timing cycle."""
        status = self.get_instrument_status()
        return bool(status & 0x02)

    def has_trigger_occurred(self) -> bool:
        """Check if a trigger has occurred."""
        status = self.get_instrument_status()
        return bool(status & 0x04)

    def is_rate_error(self) -> bool:
        """Check if trigger rate is too high."""
        status = self.get_instrument_status()
        return bool(status & 0x10)

    # =========================================================================
    # TRIGGER COMMANDS
    # =========================================================================

    def set_trigger_mode(self, mode: TriggerMode):
        """
        Set trigger mode (TM command).

        Args:
            mode: TriggerMode enum value
                0 = Internal
                1 = External
                2 = Single-Shot
                3 = Burst
        """
        self._send_gpib(f"TM {int(mode)}")
        self.state.trigger.mode = mode

    def get_trigger_mode(self) -> TriggerMode:
        """Get current trigger mode."""
        resp = self._query_gpib("TM")
        try:
            return TriggerMode(int(resp))
        except (ValueError, KeyError):
            return self.state.trigger.mode

    def set_internal_rate(self, rate_hz: float):
        """
        Set internal trigger rate (TR 0,f command).

        Args:
            rate_hz: Trigger rate in Hz (0.001 to 1,000,000)
        """
        rate_hz = max(0.001, min(1e6, rate_hz))
        self._send_gpib(f"TR 0,{rate_hz:.3f}")
        self.state.trigger.internal_rate = rate_hz

    def get_internal_rate(self) -> float:
        """Get internal trigger rate in Hz."""
        resp = self._query_gpib("TR 0")
        try:
            return float(resp)
        except ValueError:
            return self.state.trigger.internal_rate

    def set_external_threshold(self, volts: float):
        """
        Set external trigger threshold (TL command).

        Args:
            volts: Threshold voltage (-2.56 to +2.56 V)
        """
        volts = max(-2.56, min(2.56, volts))
        self._send_gpib(f"TL {volts:.2f}")
        self.state.trigger.threshold = volts

    def set_external_slope(self, slope: TriggerSlope):
        """
        Set external trigger slope (TS command).

        Args:
            slope: TriggerSlope.FALLING (0) or TriggerSlope.RISING (1)
        """
        self._send_gpib(f"TS {int(slope)}")
        self.state.trigger.slope = slope

    def set_trigger_impedance(self, impedance: Impedance):
        """
        Set external trigger input impedance (TZ 0 command).

        Args:
            impedance: Impedance.OHM_50 or Impedance.HIGH_Z
        """
        self._send_gpib(f"TZ 0,{int(impedance)}")
        self.state.trigger.impedance = impedance

    def set_burst_rate(self, rate_hz: float):
        """Set burst trigger rate (TR 1,f command)."""
        rate_hz = max(0.001, min(1e6, rate_hz))
        self._send_gpib(f"TR 1,{rate_hz:.3f}")
        self.state.trigger.burst_rate = rate_hz

    def set_burst_count(self, count: int):
        """
        Set burst count (BC command).

        Args:
            count: Number of pulses per burst (2 to 32766)
        """
        count = max(2, min(32766, count))
        self._send_gpib(f"BC {count}")
        self.state.trigger.burst_count = count

    def set_burst_period(self, period: int):
        """
        Set burst period (BP command).

        Args:
            period: Number of triggers between burst starts (4 to 32766)
                    Must be > burst_count
        """
        period = max(4, min(32766, period))
        self._send_gpib(f"BP {period}")
        self.state.trigger.burst_period = period

    def fire(self):
        """
        Fire single-shot trigger (SS command).

        Only works when trigger mode is set to Single-Shot (TM 2).
        """
        self._send_gpib("SS")

    def single_shot(self):
        """Alias for fire() - triggers a single timing cycle."""
        self.fire()

    # =========================================================================
    # DELAY COMMANDS
    # =========================================================================

    def set_delay(self, channel: int, reference: int, delay_sec: float):
        """
        Set delay time for a channel (DT command).

        Args:
            channel: Channel to set (2=A, 3=B, 5=C, 6=D)
            reference: Reference channel (1=T0, 2=A, 3=B, 5=C, 6=D)
            delay_sec: Delay in seconds (0 to 999.999999999995)

        Examples:
            set_delay(Channel.A, Channel.T0, 1e-6)  # A = T0 + 1µs
            set_delay(Channel.B, Channel.A, 500e-9) # B = A + 500ns
        """
        delay_sec = max(self.MIN_DELAY, min(self.MAX_DELAY, delay_sec))
        self._send_gpib(f"DT {channel},{reference},{delay_sec:.12E}")

        if channel in self.state.delays:
            self.state.delays[channel].reference = reference
            self.state.delays[channel].delay = delay_sec

    def get_delay(self, channel: int) -> Tuple[int, float]:
        """
        Get delay setting for a channel.

        Returns:
            Tuple of (reference_channel, delay_seconds)
        """
        # Query returns "reference,delay" format
        resp = self._query_gpib(f"DT {channel}")
        try:
            parts = resp.split(",")
            if len(parts) >= 2:
                ref = int(parts[0])
                delay = float(parts[1])
                return ref, delay
        except (ValueError, IndexError):
            pass

        if channel in self.state.delays:
            ch = self.state.delays[channel]
            return ch.reference, ch.delay
        return Channel.T0, 0.0

    def set_delay_A(self, delay_sec: float, reference: int = Channel.T0):
        """Convenience: Set channel A delay."""
        self.set_delay(Channel.A, reference, delay_sec)

    def set_delay_B(self, delay_sec: float, reference: int = Channel.T0):
        """Convenience: Set channel B delay."""
        self.set_delay(Channel.B, reference, delay_sec)

    def set_delay_C(self, delay_sec: float, reference: int = Channel.T0):
        """Convenience: Set channel C delay."""
        self.set_delay(Channel.C, reference, delay_sec)

    def set_delay_D(self, delay_sec: float, reference: int = Channel.T0):
        """Convenience: Set channel D delay."""
        self.set_delay(Channel.D, reference, delay_sec)

    # =========================================================================
    # OUTPUT COMMANDS
    # =========================================================================

    def set_output_impedance(self, channel: int, impedance: Impedance):
        """
        Set output termination impedance (TZ command).

        Args:
            channel: Output channel (1-7)
            impedance: Impedance.OHM_50 or Impedance.HIGH_Z
        """
        self._send_gpib(f"TZ {channel},{int(impedance)}")
        if channel in self.state.outputs:
            self.state.outputs[channel].impedance = impedance

    def get_output_impedance(self, channel: int) -> Impedance:
        """Get output termination impedance."""
        resp = self._query_gpib(f"TZ {channel}")
        try:
            return Impedance(int(resp))
        except (ValueError, KeyError):
            if channel in self.state.outputs:
                return self.state.outputs[channel].impedance
            return Impedance.HIGH_Z

    def set_output_mode(self, channel: int, mode: OutputMode):
        """
        Set output logic level mode (OM command).

        Args:
            channel: Output channel (1-7)
            mode: OutputMode.TTL, NIM, ECL, or VAR
        """
        self._send_gpib(f"OM {channel},{int(mode)}")
        if channel in self.state.outputs:
            self.state.outputs[channel].mode = mode

    def get_output_mode(self, channel: int) -> OutputMode:
        """Get output logic level mode."""
        resp = self._query_gpib(f"OM {channel}")
        try:
            return OutputMode(int(resp))
        except (ValueError, KeyError):
            if channel in self.state.outputs:
                return self.state.outputs[channel].mode
            return OutputMode.TTL

    def set_output_polarity(self, channel: int, polarity: Polarity):
        """
        Set output polarity (OP command).

        Args:
            channel: Output channel (1-7)
            polarity: Polarity.INVERTED or Polarity.NORMAL
        """
        self._send_gpib(f"OP {channel},{int(polarity)}")
        if channel in self.state.outputs:
            self.state.outputs[channel].polarity = polarity

    def get_output_polarity(self, channel: int) -> Polarity:
        """Get output polarity."""
        resp = self._query_gpib(f"OP {channel}")
        try:
            return Polarity(int(resp))
        except (ValueError, KeyError):
            if channel in self.state.outputs:
                return self.state.outputs[channel].polarity
            return Polarity.NORMAL

    def set_output_amplitude(self, channel: int, volts: float):
        """
        Set output amplitude for VAR mode (OA command).

        Args:
            channel: Output channel (1-7)
            volts: Amplitude in volts (±0.1 to ±4.0)
        """
        volts = max(-4.0, min(4.0, volts))
        if abs(volts) < 0.1:
            volts = 0.1 if volts >= 0 else -0.1
        self._send_gpib(f"OA {channel},{volts:.2f}")
        if channel in self.state.outputs:
            self.state.outputs[channel].amplitude = volts

    def set_output_offset(self, channel: int, volts: float):
        """
        Set output offset for VAR mode (OO command).

        Args:
            channel: Output channel (1-7)
            volts: Offset in volts (-3.0 to +4.0)
        """
        volts = max(-3.0, min(4.0, volts))
        self._send_gpib(f"OO {channel},{volts:.2f}")
        if channel in self.state.outputs:
            self.state.outputs[channel].offset = volts

    # =========================================================================
    # STORE/RECALL COMMANDS
    # =========================================================================

    def store_settings(self, location: int):
        """
        Store all settings to memory location (ST command).

        Args:
            location: Storage location (1-9)
        """
        location = max(1, min(9, location))
        self._send_gpib(f"ST {location}")

    def recall_settings(self, location: int):
        """
        Recall settings from memory location (RC command).

        Args:
            location: Storage location (0-9, 0 = factory defaults)
        """
        location = max(0, min(9, location))
        self._send_gpib(f"RC {location}")
        time.sleep(0.2)

    # =========================================================================
    # HIGH-LEVEL CONVENIENCE METHODS
    # =========================================================================

    def configure_pulse_A(self, delay: float, width: float):
        """
        Configure A-B as a pulse output.

        Sets A delay from T0, B delay from A (creating AB pulse).

        Args:
            delay: Pulse start time from T0 (seconds)
            width: Pulse width (seconds)
        """
        self.set_delay(Channel.A, Channel.T0, delay)
        self.set_delay(Channel.B, Channel.A, width)

    def configure_pulse_B(self, delay: float, width: float):
        """Configure C-D as a pulse output (CD pulse)."""
        self.set_delay(Channel.C, Channel.T0, delay)
        self.set_delay(Channel.D, Channel.C, width)

    def set_single_shot(self):
        """Set trigger mode to single-shot."""
        self.set_trigger_mode(TriggerMode.SINGLE_SHOT)

    def set_internal_trigger(self, rate_hz: float = 1000.0):
        """Set to internal trigger mode with specified rate."""
        self.set_trigger_mode(TriggerMode.INTERNAL)
        self.set_internal_rate(rate_hz)

    def set_external_trigger(self, threshold: float = 1.0,
                             slope: TriggerSlope = TriggerSlope.RISING,
                             impedance: Impedance = Impedance.HIGH_Z):
        """Configure external trigger with all settings."""
        self.set_trigger_mode(TriggerMode.EXTERNAL)
        self.set_external_threshold(threshold)
        self.set_external_slope(slope)
        self.set_trigger_impedance(impedance)

    def configure_ttl_output(self, channel: int, load_50ohm: bool = False,
                             inverted: bool = False):
        """Configure an output for TTL levels."""
        self.set_output_mode(channel, OutputMode.TTL)
        self.set_output_impedance(channel,
                                  Impedance.OHM_50 if load_50ohm else Impedance.HIGH_Z)
        self.set_output_polarity(channel,
                                 Polarity.INVERTED if inverted else Polarity.NORMAL)

    def configure_var_output(self, channel: int, amplitude: float,
                             offset: float = 0.0, load_50ohm: bool = False):
        """Configure an output for variable levels."""
        self.set_output_mode(channel, OutputMode.VAR)
        self.set_output_impedance(channel,
                                  Impedance.OHM_50 if load_50ohm else Impedance.HIGH_Z)
        self.set_output_amplitude(channel, amplitude)
        self.set_output_offset(channel, offset)

    def arm_and_fire(self):
        """Set to single-shot mode and fire."""
        self.set_trigger_mode(TriggerMode.SINGLE_SHOT)
        time.sleep(0.1)
        self.fire()

    def get_state_snapshot(self) -> dict:
        """
        Return current state as a dictionary.

        Useful for logging and debugging.
        """
        return {
            "trigger": {
                "mode": self.state.trigger.mode.name,
                "internal_rate": self.state.trigger.internal_rate,
                "threshold": self.state.trigger.threshold,
                "slope": self.state.trigger.slope.name,
                "impedance": self.state.trigger.impedance.name,
            },
            "delays": {
                "A": {
                    "reference": self.state.delays[Channel.A].reference,
                    "delay_s": self.state.delays[Channel.A].delay,
                },
                "B": {
                    "reference": self.state.delays[Channel.B].reference,
                    "delay_s": self.state.delays[Channel.B].delay,
                },
                "C": {
                    "reference": self.state.delays[Channel.C].reference,
                    "delay_s": self.state.delays[Channel.C].delay,
                },
                "D": {
                    "reference": self.state.delays[Channel.D].reference,
                    "delay_s": self.state.delays[Channel.D].delay,
                },
            },
        }
