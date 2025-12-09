from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtGui import QPainter, QPen, QColor
from PyQt6.QtCore import Qt, QRectF


class GaugeWidget(QWidget):
    def __init__(self, min_value=0, max_value=200, label="PSI", size=180):
        super().__init__()
        self.min_value = min_value
        self.max_value = max_value
        self.value = 0
        self.label = label
        self.size = size

        # Force compact dimensions
        self.setFixedSize(size, size)

        self.text_label = QLabel(f"0 {label}")
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_label.setStyleSheet("font-size: 16px; font-weight: bold; color: white;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.text_label)

    def update_value(self, val):
        self.value = max(self.min_value, min(self.max_value, val))
        self.text_label.setText(f"{self.value:.1f} {self.label}")
        self.repaint()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.size
        h = self.size * 0.7  # arc height

        # Center arc in widget
        rect = QRectF(10, 10, w - 20, h)

        start_angle = 180 * 16
        span_angle = -180 * 16

        # background arc
        pen = QPen(QColor(80, 80, 80), 14)
        painter.setPen(pen)
        painter.drawArc(rect, start_angle, span_angle)

        # compute colored arc length
        percent = (self.value - self.min_value) / (self.max_value - self.min_value)
        angle = span_angle * percent

        # Color logic (same rules)
        if self.value < 50:
            color = QColor(0, 150, 255)
        elif self.value < 150:
            color = QColor(0, 255, 0)
        else:
            color = QColor(255, 50, 50)

        pen = QPen(color, 14)
        painter.setPen(pen)
        painter.drawArc(rect, start_angle, int(angle))

        painter.end()
