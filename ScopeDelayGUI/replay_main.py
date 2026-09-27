"""Shot Replay: the offline bench for the post-shot analysis.

    python replay_main.py                    logs folder from last time, or found
    python replay_main.py D:\\data\\logs       a specific logs folder
    python replay_main.py D:\\data\\logs 46    ... and load shot 46 straight away

Connects to no instruments. Replay output goes to .\\replay_output, never
into the session folders or processed_shots.
"""

import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

from gui.replay_window import ShotReplayWindow


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Same look as main.py.
    base_font = QFont("Times New Roman")
    base_font.setBold(True)
    app.setFont(base_font)
    app.setStyleSheet("""
        * {
            font-family: 'Times New Roman';
            font-weight: bold;
            color: black;
        }
    """)

    args = sys.argv[1:]
    window = ShotReplayWindow(logs_root=args[0] if args else None)
    window.show()
    if len(args) > 1:
        window.spin_shot.setValue(int(args[1]))
        QTimer.singleShot(0, window.load_number)

    sys.exit(app.exec())
