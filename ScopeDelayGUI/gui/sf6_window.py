from PyQt6.QtWidgets import (
    QMainWindow, QVBoxLayout, QWidget, QLabel,
    QSplitter, QGroupBox, QSizePolicy,
    QHBoxLayout, QGridLayout, QDoubleSpinBox, QPushButton, QComboBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from gui.sf6_panel import SF6Panel
from gui.gauge_widget import GaugeWidget
import pyqtgraph as pg


class SF6Window(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SF6 Marx Generator Control + WJ Power Supplies")

        # Set window flags to make it appear in taskbar independently
        from PyQt6.QtCore import Qt
        self.setWindowFlags(Qt.WindowType.Window)

        self.resize(900, 1080)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout()
        central.setLayout(main_layout)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # -------------------------------------------
        # VERTICAL SPLITTER: 3 equal sections
        # -------------------------------------------
        vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(vertical_splitter)

        # -------------------------------------------
        # SECTION 1: SF6 Marx Generator Control (TOP)
        # -------------------------------------------
        sf6_group = QGroupBox("SF6 Marx Generator Control")
        sf6_group_font = QFont("Arial", 10)
        sf6_group_font.setBold(True)
        sf6_group.setFont(sf6_group_font)
        sf6_layout = QVBoxLayout()
        sf6_layout.setContentsMargins(5, 10, 5, 5)
        sf6_group.setLayout(sf6_layout)

        self.sf6_panel = SF6Panel()
        sf6_layout.addWidget(self.sf6_panel)

        vertical_splitter.addWidget(sf6_group)

        # -------------------------------------------
        # SECTION 2: WJ Controls (MIDDLE)
        # -------------------------------------------
        wj_group = QGroupBox("WJ Controls")
        wj_group_font = QFont("Arial", 10)
        wj_group_font.setBold(True)
        wj_group.setFont(wj_group_font)
        wj_layout = QVBoxLayout()
        wj_layout.setContentsMargins(8, 8, 8, 8)
        wj_layout.setSpacing(10)
        wj_group.setLayout(wj_layout)

        # Gauge displays instead of text labels
        gauges_layout = QGridLayout()
        gauges_layout.setHorizontalSpacing(10)
        gauges_layout.setVerticalSpacing(6)
        gauges_layout.setContentsMargins(4, 0, 4, 0)

        # WJ1 gauges
        self.kv1_gauge = GaugeWidget(min_value=0, max_value=100, label="kV", size=120)
        self.ma1_gauge = GaugeWidget(min_value=0, max_value=6, label="mA", size=120)

        # WJ2 gauges
        self.kv2_gauge = GaugeWidget(min_value=0, max_value=100, label="kV", size=120)
        self.ma2_gauge = GaugeWidget(min_value=0, max_value=6, label="mA", size=120)

        gauges_layout.addWidget(QLabel("Negative:"), 0, 0)
        gauges_layout.addWidget(self.kv1_gauge, 0, 1)
        gauges_layout.addWidget(self.ma1_gauge, 0, 2)
        gauges_layout.addWidget(QLabel("Positive:"), 1, 0)
        gauges_layout.addWidget(self.kv2_gauge, 1, 1)
        gauges_layout.addWidget(self.ma2_gauge, 1, 2)
        wj_layout.addLayout(gauges_layout)

        # Program row
        program_row = QHBoxLayout()
        program_row.setSpacing(6)
        program_row.addWidget(QLabel("Voltage (kV):"))
        self.program_voltage = QDoubleSpinBox()
        self.program_voltage.setRange(0, 100)
        self.program_voltage.setDecimals(2)
        self.program_voltage.setValue(50.0)
        program_row.addWidget(self.program_voltage)

        program_row.addWidget(QLabel("Current (mA):"))
        self.program_current = QDoubleSpinBox()
        self.program_current.setRange(0, 6)
        self.program_current.setDecimals(2)
        self.program_current.setValue(2.0)
        program_row.addWidget(self.program_current)

        self.btn_apply_program = QPushButton("Apply Program")
        program_row.addWidget(self.btn_apply_program)
        wj_layout.addLayout(program_row)

        # Global control buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self.btn_hv_on = QPushButton("HV ON")
        self.btn_hv_off = QPushButton("HV OFF")
        self.btn_reset = QPushButton("RESET")
        self.btn_read = QPushButton("READ")
        btn_row.addWidget(self.btn_hv_on)
        btn_row.addWidget(self.btn_hv_off)
        btn_row.addWidget(self.btn_reset)
        btn_row.addWidget(self.btn_read)
        wj_layout.addLayout(btn_row)

        # Per-unit connect/disconnect
        conn_grid = QGridLayout()
        conn_grid.setHorizontalSpacing(8)
        conn_grid.setVerticalSpacing(6)
        self.wj_port_combos = []
        self.btn_wj_connect = []
        self.btn_wj_disconnect = []

        port_labels = ["Negative Port:", "Positive Port:"]
        for i in range(2):
            label = QLabel(port_labels[i])
            combo = QComboBox()
            combo.addItem("No COM ports")
            btn_c = QPushButton("Connect")
            btn_d = QPushButton("Disconnect")
            self.wj_port_combos.append(combo)
            self.btn_wj_connect.append(btn_c)
            self.btn_wj_disconnect.append(btn_d)

            conn_grid.addWidget(label, i, 0)
            conn_grid.addWidget(combo, i, 1)
            conn_grid.addWidget(btn_c, i, 2)
            conn_grid.addWidget(btn_d, i, 3)

        wj_layout.addLayout(conn_grid)

        vertical_splitter.addWidget(wj_group)

        # -------------------------------------------
        # SECTION 3: WJ Power Supply Monitor Plot (BOTTOM)
        # -------------------------------------------
        plot_group = QGroupBox("WJ Power Supply Monitor")
        plot_layout = QVBoxLayout()
        plot_layout.setContentsMargins(8, 8, 8, 8)
        plot_layout.setSpacing(6)
        plot_group.setLayout(plot_layout)

        self.wj_plot_widget = pg.PlotWidget(background='w')
        self.wj_plot_widget.getPlotItem().setContentsMargins(10, 10, 10, 10)
        self.wj_plot_widget.showGrid(x=True, y=True)
        self.wj_plot_widget.addLegend()
        self.wj_plot_widget.setLimits(yMin=0, xMin=0)
        self.wj_plot_widget.setXRange(0, 60)
        self.wj_plot_widget.setYRange(0, 110)  # up to ~100 kV with headroom
        self.wj_plot_widget.setMinimumHeight(280)
        plot_layout.addWidget(self.wj_plot_widget)

        vertical_splitter.addWidget(plot_group)

        # Set equal sizes for all 3 sections
        vertical_splitter.setSizes([360, 360, 360])

        # Apply font styling to WJ plot
        self._apply_wj_font_styling()

        # Curves for WJ data with THICKER lines (width=5 instead of 2)
        self.kv1_curve = self.wj_plot_widget.plot(pen=pg.mkPen('y', width=5), name="WJ1 kV")
        self.ma1_curve = self.wj_plot_widget.plot(pen=pg.mkPen('c', width=5), name="WJ1 mA")
        self.kv2_curve = self.wj_plot_widget.plot(pen=pg.mkPen('r', width=5), name="WJ2 kV")
        self.ma2_curve = self.wj_plot_widget.plot(pen=pg.mkPen('m', width=5), name="WJ2 mA")

        # Style legend with bold black font
        legend = self.wj_plot_widget.plotItem.legend
        legend.setLabelTextColor('k')
        legend_font = QFont("Times New Roman", 14)
        legend_font.setBold(True)
        for item in legend.items:
            for single_item in item:
                if isinstance(single_item, pg.graphicsItems.LabelItem.LabelItem):
                    single_item.setText(single_item.text, color='k', size='14pt', bold=True)

    def _apply_wj_font_styling(self):
        """Apply Times New Roman bold font to WJ plot axes with LARGER font sizes"""
        font = QFont("Times New Roman", 16)  # Increased from 12 to 16
        font.setBold(True)

        left_axis = self.wj_plot_widget.getAxis('left')
        bottom_axis = self.wj_plot_widget.getAxis('bottom')

        for axis in (left_axis, bottom_axis):
            axis.setStyle(tickFont=font)
            axis.setPen('k')
            axis.setTextPen('k')

        # Larger label font sizes (16pt instead of 12pt)
        self.wj_plot_widget.setLabel('left', 'Voltage (kV) / Current (mA)',
                                      **{'font-size': '16pt', 'font-family': 'Times New Roman', 'font-weight': 'bold'})
        self.wj_plot_widget.setLabel('bottom', 'Time (s)',
                                      **{'font-size': '16pt', 'font-family': 'Times New Roman', 'font-weight': 'bold'})
