from PyQt6.QtWidgets import QApplication
from gui.main_window import ScopeDelayMainWindow
import sys



if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = ScopeDelayMainWindow()
    window.show()

    sys.exit(app.exec())
 