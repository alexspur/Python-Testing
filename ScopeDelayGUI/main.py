from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont
from gui.main_window import ScopeDelayMainWindow
import sys



if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Global font and color
    base_font = QFont("Times New Roman")
    base_font.setBold(True)
    app.setFont(base_font)
    app.setStyleSheet("""
        * {l
            font-family: 'Times New Roman';
            font-weight: bold;
            color: black;
        }
    """)

    window = ScopeDelayMainWindow()
    window.show()

    sys.exit(app.exec())
 
