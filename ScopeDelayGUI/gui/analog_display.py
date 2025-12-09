# gui/analog_display.py
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar

class AnalogDisplay(QWidget):
    def __init__(self, name):
        super().__init__()

        layout = QVBoxLayout()
        self.setLayout(layout)

        # self.label = QLabel(f"{name}: --- mA")
        self.label = QLabel(f"{name}: --- psi")
        self.label.setStyleSheet("font-size: 14px; font-weight: bold;")

        self.bar = QProgressBar()
        # self.bar.setRange(0, 30000)  # stored in µA internally
        self.bar.setRange(0, 200)  # 0–200 PSI
        self.bar.setValue(0)

        layout.addWidget(self.label)
        layout.addWidget(self.bar)

    # def update(self, mA: float):
    #     self.label.setText(f"{mA:.2f} mA")
    #     self.bar.setValue(int(mA * 1000))

    #     # Color logic
    #     if mA < 3:
    #         self.bar.setStyleSheet("QProgressBar::chunk { background-color: #007bff; }")  # blue
    #     elif mA < 18:
    #         self.bar.setStyleSheet("QProgressBar::chunk { background-color: #28a745; }")  # green
    #     else:
    #         self.bar.setStyleSheet("QProgressBar::chunk { background-color: #dc3545; }")  # red
    def update(self, psi: float):
        self.label.setText(f"{psi:.1f} psi")
        self.bar.setValue(int(psi))

        # Optional color logic
        if psi < 50:
            self.bar.setStyleSheet("QProgressBar::chunk { background-color: #007bff; }")  # blue (low)
        elif psi < 150:
            self.bar.setStyleSheet("QProgressBar::chunk { background-color: #28a745; }")  # green (normal)
        else:
            self.bar.setStyleSheet("QProgressBar::chunk { background-color: #dc3545; }")  # red (high)

