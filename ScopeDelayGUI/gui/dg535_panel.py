from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton, QFormLayout, QDoubleSpinBox,
    QGridLayout, QLabel, QButtonGroup
)
from utils.status_lamp import StatusLamp

class DG535Panel(QGroupBox):
    def __init__(self):
        super().__init__("DG535 Control")

        layout = QVBoxLayout()
        self.setLayout(layout)

        # ⭐ NEW: Status Lamp
        self.lamp = StatusLamp(size=14)
        layout.addWidget(self.lamp)

        # Buttons
        hl = QHBoxLayout()
        self.btn_connect = QPushButton("Connect DG535")
        self.btn_fire = QPushButton("Fire DG535")
        self.btn_disconnect = QPushButton("Disconnect")
        hl.addWidget(self.btn_connect)
        hl.addWidget(self.btn_fire)
        layout.addLayout(hl)
        layout.addWidget(self.btn_disconnect)

        # ----------------------- Improved Value Entry with Unit Buttons -----------------------------
        grid = QGridLayout()
        grid.setSpacing(8)

        # Headers
        grid.addWidget(QLabel("<b>Parameter</b>"), 0, 0)
        grid.addWidget(QLabel("<b>Value</b>"), 0, 1)
        grid.addWidget(QLabel("<b>Units</b>"), 0, 2)

        row_idx = 1

        # Delay A
        self.delayA, self.delayA_units = self._create_value_with_units("Delay A", 0.0, "μs")
        grid.addWidget(QLabel("Delay A:"), row_idx, 0)
        grid.addWidget(self.delayA, row_idx, 1)
        grid.addLayout(self.delayA_units, row_idx, 2)
        row_idx += 1

        # Width A
        self.widthA, self.widthA_units = self._create_value_with_units("Width A", 1.0, "μs")
        grid.addWidget(QLabel("Width A:"), row_idx, 0)
        grid.addWidget(self.widthA, row_idx, 1)
        grid.addLayout(self.widthA_units, row_idx, 2)
        row_idx += 1

        # Delay B
        self.delayB, self.delayB_units = self._create_value_with_units("Delay B", 0.0, "μs")
        grid.addWidget(QLabel("Delay B:"), row_idx, 0)
        grid.addWidget(self.delayB, row_idx, 1)
        grid.addLayout(self.delayB_units, row_idx, 2)
        row_idx += 1

        # Width B
        self.widthB, self.widthB_units = self._create_value_with_units("Width B", 1.0, "μs")
        grid.addWidget(QLabel("Width B:"), row_idx, 0)
        grid.addWidget(self.widthB, row_idx, 1)
        grid.addLayout(self.widthB_units, row_idx, 2)

        layout.addLayout(grid)

    def _create_value_with_units(self, name, default_value, default_unit):
        """Create a spinbox with unit selector buttons (s, ms, μs, ns, ps)"""
        # Spinbox for numeric value
        spinbox = QDoubleSpinBox()
        spinbox.setDecimals(3)
        spinbox.setRange(0, 999999)
        spinbox.setValue(default_value)
        spinbox.setMaximumWidth(100)

        # Unit buttons
        units_layout = QHBoxLayout()
        units_layout.setSpacing(2)

        button_group = QButtonGroup(self)
        button_group.setExclusive(True)

        units = ["s", "ms", "μs", "ns", "ps"]
        multipliers = {
            "s": 1.0,
            "ms": 1e-3,
            "μs": 1e-6,
            "ns": 1e-9,
            "ps": 1e-12
        }

        buttons = {}
        for unit in units:
            btn = QPushButton(unit)
            btn.setCheckable(True)
            btn.setMaximumWidth(40)
            btn.setStyleSheet("""
                QPushButton {
                    padding: 2px;
                    font-size: 10px;
                }
                QPushButton:checked {
                    background-color: #2196F3;
                    color: white;
                    font-weight: bold;
                }
            """)
            button_group.addButton(btn)
            units_layout.addWidget(btn)
            buttons[unit] = btn

            # Store multiplier as button property
            btn.multiplier = multipliers[unit]

        # Set default unit
        buttons[default_unit].setChecked(True)

        # Store button group and buttons for later access
        units_layout.button_group = button_group
        units_layout.buttons = buttons
        units_layout.spinbox = spinbox

        return spinbox, units_layout

    def get_value_in_seconds(self, spinbox, units_layout):
        """Convert spinbox value to seconds based on selected unit"""
        value = spinbox.value()
        checked_button = units_layout.button_group.checkedButton()
        if checked_button:
            return value * checked_button.multiplier
        return value * 1e-6  # Default to microseconds if nothing checked

    # Convenience methods to get values in seconds
    def get_delayA(self):
        return self.get_value_in_seconds(self.delayA, self.delayA_units)

    def get_widthA(self):
        return self.get_value_in_seconds(self.widthA, self.widthA_units)

    def get_delayB(self):
        return self.get_value_in_seconds(self.delayB, self.delayB_units)

    def get_widthB(self):
        return self.get_value_in_seconds(self.widthB, self.widthB_units)
