# gui/pressure_panel.py
from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel,
    QDoubleSpinBox, QPushButton, QComboBox
)
from PyQt6.QtCore import Qt


class PressureControlPanel(QGroupBox):
    """
    Panel for choosing the Parker regulator pressure setpoint.

    The GUI now sends the desired pressure to the Mega as a raw PSI value
    ("PSI <val>") and the Mega firmware does the calibrated PSI->DAC-voltage
    mapping (see MarxController CAL_SLOPE/CAL_OFFSET). So this panel deals only
    in engineering units (PSI / Bar / %) — there is no voltage calibration here
    anymore. The setpoint range and quick presets are configurable from main.py.
    """

    PSI_PER_BAR = 14.5038

    def __init__(self, max_psi=120.0, presets=None):
        super().__init__("Pressure Regulator Control")

        self.max_psi = float(max_psi)
        if presets is None:
            presets = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

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
        self.spin_value.setRange(0, self.max_psi)
        self.spin_value.setValue(0)
        self.spin_value.setSingleStep(1.0)
        self.spin_value.setFixedWidth(100)
        setpoint_row.addWidget(self.spin_value)

        # Unit selector
        self.combo_unit = QComboBox()
        self.combo_unit.addItems(["PSI", "Bar", "%"])
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
        # QUICK PRESET BUTTONS (configured in main.py)
        # ─────────────────────────────────────────────
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Presets:"))

        self.preset_buttons = []
        for psi in presets:
            btn = QPushButton(f"{psi:g}")
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
        # CURRENT SETPOINT DISPLAY
        # ─────────────────────────────────────────────
        status_row = QHBoxLayout()
        self.label_output = QLabel("Setpoint: 0.00 PSI (0.000 bar)")
        self.label_output.setStyleSheet("font-weight: bold; color: #333;")
        status_row.addWidget(self.label_output)
        status_row.addStretch()
        layout.addLayout(status_row)

    def _on_unit_changed(self, unit: str):
        """Update spinbox range when unit changes"""
        if unit == "PSI":
            self.spin_value.setRange(0, self.max_psi)
            self.spin_value.setSingleStep(1.0)
            self.spin_value.setDecimals(2)
        elif unit == "Bar":
            self.spin_value.setRange(0, self.max_psi / self.PSI_PER_BAR)
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

    def get_psi(self) -> float:
        """Return the current setpoint in PSI (the value sent to the Mega).

        The Mega applies the regulator calibration, so we just convert the
        chosen unit to PSI and clamp to the panel's configured max."""
        value = self.spin_value.value()
        unit = self.combo_unit.currentText()

        if unit == "PSI":
            psi = value
        elif unit == "Bar":
            psi = value * self.PSI_PER_BAR
        elif unit == "%":
            psi = (value / 100.0) * self.max_psi
        else:
            psi = 0.0

        return max(0.0, min(self.max_psi, psi))

    def update_output_display(self, psi: float):
        """Update the status label with the commanded PSI setpoint."""
        bar = psi / self.PSI_PER_BAR
        self.label_output.setText(f"Setpoint: {psi:.2f} PSI ({bar:.3f} bar)")