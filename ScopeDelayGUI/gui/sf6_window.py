# gui/sf6_window.py
from PyQt6.QtWidgets import (QMainWindow, QVBoxLayout, QWidget, QLabel,
                              QSplitter, QGroupBox, QSizePolicy)
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

        # Use a horizontal splitter to allow resizing between SF6 and WJ sections
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # ========================================
        # SF6 GROUP BOX (LEFT SECTION)
        # ========================================
        sf6_group = QGroupBox("SF6 Marx Generator Control")
        sf6_group_font = QFont("Arial", 10)
        sf6_group_font.setBold(True)
        sf6_group.setFont(sf6_group_font)
        sf6_layout = QVBoxLayout()
        sf6_layout.setContentsMargins(5, 10, 5, 5)
        sf6_group.setLayout(sf6_layout)

        self.sf6_panel = SF6Panel()
        sf6_layout.addWidget(self.sf6_panel)

        splitter.addWidget(sf6_group)

        # ========================================
        # WJ PLOT GROUP BOX (RIGHT SECTION)
        # ========================================
        wj_group = QGroupBox("WJ Power Supply Monitor")
        wj_group_font = QFont("Arial", 10)
        wj_group_font.setBold(True)
        wj_group.setFont(wj_group_font)
        wj_layout = QVBoxLayout()
        wj_layout.setContentsMargins(5, 10, 5, 5)
        wj_group.setLayout(wj_layout)

        # WJ Plot widget
        self.wj_plot_widget = pg.PlotWidget(background='w')
        self.wj_plot_widget.getPlotItem().setContentsMargins(10, 10, 10, 10)
        self.wj_plot_widget.showGrid(x=True, y=True)
        self.wj_plot_widget.addLegend()
        self.wj_plot_widget.setMinimumHeight(300)
        wj_layout.addWidget(self.wj_plot_widget)

        splitter.addWidget(wj_group)

        # Set initial splitter proportions (50% SF6, 50% WJ)
        splitter.setSizes([450, 450])

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

        self.wj_plot_widget.getAxis('left').setStyle(tickFont=font)
        self.wj_plot_widget.getAxis('bottom').setStyle(tickFont=font)

        self.wj_plot_widget.setLabel('left', 'Voltage (kV) / Current (mA)',
                                      **{'font-size': '12pt', 'font-family': 'Times New Roman', 'font-weight': 'bold'})
        self.wj_plot_widget.setLabel('bottom', 'Time (s)',
                                      **{'font-size': '12pt', 'font-family': 'Times New Roman', 'font-weight': 'bold'})
