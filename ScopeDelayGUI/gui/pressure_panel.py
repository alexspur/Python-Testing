# gui/pressure_panel.py
from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel,
    QDoubleSpinBox, QPushButton, QComboBox
)
from PyQt6.QtCore import Qt


class PressureControlPanel(QGroupBox):
    """
    Panel for controlling pressure regulator via Arduino.

    Uses calibrated voltage-to-PSI relationship:
        PSI = 2.5106 * V - 0.178
        V = (PSI + 0.178) / 2.5106

    At 10V output: PSI = 2.5106 * 10 - 0.178 = 24.928 PSI max
    At 0V output: PSI = -0.178 (clamped to 0)
    """

    # Calibration constants: PSI = SLOPE * V + INTERCEPT
    CAL_SLOPE = 2.5106      # PSI per Volt
    CAL_INTERCEPT = -0.178  # PSI offset

    # Derived limits
    MAX_VOLTAGE = 10.0
    MAX_PSI = CAL_SLOPE * MAX_VOLTAGE + CAL_INTERCEPT  # ~24.93 PSI
    MAX_BAR = MAX_PSI / 14.5038  # ~1.72 bar
    PSI_PER_BAR = 14.5038
    
    def __init__(self):
        super().__init__("Pressure Regulator Control")
        
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # ─────────────────────────────────────────────
        # SETPOINT ROW
        # ─────────────────────────────────────────────
        setpoint_row = QHBoxLayout()
        
        # Value input
        setpoint_row.addWidget(QLabel("Setpoint:"))
        self.spin_value = QDoubleSpinBox()
        self.spin_value.setDecimals(2)
        self.spin_value.setRange(0, self.MAX_PSI)  # 0 to ~24.93 PSI
        self.spin_value.setValue(0)
        self.spin_value.setSingleStep(0.5)
        self.spin_value.setFixedWidth(100)
        setpoint_row.addWidget(self.spin_value)
        
        # Unit selector
        self.combo_unit = QComboBox()
        self.combo_unit.addItems(["PSI", "Bar", "Volts", "%"])
        self.combo_unit.setCurrentText("PSI")
        self.combo_unit.currentTextChanged.connect(self._on_unit_changed)
        setpoint_row.addWidget(self.combo_unit)
        
        # Apply button
        self.btn_apply = QPushButton("Set Pressure")
        self.btn_apply.setStyleSheet(
            "background-color: #4CAF50; color: white; font-weight: bold; padding: 6px 12px;"
        )
        setpoint_row.addWidget(self.btn_apply)
        
        setpoint_row.addStretch()
        layout.addLayout(setpoint_row)
        
        # ─────────────────────────────────────────────
        # QUICK PRESET BUTTONS (0-25 PSI range)
        # ─────────────────────────────────────────────
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Presets:"))

        presets = [0, 5, 10, 12, 15, 20, 24]
        self.preset_buttons = []
        for psi in presets:
            btn = QPushButton(f"{psi}")
            btn.setFixedWidth(40)
            btn.clicked.connect(lambda checked, p=psi: self._on_preset(p))
            preset_row.addWidget(btn)
            self.preset_buttons.append(btn)
        
        # Zero button (important for safety)
        self.btn_zero = QPushButton("ZERO")
        self.btn_zero.setStyleSheet("background-color: #f44336; color: white; font-weight: bold;")
        self.btn_zero.clicked.connect(lambda: self._on_preset(0))
        preset_row.addWidget(self.btn_zero)
        
        preset_row.addStretch()
        layout.addLayout(preset_row)
        
        # ─────────────────────────────────────────────
        # CURRENT OUTPUT DISPLAY
        # ─────────────────────────────────────────────
        status_row = QHBoxLayout()
        self.label_output = QLabel("Output: 0.000 V (0.0 PSI)")
        self.label_output.setStyleSheet("font-weight: bold; color: #333;")
        status_row.addWidget(self.label_output)
        status_row.addStretch()
        layout.addLayout(status_row)
        
        # Store current output voltage
        self._current_voltage = 0.0
    
    def _on_unit_changed(self, unit: str):
        """Update spinbox range when unit changes"""
        if unit == "PSI":
            self.spin_value.setRange(0, self.MAX_PSI)  # 0 to ~24.93 PSI
            self.spin_value.setSingleStep(0.5)
            self.spin_value.setDecimals(2)
        elif unit == "Bar":
            self.spin_value.setRange(0, self.MAX_BAR)  # 0 to ~1.72 bar
            self.spin_value.setSingleStep(0.05)
            self.spin_value.setDecimals(3)
        elif unit == "Volts":
            self.spin_value.setRange(0, self.MAX_VOLTAGE)  # 0 to 10V
            self.spin_value.setSingleStep(0.1)
            self.spin_value.setDecimals(3)
        elif unit == "%":
            self.spin_value.setRange(0, 100)
            self.spin_value.setSingleStep(1.0)
            self.spin_value.setDecimals(1)
    
    def _on_preset(self, psi: float):
        """Handle preset button click"""
        self.combo_unit.setCurrentText("PSI")
        self.spin_value.setValue(psi)
        # Emit apply signal by clicking apply button
        self.btn_apply.click()
    
    def get_voltage(self) -> float:
        """
        Convert current spinbox value to output voltage (0-10V).

        Uses calibration: PSI = 2.5106 * V - 0.178
        Inverted: V = (PSI + 0.178) / 2.5106

        Returns:
            Voltage to send to Arduino (0-10V)
        """
        value = self.spin_value.value()
        unit = self.combo_unit.currentText()

        if unit == "PSI":
            # PSI → Voltage: V = (PSI - INTERCEPT) / SLOPE
            # Since INTERCEPT is negative: V = (PSI + 0.178) / 2.5106
            voltage = (value - self.CAL_INTERCEPT) / self.CAL_SLOPE
        elif unit == "Bar":
            # Bar → PSI → Voltage
            psi = value * self.PSI_PER_BAR
            voltage = (psi - self.CAL_INTERCEPT) / self.CAL_SLOPE
        elif unit == "Volts":
            voltage = value
        elif unit == "%":
            # Percent of max voltage range
            voltage = (value / 100.0) * self.MAX_VOLTAGE
        else:
            voltage = 0.0

        return max(0.0, min(self.MAX_VOLTAGE, voltage))
    
    def get_psi(self) -> float:
        """Get current setpoint in PSI using calibration formula."""
        voltage = self.get_voltage()
        return self.voltage_to_psi(voltage)

    @classmethod
    def voltage_to_psi(cls, voltage: float) -> float:
        """Convert voltage to PSI using calibration: PSI = 2.5106 * V - 0.178"""
        psi = cls.CAL_SLOPE * voltage + cls.CAL_INTERCEPT
        return max(0.0, psi)

    @classmethod
    def psi_to_voltage(cls, psi: float) -> float:
        """Convert PSI to voltage using calibration: V = (PSI + 0.178) / 2.5106"""
        voltage = (psi - cls.CAL_INTERCEPT) / cls.CAL_SLOPE
        return max(0.0, min(cls.MAX_VOLTAGE, voltage))

    def update_output_display(self, voltage: float):
        """Update the output status label"""
        self._current_voltage = voltage
        psi = self.voltage_to_psi(voltage)
        bar = psi / self.PSI_PER_BAR
        self.label_output.setText(f"Output: {voltage:.3f} V ({psi:.2f} PSI / {bar:.3f} bar)")