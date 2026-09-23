# gui/wj_panel.py

from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QDoubleSpinBox, QComboBox
)

from utils.status_lamp import StatusLamp


class WJPanel(QGroupBox):
    def __init__(self, num_units=2):
        super().__init__("WJ High Voltage Supplies")

        self.rows = []   # store each WJ row so main_window can access
        layout = QVBoxLayout()
        self.setLayout(layout)

        # ─────────────────────────────────────────────
        # PROGRAM SETTINGS (shared for all units)
        # ─────────────────────────────────────────────
        prog_row = QHBoxLayout()
        prog_row.addWidget(QLabel("Set Voltage (kV):"))
        self.voltage = QDoubleSpinBox()
        self.voltage.setRange(0, 100)
        self.voltage.setDecimals(2)
        self.voltage.setValue(60.0)   # default 60 kV (both supplies on startup)
        prog_row.addWidget(self.voltage)

        prog_row.addWidget(QLabel("Set Current (mA):"))
        self.current = QDoubleSpinBox()
        self.current.setRange(0, 6)
        self.current.setDecimals(2)
        self.current.setValue(2.0)    # default 2 mA
        prog_row.addWidget(self.current)

        self.btn_set_v = QPushButton("Apply Program")
        prog_row.addWidget(self.btn_set_v)

        layout.addLayout(prog_row)

        # ─────────────────────────────────────────────
        # ACTION BUTTONS (apply to ALL units)
        # ─────────────────────────────────────────────
        ctrl_row = QHBoxLayout()
        self.btn_hv_on  = QPushButton("HV ON (ALL)")
        self.btn_hv_off = QPushButton("HV OFF (ALL)")
        self.btn_reset  = QPushButton("RESET (ALL)")
        self.btn_read   = QPushButton("READBACK")

        ctrl_row.addWidget(self.btn_hv_on)
        ctrl_row.addWidget(self.btn_hv_off)
        ctrl_row.addWidget(self.btn_reset)
        ctrl_row.addWidget(self.btn_read)

        layout.addLayout(ctrl_row)

        # ─────────────────────────────────────────────
        # INDIVIDUAL WJ UNIT ROWS
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


class WJRow:
    """Represents one row in the WJPanel."""
    def __init__(self, index):
        self.index = index

        # Custom labels for each power supply
        labels = ["Negative Power Supply", "Positive Power Supply"]
        self.label = QLabel(labels[index] if index < len(labels) else f"WJ Power Supply #{index+1}")

        # ⭐ COM PORT DROPDOWN
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(100)

        self.connect = QPushButton("Connect")
        self.disconnect = QPushButton("Disconnect")

        self.lamp = StatusLamp(size=14)

        self.label_status = QLabel("Not Connected")
