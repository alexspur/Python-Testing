# gui/analysis_window.py
"""One reusable, non-modal window showing the latest shot's analysis figure.

The image is scaled to fit the window with its aspect ratio kept, and
re-scaled on every resize. "Open full size" hands the PNG to the system
viewer and "Open folder" opens the session folder in Explorer.
"""

import os
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)


def open_with_system(target):
    """Open a file or folder with the system default (Windows only)."""
    if hasattr(os, "startfile"):
        os.startfile(str(target))  # type: ignore[attr-defined]


class AnalysisPlotWindow(QWidget):
    def __init__(self, parent=None):
        # A top-level window of its own: non-modal, resizable, reused.
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("Shot analysis")
        self.resize(1100, 760)
        self.path = None
        self._pixmap = None

        layout = QVBoxLayout(self)
        self.caption = QLabel("No analysis yet.")
        self.caption.setStyleSheet("font-weight:bold;")
        self.caption.setWordWrap(True)
        layout.addWidget(self.caption)

        self.image = QLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(200, 150)
        # Ignored: the label takes the size the window gives it. Without
        # this a scaled pixmap grows the label's size hint, which grows the
        # window, which scales the pixmap again.
        self.image.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        layout.addWidget(self.image, 1)

        row = QHBoxLayout()
        self.btn_full = QPushButton("Open full size")
        self.btn_full.clicked.connect(self.open_full_size)
        self.btn_folder = QPushButton("Open folder")
        self.btn_folder.clicked.connect(self.open_folder)
        row.addWidget(self.btn_full)
        row.addWidget(self.btn_folder)
        row.addStretch()
        layout.addLayout(row)

    def show_image(self, path, caption=""):
        """Load a PNG and fit it to the window. A file that will not load
        keeps the window usable and says so in the caption."""
        self.path = str(path)
        name = Path(self.path).name
        pm = QPixmap(self.path)
        self._pixmap = None if pm.isNull() else pm
        if self._pixmap is None:
            self.caption.setText(f"{caption + ' - ' if caption else ''}could not load {name}")
            self.image.setText(f"could not load {self.path}")
        else:
            self.caption.setText(caption or name)
        self.setWindowTitle(f"Shot analysis - {name}")
        self.btn_full.setEnabled(self._pixmap is not None)
        self._rescale()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self):
        if self._pixmap is None:
            return
        self.image.setPixmap(self._pixmap.scaled(
            self.image.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))

    def open_full_size(self):
        if self.path:
            open_with_system(self.path)

    def open_folder(self):
        if self.path:
            open_with_system(Path(self.path).parent)
