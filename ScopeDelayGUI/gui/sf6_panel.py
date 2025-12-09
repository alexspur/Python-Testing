# gui/sf6_panel.py
from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QGridLayout
)
from utils.status_lamp import StatusLamp
from utils.rotary_knob import RotaryKnobSwitch   # ⭐ ADD THIS
from gui.analog_display import AnalogDisplay
from gui.gauge_widget import GaugeWidget


class SF6Panel(QGroupBox):
    def __init__(self):
        super().__init__("SF6 Marx Generator Control")

        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # ⭐ Arduino connection status
        self.lamp = StatusLamp(size=14)
        layout.addWidget(self.lamp)

        # Arduino Connect
        row = QHBoxLayout()
        self.label = QLabel("COM Port:")
        self.port_list = QComboBox()
        self.btn_connect = QPushButton("Connect Arduino")
        self.btn_disconnect = QPushButton("Disconnect Arduino")
        layout.addWidget(self.btn_disconnect)
        layout.addWidget(self.btn_connect)
        row.addWidget(self.label)
        row.addWidget(self.port_list)
        row.addWidget(self.btn_connect)
        layout.addLayout(row)

        # Marx switches
        grid = QGridLayout()
        # -------------------------
        # ANALOG LIVE READOUT
        # -------------------------
        self.label_ai = QLabel("Live Analog Inputs (4–20 mA):")
        layout.addWidget(self.label_ai)

        # self.ai_ch0 = AnalogDisplay("Channel 0")
        # self.ai_ch1 = AnalogDisplay("Channel 1")
        # self.ai_ch2 = AnalogDisplay("Channel 2")

        # layout.addWidget(self.ai_ch0)
        # layout.addWidget(self.ai_ch1)
        # layout.addWidget(self.ai_ch2)
        self.ai_ch0 = GaugeWidget(label="PSI", size=180)
        self.ai_ch1 = GaugeWidget(label="PSI", size=180)
        self.ai_ch2 = GaugeWidget(label="PSI", size=180)


        layout.addWidget(self.ai_ch0)
        layout.addWidget(self.ai_ch1)
        layout.addWidget(self.ai_ch2)
        # self.switches = []

        # names = [
        #     "Marx1 Supply", "Marx1 Return",
        #     "Marx2 Supply", "Marx2 Return",
        #     "Marx3 Supply", "Marx3 Return",
        #     "Marx4 Supply", "Marx4 Return"
        # ]

        # for i, name in enumerate(names):
        #     sw = QCheckBox(name)
        #     self.switches.append(sw)
        #     grid.addWidget(sw, i // 2, i % 2)
        self.switches = []
        names = [
            "Marx1 Supply", "Marx1 Return",
            "Marx2 Supply", "Marx2 Return",
            "Marx3 Supply", "Marx3 Return",
            "Marx4 Supply", "Marx4 Return"
        ]

        for i, name in enumerate(names):
            knob = RotaryKnobSwitch(label=name, size=40)
            self.switches.append(knob)
            grid.addWidget(knob, i // 2, i % 2)


        layout.addLayout(grid)
