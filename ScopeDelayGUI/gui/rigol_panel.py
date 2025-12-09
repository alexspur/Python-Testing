# gui/rigol_panel.py
from PyQt6.QtWidgets import (
    QWidget, QGroupBox, QGridLayout, QPushButton, QLabel
)
from utils.status_lamp import StatusLamp
class RigolPanel(QGroupBox):
    def __init__(self):
        super().__init__("Rigol Oscilloscopes")
        layout = QGridLayout()
        self.setLayout(layout)

        # ⭐ NEW: Status Lamp
        self.lamp = StatusLamp(size=14)
        layout.addWidget(self.lamp)


        # --- BUTTONS ---
        self.btn_r1 = QPushButton("Connect Rigol #1")
        self.btn_r2 = QPushButton("Connect Rigol #2")
        self.btn_r3 = QPushButton("Connect Rigol #3")

        # ⭐ NEW SINGLE-CAPTURE BUTTONS
        self.btn_r1_single = QPushButton("R1 SINGLE")
        self.btn_r2_single = QPushButton("R2 SINGLE")
        self.btn_r3_single = QPushButton("R3 SINGLE")


        self.btn_r1_capture = QPushButton("Capture R1")
        self.btn_r2_capture = QPushButton("Capture R2")
        self.btn_r3_capture = QPushButton("Capture R3")


        # Main capture all button
        self.btn_capture = QPushButton("Capture All Scopes")

        # --- LAYOUT ---
        layout.addWidget(QLabel("Rigol #1:"), 0, 0)
        layout.addWidget(self.btn_r1, 0, 1)
        layout.addWidget(self.btn_r1_single, 0, 2)

        layout.addWidget(QLabel("Rigol #2:"), 1, 0)
        layout.addWidget(self.btn_r2, 1, 1)
        layout.addWidget(self.btn_r2_single, 1, 2)

        layout.addWidget(QLabel("Rigol #3:"), 2, 0)
        layout.addWidget(self.btn_r3, 2, 1)
        layout.addWidget(self.btn_r3_single, 2, 2)


        layout.addWidget(self.btn_r1_capture, 0, 3)
        layout.addWidget(self.btn_r2_capture, 1, 3)
        layout.addWidget(self.btn_r3_capture, 2, 3)
        # ⭐ Status lamps for each Rigol
        self.lamp_r1 = StatusLamp(size=14)
        self.lamp_r2 = StatusLamp(size=14)
        self.lamp_r3 = StatusLamp(size=14)

        # layout.addWidget(self.lamp_r1)
        # layout.addWidget(self.lamp_r2)
        # layout.addWidget(self.lamp_r3)
        layout.addWidget(self.lamp_r1, 0, 4)
        layout.addWidget(self.lamp_r2, 1, 4)
        layout.addWidget(self.lamp_r3, 2, 4)




        self.btn_r1_disconnect = QPushButton("Disconnect R1")
        # layout.addWidget(self.btn_r1_disconnect)
        layout.addWidget(self.btn_r1_disconnect, 0, 5)

        self.btn_r2_disconnect = QPushButton("Disconnect R2")
        # layout.addWidget(self.btn_r2_disconnect)
        layout.addWidget(self.btn_r2_disconnect, 1, 5)

        self.btn_r3_disconnect = QPushButton("Disconnect R3")
        # layout.addWidget(self.btn_r3_disconnect)
        layout.addWidget(self.btn_r3_disconnect, 2, 5)

        # Capture all button
        layout.addWidget(self.btn_capture, 3, 0, 1, 3)

        self.btn_export = QPushButton("Export Waveforms to CSV")
        layout.addWidget(self.btn_export)

