from PyQt6.QtWidgets import (
    QMainWindow, QVBoxLayout, QWidget, QLabel,
    QSplitter, QGroupBox, QSizePolicy,
    QHBoxLayout, QGridLayout, QDoubleSpinBox, QPushButton, QComboBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from gui.sf6_panel import SF6Panel
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
        # Top row: SF6 panel (left) and WJ controls (right)
        # -------------------------------------------
        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(top_splitter)

        # SF6 group
        sf6_group = QGroupBox("SF6 Marx Generator Control")
        sf6_group_font = QFont("Arial", 10)
        sf6_group_font.setBold(True)
        sf6_group.setFont(sf6_group_font)
        sf6_layout = QVBoxLayout()
        sf6_layout.setContentsMargins(5, 10, 5, 5)
        sf6_group.setLayout(sf6_layout)

        self.sf6_panel = SF6Panel()
        sf6_layout.addWidget(self.sf6_panel)

        top_splitter.addWidget(sf6_group)

        # WJ controls group
        wj_group = QGroupBox("WJ Controls")
        wj_group_font = QFont("Arial", 10)
        wj_group_font.setBold(True)
        wj_group.setFont(wj_group_font)
        wj_layout = QVBoxLayout()
        wj_layout.setContentsMargins(8, 8, 8, 8)
        wj_layout.setSpacing(10)
        wj_group.setLayout(wj_layout)

        # Live numeric readouts
        values = QGridLayout()
        values.setHorizontalSpacing(10)
        values.setVerticalSpacing(6)
        values.setContentsMargins(4, 0, 4, 0)
        self.kv1_value = QLabel("0.00 kV")
        self.ma1_value = QLabel("0.00 mA")
        self.kv2_value = QLabel("0.00 kV")
        self.ma2_value = QLabel("0.00 mA")
        values.addWidget(QLabel("WJ1 kV:"), 0, 0)
        values.addWidget(self.kv1_value, 0, 1)
        values.addWidget(QLabel("WJ1 mA:"), 0, 2)
        values.addWidget(self.ma1_value, 0, 3)
        values.addWidget(QLabel("WJ2 kV:"), 1, 0)
        values.addWidget(self.kv2_value, 1, 1)
        values.addWidget(QLabel("WJ2 mA:"), 1, 2)
        values.addWidget(self.ma2_value, 1, 3)
        wj_layout.addLayout(values)

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

        for i in range(2):
            label = QLabel(f"WJ{i+1} Port:")
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

        top_splitter.addWidget(wj_group)

        # -------------------------------------------
        # Bottom plot spanning width
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

        main_layout.addWidget(plot_group)

        # Apply font styling to WJ plot
        self._apply_wj_font_styling()

        # Curves for WJ data (will be populated by main window)
        self.kv1_curve = self.wj_plot_widget.plot(pen=pg.mkPen('y', width=2), name="WJ1 kV")
        self.ma1_curve = self.wj_plot_widget.plot(pen=pg.mkPen('c', width=2), name="WJ1 mA")
        self.kv2_curve = self.wj_plot_widget.plot(pen=pg.mkPen('r', width=2), name="WJ2 kV")
        self.ma2_curve = self.wj_plot_widget.plot(pen=pg.mkPen('m', width=2), name="WJ2 mA")

    def _apply_wj_font_styling(self):
        """Apply Times New Roman bold font to WJ plot axes"""
        font = QFont("Times New Roman", 12)
        font.setBold(True)

        left_axis = self.wj_plot_widget.getAxis('left')
        bottom_axis = self.wj_plot_widget.getAxis('bottom')

        for axis in (left_axis, bottom_axis):
            axis.setStyle(tickFont=font)
            axis.setPen('k')
            axis.setTextPen('k')

        self.wj_plot_widget.setLabel('left', 'Voltage (kV) / Current (mA)',
                                      **{'font-size': '12pt', 'font-family': 'Times New Roman', 'font-weight': 'bold'})
        self.wj_plot_widget.setLabel('bottom', 'Time (s)',
                                      **{'font-size': '12pt', 'font-family': 'Times New Roman', 'font-weight': 'bold'})
