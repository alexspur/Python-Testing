# instruments/numato_relay.py
"""
Numato 4-Channel USB Relay Module Controller
Controls relays via serial commands over USB (CDC serial port).
"""
import serial
import time


class NumatoRelayController:
    """Controller for Numato 4-channel USB relay module."""

    BAUD_RATE = 19200
    NUM_CHANNELS = 4

    def __init__(self):
        self.ser: serial.Serial | None = None
        self.relay_states = [False] * self.NUM_CHANNELS

    @property
    def is_connected(self) -> bool:
        """Check if connected to relay module."""
        return self.ser is not None and self.ser.is_open

    def connect(self, port: str, baudrate: int = None) -> bool:
        """
        Connect to the Numato relay module.

        Args:
            port: Serial port (e.g., 'COM3' on Windows)
            baudrate: Baud rate (default 19200)

        Returns:
            True if connection successful
        """
        if baudrate is None:
            baudrate = self.BAUD_RATE

        if self.ser and self.ser.is_open:
            self.ser.close()

        try:
            self.ser = serial.Serial(port, baudrate, timeout=1)
            time.sleep(0.1)  # Allow module to initialize
            self.relay_states = [False] * self.NUM_CHANNELS
            return True
        except Exception as e:
            self.ser = None
            raise RuntimeError(f"Failed to connect to Numato relay: {e}")

    def close(self):
        """Disconnect from the relay module, turning all relays off first."""
        if self.ser and self.ser.is_open:
            # Turn all relays off before disconnecting
            for i in range(self.NUM_CHANNELS):
                try:
                    self._send_command(f"relay off {i}\r")
                except Exception:
                    pass
            self.ser.close()
        self.ser = None
        self.relay_states = [False] * self.NUM_CHANNELS

    def _send_command(self, cmd: str) -> bool:
        """
        Send a command string to the Numato module.

        Args:
            cmd: Command string to send

        Returns:
            True if command was sent successfully
        """
        if not self.is_connected:
            raise RuntimeError("Numato relay not connected")

        self.ser.write(cmd.encode())
        time.sleep(0.05)
        return True

    def relay_on(self, channel: int) -> bool:
        """
        Turn a relay ON.

        Args:
            channel: Relay channel (0-3)

        Returns:
            True if successful
        """
        if channel < 0 or channel >= self.NUM_CHANNELS:
            raise ValueError(f"Channel must be 0-{self.NUM_CHANNELS-1}")

        if self._send_command(f"relay on {channel}\r"):
            self.relay_states[channel] = True
            return True
        return False

    def relay_off(self, channel: int) -> bool:
        """
        Turn a relay OFF.

        Args:
            channel: Relay channel (0-3)

        Returns:
            True if successful
        """
        if channel < 0 or channel >= self.NUM_CHANNELS:
            raise ValueError(f"Channel must be 0-{self.NUM_CHANNELS-1}")

        if self._send_command(f"relay off {channel}\r"):
            self.relay_states[channel] = False
            return True
        return False

    def set_relay(self, channel: int, state: bool) -> bool:
        """
        Set relay to a specific state.

        Args:
            channel: Relay channel (0-3)
            state: True for ON, False for OFF

        Returns:
            True if successful
        """
        if state:
            return self.relay_on(channel)
        else:
            return self.relay_off(channel)

    def all_on(self) -> bool:
        """Turn all relays ON."""
        success = True
        for i in range(self.NUM_CHANNELS):
            if not self.relay_on(i):
                success = False
        return success

    def all_off(self) -> bool:
        """Turn all relays OFF."""
        success = True
        for i in range(self.NUM_CHANNELS):
            if not self.relay_off(i):
                success = False
        return success

    def get_state(self, channel: int) -> bool:
        """
        Get the current state of a relay.

        Args:
            channel: Relay channel (0-3)

        Returns:
            True if relay is ON, False if OFF
        """
        if channel < 0 or channel >= self.NUM_CHANNELS:
            raise ValueError(f"Channel must be 0-{self.NUM_CHANNELS-1}")
        return self.relay_states[channel]

    def get_all_states(self) -> list[bool]:
        """Get states of all relays."""
        return self.relay_states.copy()
