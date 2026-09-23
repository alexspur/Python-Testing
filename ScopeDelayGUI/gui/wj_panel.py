# gui/wj_panel.py

from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QDoubleSpinBox, QComboBox
)

from utils.status_lamp import StatusLamp


class WJPanel(QGroupBox):
    """Both WJ supplies share one program and command set.

    One kV field, one mA field, the presets and the three command buttons all
    act on both supplies together, which is how the supplies have always been
    driven. Each supply keeps its own row for the COM port, connect and
    disconnect, and its readback status.

    Polarity belongs to the supply, not to the number typed here: enter 70 for
    the negative rail, not -70.
    """

    # Rated maximums of both supplies, and what the DAC scaling in
    # instruments/wj.py assumes. A value above these is refused rather than
    # silently clamped down to the maximum, which is what the driver does.
    MAX_KV = 100.0
    MAX_MA = 6.0

    # Charge voltages used in routine shots. A preset only fills the kV field;
    # nothing reaches a supply until Apply Program is pressed.
    PRESET_KV = (60.0, 65.0, 70.0, 75.0)

    def __init__(self, num_units=2):
        super().__init__("WJ High Voltage Supplies")

        self.rows = []   # store each WJ row so main_window can access
        layout = QVBoxLayout()
        self.setLayout(layout)

        # ─────────────────────────────────────────────
        # PROGRAM SETTINGS (both supplies)
        # ─────────────────────────────────────────────
        prog_row = QHBoxLayout()
        prog_row.addWidget(QLabel("Set Voltage (kV):"))
        self.voltage = QDoubleSpinBox()
        self.voltage.setRange(0, self.MAX_KV)
        self.voltage.setDecimals(2)
        self.voltage.setValue(60.0)   # default 60 kV (both supplies on startup)
        prog_row.addWidget(self.voltage)

        prog_row.addWidget(QLabel("Set Current (mA):"))
        self.current = QDoubleSpinBox()
        self.current.setRange(0, self.MAX_MA)
        self.current.setDecimals(2)
        # Full current. Every supply used to be commanded to its maximum
        # regardless of this field, so the default keeps that behavior until
        # the operator edits it.
        self.current.setValue(self.MAX_MA)
        prog_row.addWidget(self.current)
        prog_row.addStretch()

        layout.addLayout(prog_row)

        # ─────────────────────────────────────────────
        # kV PRESETS (fill the field only, send nothing)
        # ─────────────────────────────────────────────
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Presets:"))
        self.preset_buttons = {}
        for kv in self.PRESET_KV:
            btn = QPushButton(f"{kv:.0f} kV")
            btn.setToolTip(
                f"Put {kv:.0f} kV in the field. Nothing is sent until you "
                "press Apply Program.")
            btn.clicked.connect(lambda _checked, v=kv: self.voltage.setValue(v))
            self.preset_buttons[kv] = btn
            preset_row.addWidget(btn)
        preset_row.addStretch()

        layout.addLayout(preset_row)

        # ─────────────────────────────────────────────
        # COMMANDS (apply to both supplies)
        # ─────────────────────────────────────────────
        ctrl_row = QHBoxLayout()
        self.btn_set_v  = QPushButton("Apply Program")
        self.btn_hv_on  = QPushButton("HV ON")
        self.btn_hv_off = QPushButton("HV OFF")

        ctrl_row.addWidget(self.btn_set_v)
        ctrl_row.addWidget(self.btn_hv_on)
        ctrl_row.addWidget(self.btn_hv_off)
        ctrl_row.addStretch()

        layout.addLayout(ctrl_row)

        # ─────────────────────────────────────────────
        # INDIVIDUAL WJ UNIT ROWS (port + status only)
        # ─────────────────────────────────────────────
        grid = QGridLayout()

        for i in range(num_units):
            row = WJRow(i)
            self.rows.append(row)

            grid.addWidget(row.label,        i, 0)
            grid.addWidget(row.port_combo,   i, 1)
            grid.addWidget(row.connect,      i, 2)
            grid.addWidget(row.disconnect,   i, 3)
            grid.addWidget(row.lamp,         i, 4)
            grid.addWidget(row.label_status, i, 5)

        layout.addLayout(grid)

    def program_values(self):
        """Return (kV, mA) from the shared fields.

        Raises ValueError if either is above the supplies' rating, so a bad
        value is refused here instead of being clamped down inside the driver
        and quietly charging to something other than what was asked for.
        """
        kv = self.voltage.value()
        ma = self.current.value()
        if kv > self.MAX_KV:
            raise ValueError(
                f"{kv:.2f} kV is above the {self.MAX_KV:.0f} kV rating of these supplies")
        if ma > self.MAX_MA:
            raise ValueError(
                f"{ma:.2f} mA is above the {self.MAX_MA:.1f} mA rating of these supplies")
        return kv, ma


class WJRow:
    """Represents one row in the WJPanel."""
    def __init__(self, index):
        self.index = index

        # Short, because this label sets the panel's minimum width and the
        # panel has to sit beside the scopes without the window scrolling.
        labels = ["Negative:", "Positive:"]
        self.label = QLabel(labels[index] if index < len(labels) else f"WJ Power Supply #{index+1}")

        # ⭐ COM PORT DROPDOWN
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(100)

        self.connect = QPushButton("Connect")
        self.disconnect = QPushButton("Disconnect")

        self.lamp = StatusLamp(size=14)

        self.label_status = QLabel("Not Connected")
        # Fixed so the live readback text ("75.00 kV  6.000 mA  HV ON") cannot
        # widen the panel and push the window back into a horizontal scroll.
        self.label_status.setMinimumWidth(210)
        self.label_status.setMaximumWidth(210)
