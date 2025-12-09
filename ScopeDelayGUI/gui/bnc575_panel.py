from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton,
    QFormLayout, QDoubleSpinBox
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
        # self.btn_connect = QPushButton("Connect BNC575")
        self.btn_fire = QPushButton("Fire Pulse")
        self.btn_disconnect = QPushButton("Disconnect")
        layout.addWidget(self.btn_disconnect)
        row.addWidget(self.btn_connect)
        row.addWidget(self.btn_fire)
        layout.addLayout(row)

        # ----------------------- Spinboxes -----------------------------
        form = QFormLayout()

        # Channel A
        self.widthA = QDoubleSpinBox(); self.widthA.setDecimals(9)
        self.delayA = QDoubleSpinBox(); self.delayA.setDecimals(9)

        # Channel B
        self.widthB = QDoubleSpinBox(); self.widthB.setDecimals(9)
        self.delayB = QDoubleSpinBox(); self.delayB.setDecimals(9)

        # Channel C
        self.widthC = QDoubleSpinBox(); self.widthC.setDecimals(9)
        self.delayC = QDoubleSpinBox(); self.delayC.setDecimals(9)

        # Channel D
        self.widthD = QDoubleSpinBox(); self.widthD.setDecimals(9)
        self.delayD = QDoubleSpinBox(); self.delayD.setDecimals(9)
        # Channel A defaults
        self.widthA.setValue(1e-6)
        self.delayA.setValue(0)

        # Channel B defaults
        self.widthB.setValue(1e-6)
        self.delayB.setValue(0)

        # Channel C defaults
        self.widthC.setValue(40e-6)
        self.delayC.setValue(0)

        # Channel D defaults
        self.widthD.setValue(40e-6)
        self.delayD.setValue(0)
        # Add labeled rows
        form.addRow("Width A:", self.widthA)
        form.addRow("Delay A:", self.delayA)
        form.addRow("Width B:", self.widthB)
        form.addRow("Delay B:", self.delayB)
        form.addRow("Width C:", self.widthC)
        form.addRow("Delay C:", self.delayC)
        form.addRow("Width D:", self.widthD)
        form.addRow("Delay D:", self.delayD)

        layout.addLayout(form)

        # --------------------------- Channel Enable Toggles ----------------
        enable_row = QHBoxLayout()
        self.btn_en_a = QPushButton("CHA Enabled"); self.btn_en_a.setCheckable(True); self.btn_en_a.setChecked(True)
        self.btn_en_b = QPushButton("CHB Enabled"); self.btn_en_b.setCheckable(True); self.btn_en_b.setChecked(True)
        self.btn_en_c = QPushButton("CHC Enabled"); self.btn_en_c.setCheckable(True); self.btn_en_c.setChecked(True)
        self.btn_en_d = QPushButton("CHD Enabled"); self.btn_en_d.setCheckable(True); self.btn_en_d.setChecked(True)
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
        form.addRow(QLabel("Trigger Source:"))
        self.trig_source = QComboBox()
        self.trig_source.addItems(["EXT", "INT"])
        form.addRow(self.trig_source)

        form.addRow(QLabel("Trigger Slope:"))
        self.trig_slope = QComboBox()
        self.trig_slope.addItems(["RIS", "FALL"])
        form.addRow(self.trig_slope)

        form.addRow(QLabel("Trigger Level (V):"))
        self.trig_level = QDoubleSpinBox()
        self.trig_level.setDecimals(3)
        self.trig_level.setRange(0.0, 5.0)
        self.trig_level.setValue(2.50)
        form.addRow(self.trig_level)

        self.btn_apply_trigger = QPushButton("Apply Trigger Settings")
        layout.addWidget(self.btn_apply_trigger)
