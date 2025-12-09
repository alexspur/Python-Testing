import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QPushButton, QLabel, QTextEdit, QComboBox, QGridLayout,
    QDoubleSpinBox, QFrame, QGroupBox, QFormLayout, QCheckBox
)
from PyQt6.QtCore import Qt
import pyqtgraph as pg



class ScopeDelayGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Scope + Delay + SF6 Control")
        self.setGeometry(100, 100, 1700, 900)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout()
        central.setLayout(main_layout)

        # Tabs
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # Two main tabs
        self.scope_tab = QWidget()
        self.sf6_tab = QWidget()
        self.tabs.addTab(self.scope_tab, "Scope + Delay")
        self.tabs.addTab(self.sf6_tab, "SF6 Control")

        # Build both tabs
        self.build_scope_tab()
        self.build_sf6_tab()


    # ----------------------------------------------------------------------
    #  BUILD SCOPE TAB (LEFT CONTROL PANELS + RIGHT SCOPE DISPLAYS)
    # ----------------------------------------------------------------------
    def build_scope_tab(self):
        layout = QHBoxLayout()
        self.scope_tab.setLayout(layout)

        # ------------------------------------------------------------------
        # LEFT SIDE — All control panels
        # ------------------------------------------------------------------
        left_column = QVBoxLayout()
        layout.addLayout(left_column, 35)

        # DG535 panel
        left_column.addWidget(self.build_dg535_panel())

        # BNC575 panel
        left_column.addWidget(self.build_bnc575_panel())

        # Rigol connect panel
        left_column.addWidget(self.build_rigol_panel())

        # Status + log panel
        left_column.addLayout(self.build_status_and_log())

        # ------------------------------------------------------------------
        # RIGHT SIDE — 3 oscilloscope displays
        # ------------------------------------------------------------------
        right_column = QVBoxLayout()
        layout.addLayout(right_column, 65)

        # Each plot area
        self.scope1 = self.make_scope_plot("Rigol Scope 1")
        self.scope2 = self.make_scope_plot("Rigol Scope 2")
        self.scope3 = self.make_scope_plot("Rigol Scope 3")

        right_column.addWidget(self.scope1)
        right_column.addWidget(self.scope2)
        right_column.addWidget(self.scope3)



    # ----------------------------------------------------------------------
    #  PANELS
    # ----------------------------------------------------------------------

    # ---------------- DG535 panel ----------------
    def build_dg535_panel(self):
        box = QGroupBox("DG535 Control")
        layout = QVBoxLayout()
        box.setLayout(layout)

        # Connect + Fire buttons
        hl = QHBoxLayout()
        self.btn_dg_connect = QPushButton("Connect DG535")
        self.btn_dg_fire = QPushButton("Fire DG535")

        hl.addWidget(self.btn_dg_connect)
        hl.addWidget(self.btn_dg_fire)
        layout.addLayout(hl)

        # Timing fields (Delay A, Delay B, Width A, Width B)
        form = QFormLayout()

        self.dg_delayA = QDoubleSpinBox(); self.dg_delayA.setDecimals(9)
        self.dg_delayB = QDoubleSpinBox(); self.dg_delayB.setDecimals(9)
        self.dg_widthA = QDoubleSpinBox(); self.dg_widthA.setDecimals(9)
        self.dg_widthB = QDoubleSpinBox(); self.dg_widthB.setDecimals(9)

        form.addRow("Delay A from t0:", self.dg_delayA)
        form.addRow("Delay B from t0:", self.dg_delayB)
        form.addRow("Width A:", self.dg_widthA)
        form.addRow("Width B:", self.dg_widthB)

        layout.addLayout(form)

        return box



    # ---------------- BNC575 panel ----------------
    def build_bnc575_panel(self):
        box = QGroupBox("BNC575 Control")
        layout = QVBoxLayout()
        box.setLayout(layout)

        btns = QHBoxLayout()
        self.btn_bnc_connect = QPushButton("Connect BNC575")
        self.btn_bnc_fire = QPushButton("Fire Pulse")
        btns.addWidget(self.btn_bnc_connect)
        btns.addWidget(self.btn_bnc_fire)
        layout.addLayout(btns)

        form = QFormLayout()

        self.bnc_widthA = QDoubleSpinBox(); self.bnc_widthA.setDecimals(9)
        self.bnc_delayA = QDoubleSpinBox(); self.bnc_delayA.setDecimals(9)
        self.bnc_widthB = QDoubleSpinBox(); self.bnc_widthB.setDecimals(9)
        self.bnc_delayB = QDoubleSpinBox(); self.bnc_delayB.setDecimals(9)

        form.addRow("Width A:", self.bnc_widthA)
        form.addRow("Delay A:", self.bnc_delayA)
        form.addRow("Width B:", self.bnc_widthB)
        form.addRow("Delay B:", self.bnc_delayB)

        layout.addLayout(form)

        # Apply + Read + Arm
        hl2 = QHBoxLayout()
        self.btn_bnc_apply = QPushButton("Apply Settings")
        self.btn_bnc_read = QPushButton("Read Settings")
        self.btn_bnc_arm = QPushButton("Arm")
        hl2.addWidget(self.btn_bnc_apply)
        hl2.addWidget(self.btn_bnc_read)
        hl2.addWidget(self.btn_bnc_arm)
        layout.addLayout(hl2)

        return box



    # ---------------- Rigol panel ----------------
    def build_rigol_panel(self):
        box = QGroupBox("Rigol Oscilloscopes")
        layout = QVBoxLayout()
        box.setLayout(layout)

        hl = QHBoxLayout()
        self.btn_r1 = QPushButton("Connect Rigol #1")
        self.btn_r2 = QPushButton("Connect Rigol #2")
        self.btn_r3 = QPushButton("Connect Rigol #3")
        hl.addWidget(self.btn_r1)
        hl.addWidget(self.btn_r2)
        hl.addWidget(self.btn_r3)
        layout.addLayout(hl)

        self.btn_capture = QPushButton("Capture Waveforms (All)")
        layout.addWidget(self.btn_capture)

        return box



    # ---------------- Status + log ----------------
    def build_status_and_log(self):
        layout = QVBoxLayout()

        hl = QHBoxLayout()
        self.status_label = QLabel("Status: Ready")
        self.status_lamp = QFrame()
        self.status_lamp.setFixedSize(25, 25)
        self.status_lamp.setStyleSheet("background-color: green; border-radius: 13px;")
        hl.addWidget(self.status_label)
        hl.addWidget(self.status_lamp)
        layout.addLayout(hl)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

        return layout



    # ---------------- SF6 Panel ----------------
    def build_sf6_tab(self):
        layout = QVBoxLayout()
        self.sf6_tab.setLayout(layout)

        box = QGroupBox("SF6 Marx Generator Control")
        v = QVBoxLayout()
        box.setLayout(v)

        # Arduino Connect
        h = QHBoxLayout()
        self.arduino_port = QComboBox()
        self.btn_arduino_connect = QPushButton("Connect Arduino")

        h.addWidget(QLabel("COM Port:"))
        h.addWidget(self.arduino_port)
        h.addWidget(self.btn_arduino_connect)
        v.addLayout(h)

        # 8 relay switches (4 supply, 4 return)
        grid = QGridLayout()
        self.sf6_switches = []

        labels = [
            "Marx1 Supply", "Marx1 Return",
            "Marx2 Supply", "Marx2 Return",
            "Marx3 Supply", "Marx3 Return",
            "Marx4 Supply", "Marx4 Return"
        ]

        for idx, txt in enumerate(labels):
            sw = QCheckBox(txt)
            self.sf6_switches.append(sw)
            grid.addWidget(sw, idx // 2, idx % 2)

        v.addLayout(grid)
        layout.addWidget(box)



    # ----------------------------------------------------------------------
    #  CREATE OSCILLOSCOPE PLOT
    # ----------------------------------------------------------------------
    def make_scope_plot(self, title):
        plot = pg.PlotWidget()
        plot.setTitle(title)
        plot.showGrid(x=True, y=True)
        plot.setLabel("left", "Voltage (V)")
        plot.setLabel("bottom", "Time (s)")
        return plot



# ----------------------------------------------------------------------
# MAIN APP ENTRY POINT
# ----------------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = ScopeDelayGUI()
    gui.show()
    sys.exit(app.exec())
