# gui/numato_relay_panel.py
"""Numato relay panel: the COM port row and the three HV relay modes.

The three buttons are the status lamps. The button of the commanded mode
is full colour with a thick dark border (GROUND red, FLOAT yellow, CHARGE
green); the other two are a dark, muted version of their colour with grey
text. Unknown: all three dimmed and "State unknown" beneath. While a
transition runs all three are disabled and the target button blinks.

The state shown is what the GUI last commanded, never a readback: the
Numato reports only its own cache. The panel only asks the main window for
a mode; the write order, the HV-off interlock, the safety rule and the
logging live there.
"""
from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QComboBox, QPushButton,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from utils.status_lamp import StatusLamp
from utils.relay_modes import MODES, GROUND, FLOAT, CHARGE, UNKNOWN

# (background, text) when the mode is the current one, and when it is not.
LIT = {
    GROUND: ("#E00000", "#FFFFFF"),
    FLOAT:  ("#FFD400", "#000000"),
    CHARGE: ("#00C020", "#FFFFFF"),
}
DIM = {
    GROUND: ("#5A1E1E", "#9A9A9A"),
    FLOAT:  ("#5C5320", "#9A9A9A"),
    CHARGE: ("#1E4D26", "#9A9A9A"),
}
DESCRIPTION = {
    GROUND: "Marx grounded",
    FLOAT:  "isolated from supplies and ground",
    CHARGE: "supplies connected to the Marx, HV on",
}
BLINK_MS = 400


def button_style(mode, lit):
    bg, fg = (LIT if lit else DIM)[mode]
    border = "3px solid #202020" if lit else "1px solid #404040"
    # The :disabled rule keeps the colours while a transition has the buttons
    # off; Qt would otherwise grey the text and hide the blink.
    return (f"QPushButton {{ background-color:{bg}; color:{fg}; font-weight:bold; "
            f"padding:6px 14px; border:{border}; border-radius:4px; }}"
            f"QPushButton:disabled {{ background-color:{bg}; color:{fg}; }}")


class NumatoRelayPanel(QGroupBox):
    """COM port row, connection lamp, and the three mode buttons."""

    mode_requested = pyqtSignal(str)     # GROUND / FLOAT / CHARGE

    def __init__(self, parent=None):
        super().__init__("Numato Relay Control", parent)

        layout = QVBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setLayout(layout)

        # Connection lamp and text: "Connected (COM7)" / "Disconnected".
        self.lamp = StatusLamp(size=14)
        self.lamp.set_status("red", "Disconnected")
        layout.addWidget(self.lamp)

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

        # The three modes: the button is the lamp; a short description beside it.
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        self.buttons = {}
        self.descriptions = {}
        self.lit = {}
        for row, mode in enumerate(MODES):
            btn = QPushButton(mode)
            btn.setMinimumHeight(32)
            btn.setMinimumWidth(110)
            btn.setToolTip(DESCRIPTION[mode])
            btn.clicked.connect(lambda _checked=False, m=mode: self.mode_requested.emit(m))
            desc = QLabel(DESCRIPTION[mode])
            self.buttons[mode] = btn
            self.descriptions[mode] = desc
            grid.addWidget(btn, row, 0)
            grid.addWidget(desc, row, 1)
        layout.addLayout(grid)

        self.state_label = QLabel("State unknown")
        self.state_label.setStyleSheet("font-style:italic; color:#555555;")
        layout.addWidget(self.state_label)

        self.mode = UNKNOWN
        self.busy_target = None
        self._blink_on = False
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(BLINK_MS)
        self._blink_timer.timeout.connect(self._blink)
        for mode in MODES:
            self._paint(mode, False)
        layout.addStretch(1)

    # ------------------------------------------------------------ paint
    def _paint(self, mode, lit):
        self.lit[mode] = bool(lit)
        self.buttons[mode].setStyleSheet(button_style(mode, lit))

    def _blink(self):
        if self.busy_target is None:
            return
        self._blink_on = not self._blink_on
        self._paint(self.busy_target, self._blink_on)

    # ------------------------------------------------------------ state
    def set_mode(self, mode):
        """Light the button of the commanded mode only. Anything that is not
        one of the three modes shows all three dimmed and 'State unknown'."""
        self.mode = mode if mode in MODES else UNKNOWN
        for m in MODES:
            self._paint(m, m == self.mode)
        if self.mode in MODES:
            self.state_label.setText(f"State: {self.mode} (commanded, not read back)")
        else:
            self.state_label.setText("State unknown")

    def set_busy(self, busy, target=""):
        """All three buttons off while a transition runs; the target blinks."""
        for btn in self.buttons.values():
            btn.setEnabled(not busy)
        if busy:
            self.busy_target = target if target in MODES else None
            self._blink_on = False
            self.state_label.setText(f"Changing to {target} ..." if target else "Changing ...")
            self._blink_timer.start()
        else:
            self._blink_timer.stop()
            self.busy_target = None
            self.set_mode(self.mode)

    def set_enabled_modes(self, modes):
        """Enable only these buttons (GROUND alone after a failed write)."""
        for m, btn in self.buttons.items():
            btn.setEnabled(m in modes)

    def set_connected(self, connected, port=""):
        if connected:
            self.lamp.set_status("green", f"Connected ({port})")
        else:
            self.lamp.set_status("red", "Disconnected")
            self.set_mode(UNKNOWN)
