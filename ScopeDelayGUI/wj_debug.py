# main_wj_debug.py

import sys
from PyQt6.QtWidgets import QApplication
from gui.wj_debug_window import WJDebugWindow


def main():
    app = QApplication(sys.argv)
    win = WJDebugWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
