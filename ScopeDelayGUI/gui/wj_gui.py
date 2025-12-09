import sys
import serial
import serial.tools.list_ports
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QComboBox
)
from PyQt6.QtCore import QTimer


# SOH = b'\x01'      # Start of header (Ctrl+A)
# CR  = b'\r'        # Carriage return


# def make_packet(cmd: str):
#     """
#     Wrap ASCII command in proper WJ packet:
#     [SOH][ASCII][checksum][CR]
#     """
#     data = cmd.encode('ascii')
#     checksum = (sum(data) % 256)
#     return SOH + data + bytes([checksum]) + CR
SOH = b'\x01'
CR  = b'\r'

def build_cmd(core: str) -> bytes:
    """
    core: ASCII command body (e.g. 'Q', 'V', or full 'S....' string)

    Returns full packet: SOH + core + checksum_as_ascii_hex + CR
    """
    body = core.encode('ascii')
    cs = sum(body) & 0xFF          # modulo-256 checksum
    cs_ascii = f"{cs:02X}"         # e.g. 0x51 -> "51"
    return SOH + body + cs_ascii.encode('ascii') + CR


class WJGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.ser = None

        self.setWindowTitle("WJ100P6.0 USB Control")
        layout = QVBoxLayout()
        self.setLayout(layout)

        # -----------------------------
        # COM Port Select
        # -----------------------------
        h = QHBoxLayout()
        self.portBox = QComboBox()
        self.refresh_ports()
        self.btnConnect = QPushButton("Connect")
        self.btnConnect.clicked.connect(self.connect_serial)
        h.addWidget(QLabel("COM Port:"))
        h.addWidget(self.portBox)
        h.addWidget(self.btnConnect)
        layout.addLayout(h)

        # -----------------------------
        # Voltage / Current input
        # -----------------------------
        h2 = QHBoxLayout()
        self.voltageIn = QLineEdit("0")
        self.currentIn = QLineEdit("0")
        h2.addWidget(QLabel("kV Setpoint:"))
        h2.addWidget(self.voltageIn)
        h2.addWidget(QLabel("mA Setpoint:"))
        h2.addWidget(self.currentIn)
        layout.addLayout(h2)

        # -----------------------------
        # Buttons
        # -----------------------------
        h3 = QHBoxLayout()
        self.btnSend = QPushButton("Send Program")
        self.btnSend.clicked.connect(self.send_program)

        self.btnHVON = QPushButton("HV ON")
        self.btnHVON.clicked.connect(self.hv_on)

        self.btnHVOFF = QPushButton("HV OFF")
        self.btnHVOFF.clicked.connect(self.hv_off)

        self.btnReset = QPushButton("Reset")
        self.btnReset.clicked.connect(self.reset_ps)

        h3.addWidget(self.btnSend)
        h3.addWidget(self.btnHVON)
        h3.addWidget(self.btnHVOFF)
        h3.addWidget(self.btnReset)
        layout.addLayout(h3)

        # -----------------------------
        # Console
        # -----------------------------
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        layout.addWidget(self.console)

        # Timer for polling
        self.poller = QTimer()
        self.poller.timeout.connect(self.poll_status)

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------

    def refresh_ports(self):
        self.portBox.clear()
        for p in serial.tools.list_ports.comports():
            self.portBox.addItem(p.device)

    def log(self, msg):
        self.console.append(msg)

    def connect_serial(self):
        port = self.portBox.currentText()
        if not port:
            self.log("No COM port selected.")
            return

        try:
            self.ser = serial.Serial(port, 9600, timeout=0.3)
            self.log(f"[OK] Connected to {port}")
            self.poller.start(1000)     # 1-second polling (prevents HV timeout)
        except Exception as e:
            self.log(f"[ERROR] {e}")

    # ---------------------------------------------------------------------
    # Serial send helper
    # ---------------------------------------------------------------------
    def send_cmd(self, cmd: str):
        if not self.ser:
            self.log("Not connected.")
            return None
        pkt = build_cmd(cmd)
        self.ser.write(pkt)
        self.log(f">>> {cmd}")
        try:
            reply = self.ser.readline().decode(errors="ignore")
            if reply:
                self.log(f"<<< {reply}")
            return reply
        except:
            return None

    # ---------------------------------------------------------------------
    # WJ COMMANDS
    # ---------------------------------------------------------------------

    # Voltage and Current control
    # WJ interface expects HEX 0–FFF scaled values
    # 70 kV → 0xFFF
    # 6 mA → 0xFFF

    def send_program(self):
        try:
            kv = float(self.voltageIn.text())
            ma = float(self.currentIn.text())
        except:
            self.log("[ERROR] Invalid numeric input.")
            return

        kv_hex = int((kv / 100.0) * 0xFFF)     # scale to full 100kV
        ma_hex = int((ma / 6.0) * 0xFFF)       # scale to full 6mA

        self.send_cmd(f"V{kv_hex:03X}")
        self.send_cmd(f"I{ma_hex:03X}")

    def hv_on(self):
        # HV ON bit → 'H1'
        self.send_cmd("H1")

    def hv_off(self):
        # HV OFF bit → 'F1'
        self.send_cmd("F1")

    def reset_ps(self):
        # Reset → 'R1'
        self.send_cmd("R1")

    # ---------------------------------------------------------------------
    # Polling status (required every <1.5 sec)
    # ---------------------------------------------------------------------
    def poll_status(self):
        self.send_cmd("Q")   # Query monitors


if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = WJGUI()
    gui.show()
    sys.exit(app.exec())
