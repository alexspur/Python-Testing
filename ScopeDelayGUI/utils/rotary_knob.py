from PyQt6.QtWidgets import QWidget, QFrame, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QMouseEvent


class RotaryKnobSwitch(QWidget):
    """
    A round ON/OFF switch that acts like a knob:
        - Click to toggle
        - Changes lamp color (green = ON, gray = OFF)
        - Emits stateChanged(bool)
    """

    from PyQt6.QtCore import pyqtSignal
    stateChanged = pyqtSignal(bool)

    def __init__(self, label="Switch", size=40):
        super().__init__()

        self.state = False
        self.size = size

        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        self.setLayout(layout)

        # Knob body (clickable frame)
        self.knob = QFrame()
        self.knob.setFixedSize(size, size)
        self.knob.setStyleSheet(self._style(False))
        layout.addWidget(self.knob)

        # Label text
        self.label = QLabel(label)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

    # -------------------------
    # Style helper
    # -------------------------
    def _style(self, on):
        radius = int(self.size / 2)
        color = "#00CC22" if on else "#444444"
        return (
            f"background-color: {color}; "
            f"border-radius: {radius}px; "
            f"border: 2px solid black;"
        )

    # -------------------------
    # Mouse click toggles switch
    # -------------------------
    def mousePressEvent(self, e: QMouseEvent):
        self.set_on(not self.state)

    # -------------------------
    # Public setter
    # -------------------------
    def set_on(self, on: bool):
        self.state = on
        self.knob.setStyleSheet(self._style(on))
        self.stateChanged.emit(on)
