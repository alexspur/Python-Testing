from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton,
    QFormLayout, QDoubleSpinBox, QButtonGroup, QGridLayout
)
from utils.status_lamp import StatusLamp
from PyQt6.QtWidgets import QComboBox, QLabel
from PyQt6.QtWidgets import QPushButton

class BNC575Panel(QGroupBox):
    def __init__(self):
        super().__init__("BNC575 Control")

        layout = QVBoxLayout()
        self.setLayout(layout)
        self.lamp = StatusLamp(size=14)
        layout.addWidget(self.lamp)

        # --------------------------- Buttons ---------------------------
        row = QHBoxLayout()
        self.btn_connect = QPushButton("Connect BNC575")
        self.btn_fire = QPushButton("Fire Pulse")
        self.btn_disconnect = QPushButton("Disconnect")
        layout.addWidget(self.btn_disconnect)
        row.addWidget(self.btn_connect)
        row.addWidget(self.btn_fire)
        layout.addLayout(row)

        # ----------------------- Improved Value Entry with Unit Buttons -----------------------------
        # Create spinboxes with unit selectors for each channel
        grid = QGridLayout()
        grid.setSpacing(8)

        # Headers
        grid.addWidget(QLabel("<b>Parameter</b>"), 0, 0)
        grid.addWidget(QLabel("<b>Value</b>"), 0, 1)
        grid.addWidget(QLabel("<b>Units</b>"), 0, 2)

        row_idx = 1

        # Channel A
        self.widthA, self.widthA_units = self._create_value_with_units("Width A", 1.0, "μs")
        grid.addWidget(QLabel("Width A:"), row_idx, 0)
        grid.addWidget(self.widthA, row_idx, 1)
        grid.addLayout(self.widthA_units, row_idx, 2)
        row_idx += 1

        self.delayA, self.delayA_units = self._create_value_with_units("Delay A", 0.0, "μs")
        grid.addWidget(QLabel("Delay A:"), row_idx, 0)
        grid.addWidget(self.delayA, row_idx, 1)
        grid.addLayout(self.delayA_units, row_idx, 2)
        row_idx += 1

        # Channel B
        self.widthB, self.widthB_units = self._create_value_with_units("Width B", 1.0, "μs")
        grid.addWidget(QLabel("Width B:"), row_idx, 0)
        grid.addWidget(self.widthB, row_idx, 1)
        grid.addLayout(self.widthB_units, row_idx, 2)
        row_idx += 1

        self.delayB, self.delayB_units = self._create_value_with_units("Delay B", 0.0, "μs")
        grid.addWidget(QLabel("Delay B:"), row_idx, 0)
        grid.addWidget(self.delayB, row_idx, 1)
        grid.addLayout(self.delayB_units, row_idx, 2)
        row_idx += 1

        # Channel C
        self.widthC, self.widthC_units = self._create_value_with_units("Width C", 40.0, "μs")
        grid.addWidget(QLabel("Width C:"), row_idx, 0)
        grid.addWidget(self.widthC, row_idx, 1)
        grid.addLayout(self.widthC_units, row_idx, 2)
        row_idx += 1

        self.delayC, self.delayC_units = self._create_value_with_units("Delay C", 0.0, "μs")
        grid.addWidget(QLabel("Delay C:"), row_idx, 0)
        grid.addWidget(self.delayC, row_idx, 1)
        grid.addLayout(self.delayC_units, row_idx, 2)
        row_idx += 1

        # Channel D
        self.widthD, self.widthD_units = self._create_value_with_units("Width D", 40.0, "μs")
        grid.addWidget(QLabel("Width D:"), row_idx, 0)
        grid.addWidget(self.widthD, row_idx, 1)
        grid.addLayout(self.widthD_units, row_idx, 2)
        row_idx += 1

        self.delayD, self.delayD_units = self._create_value_with_units("Delay D", 0.0, "μs")
        grid.addWidget(QLabel("Delay D:"), row_idx, 0)
        grid.addWidget(self.delayD, row_idx, 1)
        grid.addLayout(self.delayD_units, row_idx, 2)

        layout.addLayout(grid)

        # --------------------------- Channel Enable Toggles ----------------
        enable_row = QHBoxLayout()
        self.btn_en_a = QPushButton("CHA Enabled")
        self.btn_en_a.setCheckable(True)
        self.btn_en_a.setChecked(True)
        self.btn_en_a.setStyleSheet("QPushButton:checked { background-color: #4CAF50; color: white; font-weight: bold; }")

        self.btn_en_b = QPushButton("CHB Enabled")
        self.btn_en_b.setCheckable(True)
        self.btn_en_b.setChecked(True)
        self.btn_en_b.setStyleSheet("QPushButton:checked { background-color: #4CAF50; color: white; font-weight: bold; }")

        self.btn_en_c = QPushButton("CHC Enabled")
        self.btn_en_c.setCheckable(True)
        self.btn_en_c.setChecked(True)
        self.btn_en_c.setStyleSheet("QPushButton:checked { background-color: #4CAF50; color: white; font-weight: bold; }")

        self.btn_en_d = QPushButton("CHD Enabled")
        self.btn_en_d.setCheckable(True)
        self.btn_en_d.setChecked(True)
        self.btn_en_d.setStyleSheet("QPushButton:checked { background-color: #4CAF50; color: white; font-weight: bold; }")

        enable_row.addWidget(self.btn_en_a)
        enable_row.addWidget(self.btn_en_b)
        enable_row.addWidget(self.btn_en_c)
        enable_row.addWidget(self.btn_en_d)
        layout.addLayout(enable_row)

        # Trigger enable toggle
        trig_row = QHBoxLayout()
        self.btn_en_trig = QPushButton("Trigger Enabled")
        self.btn_en_trig.setCheckable(True)
        self.btn_en_trig.setChecked(True)
        self.btn_en_trig.setStyleSheet("QPushButton:checked { background-color: #4CAF50; color: white; font-weight: bold; }")
        trig_row.addWidget(self.btn_en_trig)
        layout.addLayout(trig_row)

        # --------------------------- Apply / Read / Arm ----------------
        row2 = QHBoxLayout()
        self.btn_apply = QPushButton("Apply Settings")
        self.btn_read  = QPushButton("Read Settings")
        self.btn_arm   = QPushButton("Arm (EXT TRIG)")
        row2.addWidget(self.btn_apply)
        row2.addWidget(self.btn_read)
        row2.addWidget(self.btn_arm)

        layout.addLayout(row2)

        # --- Trigger Controls ---
        self.trig_source = QComboBox()
        self.trig_source.addItems(["EXT", "INT"])
        grid.addWidget(QLabel("Trigger Source:"), row_idx + 1, 0)
        grid.addWidget(self.trig_source, row_idx + 1, 1)

        self.trig_slope = QComboBox()
        self.trig_slope.addItems(["RIS", "FALL"])
        grid.addWidget(QLabel("Trigger Slope:"), row_idx + 2, 0)
        grid.addWidget(self.trig_slope, row_idx + 2, 1)

        self.trig_level = QDoubleSpinBox()
        self.trig_level.setDecimals(3)
        self.trig_level.setRange(0.0, 5.0)
        self.trig_level.setValue(2.50)
        grid.addWidget(QLabel("Trigger Level (V):"), row_idx + 3, 0)
        grid.addWidget(self.trig_level, row_idx + 3, 1)

        self.btn_apply_trigger = QPushButton("Apply Trigger Settings")
        layout.addWidget(self.btn_apply_trigger)

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
    def get_widthA(self):
        return self.get_value_in_seconds(self.widthA, self.widthA_units)

    def get_delayA(self):
        return self.get_value_in_seconds(self.delayA, self.delayA_units)

    def get_widthB(self):
        return self.get_value_in_seconds(self.widthB, self.widthB_units)

    def get_delayB(self):
        return self.get_value_in_seconds(self.delayB, self.delayB_units)

    def get_widthC(self):
        return self.get_value_in_seconds(self.widthC, self.widthC_units)

    def get_delayC(self):
        return self.get_value_in_seconds(self.delayC, self.delayC_units)

    def get_widthD(self):
        return self.get_value_in_seconds(self.widthD, self.widthD_units)

    def get_delayD(self):
        return self.get_value_in_seconds(self.delayD, self.delayD_units)
