from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QGridLayout
)
from PyQt6.QtCore import Qt
from utils.status_lamp import StatusLamp
from utils.rotary_knob import RotaryKnobSwitch
from gui.gauge_widget import GaugeWidget


class SF6Panel(QGroupBox):
    def __init__(self):
        super().__init__("SF6 Marx Generator Control")

        layout = QVBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setLayout(layout)
        
        # Arduino connection status
        self.lamp = StatusLamp(size=14)
        layout.addWidget(self.lamp)

        # Arduino connect row (compact single row)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.label = QLabel("COM Port:")
        self.port_list = QComboBox()
        self.btn_connect = QPushButton("Connect")
        self.btn_disconnect = QPushButton("Disconnect")
        row.addWidget(self.label)
        row.addWidget(self.port_list)
        row.addWidget(self.btn_connect)
        row.addWidget(self.btn_disconnect)
        layout.addLayout(row)

        # Analog live readout
        self.label_ai = QLabel("Live Analog Inputs (4-20 mA):")
        layout.addWidget(self.label_ai)

        # Gauges side by side to minimize height (0-200 PSI range for 4-20mA)
        gauges = QHBoxLayout()
        gauges.setSpacing(12)
        self.ai_ch0 = GaugeWidget(min_value=0, max_value=200, label="PSI", size=120)
        self.ai_ch1 = GaugeWidget(min_value=0, max_value=200, label="PSI", size=120)
        self.ai_ch2 = GaugeWidget(min_value=0, max_value=200, label="PSI", size=120)
        gauges.addWidget(self.ai_ch0)
        gauges.addWidget(self.ai_ch1)
        gauges.addWidget(self.ai_ch2)
        layout.addLayout(gauges)

        # Marx switches
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        self.switches = []
        names = [
            "Marx1 Supply", "Marx1 Return",
            "Marx2 Supply", "Marx2 Return",
            "Marx3 Supply", "Marx3 Return",
            "Marx4 Supply", "Marx4 Return"
        ]

        for i, name in enumerate(names):
            knob = RotaryKnobSwitch(label=name, size=36)
            self.switches.append(knob)
            grid.addWidget(knob, i // 2, i % 2)

        layout.addLayout(grid)
        layout.addStretch(1)
