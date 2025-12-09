# gui/sf6_window.py
from PyQt6.QtWidgets import QMainWindow, QVBoxLayout, QWidget
from gui.sf6_panel import SF6Panel


class SF6Window(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SF6 Marx Generator Control")
        self.resize(600, 800)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout()
        central.setLayout(layout)

        self.sf6_panel = SF6Panel()
        layout.addWidget(self.sf6_panel)
