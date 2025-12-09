from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton, QFormLayout, QDoubleSpinBox
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
        hl.addWidget(self.btn_connect)
        hl.addWidget(self.btn_fire)
        layout.addLayout(hl)

        # Timing fields
        form = QFormLayout()
        self.delayA = QDoubleSpinBox()
        self.delayB = QDoubleSpinBox()
        self.widthA = QDoubleSpinBox()
        self.widthB = QDoubleSpinBox()
        
        self.btn_disconnect = QPushButton("Disconnect")
        layout.addWidget(self.btn_disconnect)

        for w in [self.delayA, self.delayB, self.widthA, self.widthB]:
            w.setDecimals(9)
            w.setRange(0, 1)

        form.addRow("Delay A:", self.delayA)
        form.addRow("Delay B:", self.delayB)
        form.addRow("Width A:", self.widthA)
        form.addRow("Width B:", self.widthB)
        layout.addLayout(form)
