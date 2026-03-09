# gui/numato_relay_panel.py
"""
GUI Panel for Numato 4-Channel USB Relay Module
Styled to match SF6 panel with rotary knob switches
"""
from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QComboBox, QPushButton
)
from PyQt6.QtCore import Qt, pyqtSignal
from utils.status_lamp import StatusLamp
from utils.rotary_knob import RotaryKnobSwitch


class NumatoRelayPanel(QGroupBox):
    """Panel for controlling the Numato 4-channel USB relay module."""

    # Signals for main window to connect
    relay_state_changed = pyqtSignal(int, bool)  # channel, state
    all_on_requested = pyqtSignal()
    all_off_requested = pyqtSignal()
    polling_toggle_requested = pyqtSignal(bool)  # True = start, False = stop

    # Relay names - customize these as needed
    RELAY_NAMES = [
        "Discharge Relay",
        "Relay 1",
        "Charging Relay",
        "Relay 3"
    ]

    def __init__(self, parent=None):
        super().__init__("Numato Relay Control", parent)

        layout = QVBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setLayout(layout)

        # Status lamp
        self.lamp = StatusLamp(size=14)
        self.lamp.set_status("red", "Disconnected")
        layout.addWidget(self.lamp)

        # Connection row
        conn_row = QHBoxLayout()
        conn_row.setSpacing(6)

        conn_row.addWidget(QLabel("COM Port:"))

        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(80)
        conn_row.addWidget(self.port_combo)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setMaximumWidth(55)
        conn_row.addWidget(self.btn_refresh)

        self.btn_connect = QPushButton("Connect")
        conn_row.addWidget(self.btn_connect)

        self.btn_disconnect = QPushButton("Disconnect")
        conn_row.addWidget(self.btn_disconnect)

        layout.addLayout(conn_row)

        # Relay switches in a 2x2 grid (matching Marx switches style)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)

        self.switches = []
        for i, name in enumerate(self.RELAY_NAMES):
            knob = RotaryKnobSwitch(label=name, size=36)
            self.switches.append(knob)
            grid.addWidget(knob, i // 2, i % 2)

            # Connect switch state change to signal
            knob.stateChanged.connect(lambda on, ch=i: self._on_switch_changed(ch, on))

        layout.addLayout(grid)

        # All ON / All OFF buttons
        all_row = QHBoxLayout()
        all_row.setSpacing(8)

        self.btn_all_on = QPushButton("ALL ON")
        self.btn_all_on.clicked.connect(self._on_all_on)

        self.btn_all_off = QPushButton("ALL OFF")
        self.btn_all_off.clicked.connect(self._on_all_off)

        all_row.addWidget(self.btn_all_on)
        all_row.addWidget(self.btn_all_off)
        layout.addLayout(all_row)

        # Pushbutton polling row
        poll_row = QHBoxLayout()
        poll_row.setSpacing(6)

        self.btn_polling = QPushButton("Start Polling")
        self.btn_polling.clicked.connect(self._on_polling_toggle)
        poll_row.addWidget(self.btn_polling)

        self.poll_status_label = QLabel("GPIO polling: OFF")
        poll_row.addWidget(self.poll_status_label)

        layout.addLayout(poll_row)

        self._polling_active = False

        layout.addStretch(1)

    def _on_switch_changed(self, channel: int, on: bool):
        """Handle switch toggle - emit signal for main window"""
        self.relay_state_changed.emit(channel, on)

    def _on_all_on(self):
        """Turn all switches on and emit signal"""
        for switch in self.switches:
            switch.set_on(True)
        self.all_on_requested.emit()

    def _on_all_off(self):
        """Turn all switches off and emit signal"""
        for switch in self.switches:
            switch.set_on(False)
        self.all_off_requested.emit()

    def _on_polling_toggle(self):
        """Toggle GPIO polling on/off."""
        self._polling_active = not self._polling_active
        self.polling_toggle_requested.emit(self._polling_active)

    def set_polling_active(self, active: bool):
        """Update the polling button/label to reflect current state."""
        self._polling_active = active
        if active:
            self.btn_polling.setText("Stop Polling")
            self.poll_status_label.setText("GPIO polling: ON")
        else:
            self.btn_polling.setText("Start Polling")
            self.poll_status_label.setText("GPIO polling: OFF")

    def update_relay_state(self, channel: int, is_on: bool):
        """Update the display for a specific relay (called from main window)."""
        if 0 <= channel < len(self.switches):
            # Update without triggering signal
            self.switches[channel].state = is_on
            self.switches[channel].knob.setStyleSheet(self.switches[channel]._style(is_on))

    def update_all_states(self, states: list[bool]):
        """Update display for all relays."""
        for i, state in enumerate(states):
            if i < len(self.switches):
                self.update_relay_state(i, state)

    def set_connected(self, connected: bool, port: str = ""):
        """Update connection status display."""
        if connected:
            self.lamp.set_status("green", f"Connected ({port})")
        else:
            self.lamp.set_status("red", "Disconnected")
            # Reset all switches to OFF when disconnected
            for switch in self.switches:
                switch.state = False
                switch.knob.setStyleSheet(switch._style(False))
