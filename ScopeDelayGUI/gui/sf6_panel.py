from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel
)
from PyQt6.QtCore import Qt
from gui.gauge_widget import GaugeWidget


class SF6Panel(QGroupBox):
    """SF6 dome pressure monitor.

    The Marx valve relays and the Portenta analog inputs are gone — the
    Mega now controls everything. The only live readout left here is the
    SF6 dome pressure, which main_window._on_glassman_mega_parsed pushes
    into self.ai_ch2 from the Mega's A5 reading (d["psi"]).
    """

    def __init__(self, pressure_min=0, pressure_max=100):
        super().__init__("SF6 Dome Pressure")

        layout = QVBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setLayout(layout)

        self.label_ai = QLabel("SF6 Dome Pressure (Mega A5):")
        layout.addWidget(self.label_ai)

        # Live dome pressure gauge, fed by the Mega. Range is configurable from
        # main.py (PRESSURE_GAUGE_MIN_PSI / PRESSURE_GAUGE_MAX_PSI).
        gauges = QHBoxLayout()
        gauges.setSpacing(12)
        self.ai_ch2 = GaugeWidget(min_value=pressure_min, max_value=pressure_max, label="PSI", size=120)
        gauges.addWidget(self.ai_ch2)
        gauges.addStretch()
        layout.addLayout(gauges)

        layout.addStretch(1)
