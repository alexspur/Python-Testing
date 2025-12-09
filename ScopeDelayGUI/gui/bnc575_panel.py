from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton,
    QFormLayout, QDoubleSpinBox
)
from utils.status_lamp import StatusLamp

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

        # --------------------------- Apply / Read / Arm ----------------
        row2 = QHBoxLayout()
        self.btn_apply = QPushButton("Apply Settings")
        self.btn_read  = QPushButton("Read Settings")
        self.btn_arm   = QPushButton("Arm (EXT TRIG)")
        row2.addWidget(self.btn_apply)
        row2.addWidget(self.btn_read)
        row2.addWidget(self.btn_arm)

        layout.addLayout(row2)
