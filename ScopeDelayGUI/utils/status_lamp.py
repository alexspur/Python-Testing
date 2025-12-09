from PyQt6.QtWidgets import QWidget, QLabel, QHBoxLayout, QFrame
from PyQt6.QtCore import Qt


class StatusLamp(QWidget):
    def __init__(self, size=14, text=""):
        super().__init__()

        self.size = size
        self.color = "gray"
        self.text = text

        layout = QHBoxLayout()
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(6)
        self.setLayout(layout)

        # Status label
        self.label = QLabel(text)
        self.label.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Circular lamp frame
        self.lamp = QFrame()
        self.lamp.setFixedSize(size, size)
        self.lamp.setStyleSheet(self._make_style("gray"))

        layout.addWidget(self.label)
        layout.addWidget(self.lamp)

    # ---------------------------------------------------
    # Helper to make the round lamp stylesheet
    # ---------------------------------------------------
    def _make_style(self, color):
        radius = int(self.size / 2)
        return (
            f"background-color: {color}; "
            f"border-radius: {radius}px; "
            f"border: 1px solid #222;"
        )

    # ---------------------------------------------------
    # Public API for updating the lamp
    # ---------------------------------------------------
    def set_status(self, color, text=""):
        # Accept common names
        color_map = {
            "green": "#00CC22",
            "red":   "#CC0000",
            "yellow": "#FFCC00",
            "gray": "#555555"
        }

        if color in color_map:
            color = color_map[color]

        self.lamp.setStyleSheet(self._make_style(color))

        if text:
            self.label.setText(text)
