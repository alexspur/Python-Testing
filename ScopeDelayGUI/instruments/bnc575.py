import time
from dataclasses import dataclass, field
from typing import Dict, Tuple

import serial

# Static capability map (no device queries)
capabilities: Dict[str, Dict[str, bool]] = {
    "CHA": {"delay": True, "width": True, "polarity": True},
    "CHB": {"delay": True, "width": True, "polarity": True},
    "CHC": {"delay": True, "width": True, "polarity": True},
    "CHD": {"delay": True, "width": True, "polarity": True},
    "T0": {"trigger": True, "source_select": True},
}


@dataclass
class ChannelState:
    delay: float = 0.0
    width: float = 1e-6
    polarity: str = "POS"  # POS or NEG
    enabled: bool = True


@dataclass
class TriggerState:
    source: str = "EXT"  # EXT, INT (cached only)
    enabled: bool = False
    level: float = 3.0
    slope: str = "POS"  # POS / NEG
    mode: str = "TRIG"  # TRIG, DUAL, DIS


@dataclass
class BNC575Model:
    channels: Dict[str, ChannelState] = field(default_factory=dict)
    trigger: TriggerState = field(default_factory=TriggerState)

    def __post_init__(self) -> None:
        for name in ["CHA", "CHB", "CHC", "CHD"]:
            self.channels.setdefault(name, ChannelState())

    # Channel setters
    def set_delay(self, channel: str, value: float) -> None:
        self.channels[channel].delay = value

    def set_width(self, channel: str, value: float) -> None:
        self.channels[channel].width = value

    def set_polarity(self, channel: str, value: str) -> None:
        self.channels[channel].polarity = value.upper()

    def set_enabled(self, channel: str, enabled: bool) -> None:
        self.channels[channel].enabled = enabled

    # Trigger setters
    def set_trigger_source(self, source: str) -> None:
        self.trigger.source = source.upper()

    def set_trigger_output(self, enabled: bool) -> None:
        self.trigger.enabled = enabled

    def set_trigger_level(self, level: float) -> None:
        self.trigger.level = level

    def set_trigger_slope(self, slope: str) -> None:
        self.trigger.slope = slope.upper()

    def set_trigger_mode(self, mode: str) -> None:
        self.trigger.mode = mode.upper()

    def snapshot(self) -> Dict[str, Dict]:
        return {
            "channels": {
                k: {
                    "delay": v.delay,
                    "width": v.width,
                    "polarity": v.polarity,
                    "enabled": v.enabled,
                }
                for k, v in self.channels.items()
            },
            "trigger": {
                "source": self.trigger.source,
                "enabled": self.trigger.enabled,
                "level": self.trigger.level,
                "slope": self.trigger.slope,
            },
        }


class BNC575Controller:
    """
    Write-only controller for the BNC575.
    - No reads/queries are performed (device is unreliable).
    - Public API remains compatible with existing GUI calls.
    - All getters return cached model values.
    """

    def __init__(self) -> None:
        self.ser: serial.Serial | None = None
        self.model = BNC575Model()

    # ------------------------------------------------------------------
    # Connection / teardown
    # ------------------------------------------------------------------
    def connect(self, port: str, baudrate: int = 115200) -> None:
        """Open the serial port and apply a safe default configuration."""
        if self.ser and self.ser.is_open:
            self.ser.close()

        self.ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=0.2,
            write_timeout=0.2,
        )
        time.sleep(0.2)

        if self.ser:
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()

        # Default model values (matches GUI defaults)
        self.model.channels["CHA"].width = 1e-6
        self.model.channels["CHA"].delay = 0.0
        self.model.channels["CHB"].width = 1e-6
        self.model.channels["CHB"].delay = 0.0
        self.model.channels["CHC"].width = 40e-6
        self.model.channels["CHC"].delay = 0.0
        self.model.channels["CHD"].width = 40e-6
        self.model.channels["CHD"].delay = 0.0
        self.model.trigger.source = "EXT"
        self.model.trigger.enabled = False
        self.model.trigger.level = 3.0
        self.model.trigger.slope = "POS"

        # Apply a clean reset and commit defaults
        self._write_scpi("*RST")
        self._write_scpi(":ABOR")
        self._initialize_engine()
        self.commit_all_channels()
        self._arm_trigger_state()

    def close(self) -> None:
        if self.ser and self.ser.is_open:
            self.ser.close()
            self.ser = None

    # ------------------------------------------------------------------
    # Public API (compatibility)
    # ------------------------------------------------------------------
    def identify(self) -> str:
        """Return a cached identifier (no device read)."""
        return "BNC575 (write-only mode)"

    def apply_settings(
        self,
        wA: float,
        dA: float,
        wB: float,
        dB: float,
        wC: float,
        dC: float,
        wD: float,
        dD: float,
    ) -> None:
        """Apply widths/delays for channels A–D, updating model then committing."""
        self.model.set_width("CHA", wA)
        self.model.set_delay("CHA", dA)
        self.model.set_width("CHB", wB)
        self.model.set_delay("CHB", dB)
        self.model.set_width("CHC", wC)
        self.model.set_delay("CHC", dC)
        self.model.set_width("CHD", wD)
        self.model.set_delay("CHD", dD)

        self.commit_all_channels()

    def read_settings(self) -> Tuple[float, float, float, float, float, float, float, float]:
        """Return cached model settings (no instrument read)."""
        c = self.model.channels
        return (
            c["CHA"].width,
            c["CHA"].delay,
            c["CHB"].width,
            c["CHB"].delay,
            c["CHC"].width,
            c["CHC"].delay,
            c["CHD"].width,
            c["CHD"].delay,
        )

    def arm_external_trigger(self, level: float = 3.0, slope: str = "RIS") -> bool:
        """Configure and arm for external trigger (cached + write-only)."""
        self.set_trigger_settings(source="EXT", slope=slope, level=level)
        return self.arm_trigger()

    def fire_internal(self) -> None:
        """Software trigger (no readback)."""
        # Ensure trigger engine is in a runnable state and ON
        self._arm_trigger_state()
        self._write_scpi("*TRG")

    def arm_trigger(self) -> bool:
        """Enable trigger using cached settings (no GUI read)."""
        self.model.set_trigger_mode("TRIG")
        self.model.set_trigger_output(True)
        self._arm_trigger_state()
        return True

    def disarm_trigger(self) -> bool:
        """Disable trigger (stops waiting)."""
        self.model.set_trigger_output(False)
        self._arm_trigger_state()
        return True

    def enable_trigger(self, enabled: bool = True) -> bool:
        """
        Explicit enable/disable trigger. Enabling arms with current settings;
        disabling turns trigger off.
        """
        self.model.set_trigger_output(enabled)
        if enabled and self.model.trigger.mode == "DIS":
            self.model.set_trigger_mode("TRIG")
        self._arm_trigger_state()
        return True

    # ------------------------------------------------------------------
    # Trigger helpers
    # ------------------------------------------------------------------
    def set_trigger_output(self, channel: str, state: bool) -> None:
        # Alias to enable_output for compatibility
        self.enable_output(channel, state)

    def set_trigger_source(self, source: str) -> None:
        self.model.set_trigger_source(source)
        self._arm_trigger_state()

    def set_trigger_settings(self, source: str = "EXT", slope: str = "RIS", level: float = 2.50) -> bool:
        """
        Apply trigger edge/level and cache source.
        Firmware often ignores explicit source selection; we still cache it.
        """
        source = source.upper()
        slope = slope.upper()

        if slope not in ("RIS", "FALL"):
            raise ValueError("Slope must be RIS or FALL")
        if source not in ("EXT", "INT"):
            raise ValueError("Source must be EXT or INT")

        self.model.set_trigger_source(source)
        self.model.set_trigger_slope("POS" if slope == "RIS" else "NEG")
        self.model.set_trigger_level(level)
        self.model.set_trigger_mode("TRIG")

        self._write_scpi(":ABOR")
        self._write_scpi(f":PULSE0:TRIG:EDGE {slope}")
        self._write_scpi(f":PULSE0:TRIG:LEV {level:.3f}")
        # Mode selection handled in _arm_trigger_state
        return True

    # ------------------------------------------------------------------
    # Channel helpers
    # ------------------------------------------------------------------
    def set_delay(self, channel: str, value: float) -> None:
        self.model.set_delay(channel, value)
        self.commit_settings(channel)

    def set_width(self, channel: str, value: float) -> None:
        self.model.set_width(channel, value)
        self.commit_settings(channel)

    def set_polarity(self, channel: str, polarity: str) -> None:
        p = polarity.upper()
        if p not in ("POS", "NEG"):
            raise ValueError("Polarity must be POS or NEG")
        self.model.set_polarity(channel, p)
        self.commit_settings(channel)

    def enable_output(self, channel: str, enabled: bool) -> None:
        self.model.set_enabled(channel, enabled)
        self.commit_settings(channel)

    # ------------------------------------------------------------------
    # Commit logic
    # ------------------------------------------------------------------
    def commit_settings(self, channel: str) -> None:
        ch_id = self._channel_to_number(channel)
        st = self.model.channels[channel.upper()]
        self._write_scpi(f":PULSE{ch_id}:MODE NORM")
        self._write_scpi(f":PULSE{ch_id}:STATE {'ON' if st.enabled else 'OFF'}")
        self._write_scpi(f":PULSE{ch_id}:POL {'NORM' if st.polarity == 'POS' else 'INVT'}")
        self._write_scpi(f":PULSE{ch_id}:WIDT {st.width:.6E}")
        self._write_scpi(f":PULSE{ch_id}:DEL {st.delay:.6E}")
        self._write_scpi(f":PULSE{ch_id}:SYNC T0")

    def commit_all_channels(self) -> None:
        for ch in ["CHA", "CHB", "CHC", "CHD"]:
            self.commit_settings(ch)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _initialize_engine(self) -> None:
        """Set up master timing engine in a known state."""
        self._write_scpi(":PULSE0:TRIG:MODE DIS")
        self._write_scpi(":PULSE0:MODE SING")

    def _arm_trigger_state(self) -> None:
        """Apply trigger settings from the model."""
        trig = self.model.trigger
        mode = trig.mode if trig.enabled else "DIS"
        self._write_scpi(f":PULSE0:TRIG:MODE {mode}")
        self._write_scpi(f":PULSE0:TRIG:LEV {trig.level:.3f}")
        self._write_scpi(f":PULSE0:TRIG:EDGE {'RIS' if trig.slope == 'POS' else 'FALL'}")
        self._write_scpi(f":PULSE0:MODE SING")
        self._write_scpi(":PULSE0:STATE ON")

    def _channel_to_number(self, channel: str) -> int:
        mapping = {"CHA": 1, "CHB": 2, "CHC": 3, "CHD": 4}
        key = channel.upper()
        if key not in mapping:
            raise ValueError(f"Unknown channel: {channel}")
        return mapping[key]

    def _write_scpi(self, cmd: str, retries: int = 3, delay_s: float = 0.015) -> None:
        """
        Robust, write-only SCPI sender.
        - Flush buffers
        - Write with newline
        - Sleep briefly
        - Retry on serial errors
        """
        if not self.ser or not self.ser.is_open:
            raise RuntimeError("BNC575 serial not open")

        for attempt in range(retries):
            try:
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
                self.ser.write((cmd + "\n").encode("ascii"))
                self.ser.flush()
                time.sleep(delay_s)
                return
            except serial.SerialException:
                if attempt == retries - 1:
                    raise
                time.sleep(0.05)

    # ------------------------------------------------------------------
    # Disabled query (no reads)
    # ------------------------------------------------------------------
    def query(self, cmd: str) -> str:
        return ""
