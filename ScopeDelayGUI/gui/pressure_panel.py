# gui/pressure_panel.py
from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, 
    QDoubleSpinBox, QPushButton, QComboBox
)
from PyQt6.QtCore import Qt


class PressureControlPanel(QGroupBox):
    """
    Panel for controlling Parker P31P pressure regulator via Arduino.
    
    Handles PSI/Bar to voltage conversion for 0-148 PSI (0-10 bar) regulator.
    """
    
    # Regulator specs: 0-10 bar = 0-148 PSI, controlled by 0-10V
    MAX_PSI = 148.0
    MAX_BAR = 10.0
    MAX_VOLTAGE = 10.0
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
        self.spin_value.setRange(0, 148)
        self.spin_value.setValue(0)
        self.spin_value.setSingleStep(1.0)
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
        # QUICK PRESET BUTTONS
        # ─────────────────────────────────────────────
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Presets:"))
        
        presets = [0, 10, 20, 30, 50, 75, 100]
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
            self.spin_value.setRange(0, self.MAX_PSI)
            self.spin_value.setSingleStep(1.0)
            self.spin_value.setDecimals(1)
        elif unit == "Bar":
            self.spin_value.setRange(0, self.MAX_BAR)
            self.spin_value.setSingleStep(0.1)
            self.spin_value.setDecimals(2)
        elif unit == "Volts":
            self.spin_value.setRange(0, self.MAX_VOLTAGE)
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
        
        Returns:
            Voltage to send to Arduino (0-10V)
        """
        value = self.spin_value.value()
        unit = self.combo_unit.currentText()
        
        if unit == "PSI":
            # PSI → Voltage: V = (PSI / 148) * 10
            voltage = (value / self.MAX_PSI) * self.MAX_VOLTAGE
        elif unit == "Bar":
            # Bar → Voltage: V = (Bar / 10) * 10
            voltage = (value / self.MAX_BAR) * self.MAX_VOLTAGE
        elif unit == "Volts":
            voltage = value
        elif unit == "%":
            # Percent → Voltage: V = (% / 100) * 10
            voltage = (value / 100.0) * self.MAX_VOLTAGE
        else:
            voltage = 0.0
        
        return max(0.0, min(self.MAX_VOLTAGE, voltage))
    
    def get_psi(self) -> float:
        """Get current setpoint in PSI"""
        voltage = self.get_voltage()
        return (voltage / self.MAX_VOLTAGE) * self.MAX_PSI
    
    def update_output_display(self, voltage: float):
        """Update the output status label"""
        self._current_voltage = voltage
        psi = (voltage / self.MAX_VOLTAGE) * self.MAX_PSI
        bar = (voltage / self.MAX_VOLTAGE) * self.MAX_BAR
        self.label_output.setText(f"Output: {voltage:.3f} V ({psi:.1f} PSI / {bar:.2f} bar)")