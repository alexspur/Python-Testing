"""
Quantel CFR Laser Control GUI
Standalone PyQt5 application for full RS-232 control of the Quantel CFR laser system.

Serial settings (per manual):
  9600 baud | 8 data bits | no parity | 1 stop bit | no flow control
  Tx/Rx only — no hardware handshaking.

Usage:
  pip install pyserial pyqt5
  python cfr_laser_gui.py

Note: If the Remote Box is used, it disables serial control.
      Re-enable via Remote Box: System menu → serial link → ON
"""

import sys
import time
import threading
from datetime import datetime

import serial
import serial.tools.list_ports
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QGroupBox, QPushButton, QLabel, QComboBox, QLineEdit,
    QTextEdit, QSpinBox, QDoubleSpinBox, QTabWidget, QFrame, QSplitter,
    QStatusBar, QMessageBox, QCheckBox, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread
from PyQt5.QtGui import QFont, QColor, QPalette, QTextCursor


# ─────────────────────────────────────────────────────────────────────────────
# Serial worker — all I/O off the GUI thread
# ─────────────────────────────────────────────────────────────────────────────

class SerialWorker(QObject):
    """Handles blocking serial I/O in a background thread."""
    response_received = pyqtSignal(str, str)   # (command, response)
    error_occurred    = pyqtSignal(str)

    CMD_DELAY = 0.15   # 150 ms minimum between commands (per manual)

    def __init__(self):
        super().__init__()
        self.ser = None
        self._lock = threading.Lock()
        self._last_cmd_time = 0.0

    def connect(self, port: str) -> bool:
        try:
            self.ser = serial.Serial(
                port=port,
                baudrate=9600,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
                timeout=1.0
            )
            return True
        except serial.SerialException as e:
            self.error_occurred.emit(f"Connect failed: {e}")
            return False

    def disconnect(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.ser = None

    def is_connected(self) -> bool:
        return self.ser is not None and self.ser.is_open

    def send(self, cmd: str) -> str:
        """Send command, return response (blocking). Thread-safe."""
        with self._lock:
            # Enforce minimum inter-command delay
            elapsed = time.monotonic() - self._last_cmd_time
            if elapsed < self.CMD_DELAY:
                time.sleep(self.CMD_DELAY - elapsed)

            if not self.is_connected():
                return "[NOT CONNECTED]"
            try:
                self.ser.reset_input_buffer()
                self.ser.write((cmd + "\r\n").encode("ascii"))
                self._last_cmd_time = time.monotonic()

                # Read until timeout or newline
                response = b""
                deadline = time.monotonic() + 1.5
                while time.monotonic() < deadline:
                    chunk = self.ser.read(self.ser.in_waiting or 1)
                    if chunk:
                        response += chunk
                        if b"\r" in response or b"\n" in response:
                            break
                decoded = response.decode("ascii", errors="replace").strip()
                self.response_received.emit(cmd, decoded)
                return decoded
            except serial.SerialException as e:
                msg = f"Serial error: {e}"
                self.error_occurred.emit(msg)
                return f"[ERROR: {e}]"

    def send_async(self, cmd: str):
        """Fire-and-forget in a daemon thread."""
        t = threading.Thread(target=self.send, args=(cmd,), daemon=True)
        t.start()


# ─────────────────────────────────────────────────────────────────────────────
# Status Indicator widget
# ─────────────────────────────────────────────────────────────────────────────

class StatusLamp(QLabel):
    COLORS = {"green": "#00e676", "red": "#f44336", "yellow": "#ffea00", "grey": "#555"}

    def __init__(self, size=14):
        super().__init__()
        self.setFixedSize(size, size)
        self.set("grey")

    def set(self, color: str):
        c = self.COLORS.get(color, "#555")
        self.setStyleSheet(
            f"background:{c}; border-radius:{self.width()//2}px;"
            f"border:1px solid rgba(255,255,255,0.3);"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Main Window
# ─────────────────────────────────────────────────────────────────────────────

DARK = """
QMainWindow, QWidget { background: #1e1e1e; color: #e0e0e0; font-family: 'Consolas', 'Courier New', monospace; }
QGroupBox {
    border: 1px solid #404040;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 6px;
    font-size: 11px;
    color: #b0b0b0;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QPushButton {
    background: #2d2d2d;
    border: 1px solid #505050;
    border-radius: 4px;
    padding: 5px 12px;
    color: #e0e0e0;
    font-size: 12px;
    min-height: 26px;
}
QPushButton:hover { background: #3d3d3d; border-color: #606060; }
QPushButton:pressed { background: #4d4d4d; }
QPushButton:disabled { color: #606060; border-color: #404040; }
QPushButton#btn_fire { background:#c62828; border-color:#e53935; color:white; font-weight:bold; }
QPushButton#btn_fire:hover { background:#d32f2f; }
QPushButton#btn_stop { background:#2e7d32; border-color:#43a047; color:white; font-weight:bold; }
QPushButton#btn_stop:hover { background:#388e3c; }
QPushButton#btn_connect { background:#1565c0; border-color:#1e88e5; color:white; }
QPushButton#btn_connect:hover { background:#1976d2; }
QPushButton#btn_shutter_open { background:#e65100; border-color:#ef6c00; color:white; font-weight:bold; }
QPushButton#btn_shutter_close { background:#546e7a; border-color:#78909c; color:white; }
QLabel { color: #c0c0c0; font-size: 12px; }
QLabel#value_label { color: #f0f0f0; font-size: 13px; font-weight: bold; }
QLabel#header { color: #42a5f5; font-size: 13px; font-weight: bold; }
QComboBox {
    background: #2d2d2d; border: 1px solid #505050; border-radius: 4px;
    padding: 3px 8px; color: #e0e0e0; min-height: 24px;
}
QComboBox QAbstractItemView { background: #2d2d2d; color: #e0e0e0; selection-background-color: #1565c0; }
QLineEdit, QSpinBox, QDoubleSpinBox {
    background: #2d2d2d; border: 1px solid #505050; border-radius: 4px;
    padding: 3px 8px; color: #e0e0e0; min-height: 24px;
}
QTextEdit {
    background: #252525; border: 1px solid #404040; border-radius: 4px;
    color: #81c784; font-family: 'Consolas', 'Courier New', monospace; font-size: 11px;
}
QTabWidget::pane { border: 1px solid #404040; }
QTabBar::tab {
    background: #2d2d2d; border: 1px solid #404040; padding: 6px 16px; margin-right: 2px;
    color: #a0a0a0; font-size: 11px;
}
QTabBar::tab:selected { background: #1e1e1e; color: #e0e0e0; border-bottom: 2px solid #42a5f5; }
QSplitter::handle { background: #404040; }
QStatusBar { background: #252525; color: #a0a0a0; font-size: 11px; }
QCheckBox { color: #c0c0c0; }
QCheckBox::indicator { width:14px; height:14px; border:1px solid #505050; background:#2d2d2d; border-radius:2px; }
QCheckBox::indicator:checked { background:#1565c0; border-color:#1e88e5; }
"""


class CFRLaserGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker = SerialWorker()
        self.worker.response_received.connect(self._on_response)
        self.worker.error_occurred.connect(self._on_error)

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_status)

        self.setWindowTitle("Quantel CFR Laser Control  —  ICE450")
        self.setMinimumSize(960, 700)
        self.setStyleSheet(DARK)
        self._build_ui()
        self._refresh_ports()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(6)
        root.setContentsMargins(8, 8, 8, 8)

        # ── Top bar: connection ───────────────────────────────────────────────
        root.addWidget(self._build_connection_bar())

        # ── Main content ──────────────────────────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, 1)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setSpacing(6)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self._build_status_panel())
        ll.addWidget(self._build_flashlamp_panel())
        ll.addWidget(self._build_qswitch_panel())
        ll.addWidget(self._build_shutter_panel())
        ll.addStretch()

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setSpacing(6)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self._build_tabs())
        rl.addWidget(self._build_console())

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([360, 600])

        # ── Status bar ────────────────────────────────────────────────────────
        self.statusBar().showMessage("Disconnected")

    # ── Connection bar ────────────────────────────────────────────────────────

    def _build_connection_bar(self):
        box = QGroupBox("Connection")
        h = QHBoxLayout(box)
        h.setSpacing(8)

        self.conn_lamp = StatusLamp(14)
        h.addWidget(self.conn_lamp)

        h.addWidget(QLabel("Port:"))
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(110)
        h.addWidget(self.port_combo)

        self.btn_refresh = QPushButton("↺ Refresh")
        self.btn_refresh.clicked.connect(self._refresh_ports)
        h.addWidget(self.btn_refresh)

        self.btn_connect = QPushButton("Connect")
        self.btn_connect.setObjectName("btn_connect")
        self.btn_connect.clicked.connect(self._toggle_connect)
        h.addWidget(self.btn_connect)

        h.addStretch()

        # Serial link enable reminder
        note = QLabel("⚠ If Remote Box was used: re-enable serial via System → serial link → ON")
        note.setStyleSheet("color:#ffd54f; font-size:11px;")
        h.addWidget(note)

        # Poll toggle
        self.chk_poll = QCheckBox("Auto-poll (2s)")
        self.chk_poll.setChecked(True)
        self.chk_poll.stateChanged.connect(self._on_poll_toggle)
        h.addWidget(self.chk_poll)

        return box

    # ── Status panel ──────────────────────────────────────────────────────────

    def _build_status_panel(self):
        box = QGroupBox("System Status")
        g = QGridLayout(box)
        g.setSpacing(6)

        def row(label, row_idx):
            lbl = QLabel(label)
            lbl.setStyleSheet("color:#909090; font-size:11px;")
            val = QLabel("—")
            val.setObjectName("value_label")
            lamp = StatusLamp(10)
            g.addWidget(lbl,  row_idx, 0)
            g.addWidget(val,  row_idx, 1)
            g.addWidget(lamp, row_idx, 2)
            return val, lamp

        self.lbl_state,    self.lamp_state    = row("State:",        0)
        self.lbl_temp_cg,  self.lamp_temp_cg  = row("CG Temp:",      1)
        self.lbl_temp_hg,  self.lamp_temp_hg  = row("HG Temp:",      2)
        self.lbl_temp_cs,  self.lamp_temp_cs  = row("CS Temp:",      3)
        self.lbl_flow,     self.lamp_flow     = row("Flow Rate:",     4)
        self.lbl_shutter,  self.lamp_shutter  = row("Shutter:",       5)
        self.lbl_qs_sync,  self.lamp_qs_sync  = row("QS Sync:",      6)
        self.lbl_interlock,self.lamp_interlock= row("Interlocks:",    7)
        self.lbl_version,  _                  = row("Firmware:",      8)
        self.lbl_fl_count, _                  = row("FL Count:",      9)

        btn_refresh = QPushButton("Refresh Status")
        btn_refresh.clicked.connect(self._manual_refresh)
        g.addWidget(btn_refresh, 10, 0, 1, 3)

        return box

    # ── Flashlamp panel ───────────────────────────────────────────────────────

    def _build_flashlamp_panel(self):
        box = QGroupBox("Flashlamp")
        v = QVBoxLayout(box)
        v.setSpacing(6)

        # Fire / stop / simmer row
        h1 = QHBoxLayout()
        self.btn_fire_int = QPushButton("▶ Fire INT")
        self.btn_fire_int.setObjectName("btn_fire")
        self.btn_fire_int.clicked.connect(lambda: self._send_cmd("A"))
        h1.addWidget(self.btn_fire_int)

        self.btn_fire_ext = QPushButton("▶ Fire EXT")
        self.btn_fire_ext.setObjectName("btn_fire")
        self.btn_fire_ext.clicked.connect(lambda: self._send_cmd("E"))
        h1.addWidget(self.btn_fire_ext)

        self.btn_simmer = QPushButton("Simmer")
        self.btn_simmer.clicked.connect(lambda: self._send_cmd("M"))
        h1.addWidget(self.btn_simmer)

        self.btn_stop = QPushButton("■ STOP")
        self.btn_stop.setObjectName("btn_stop")
        self.btn_stop.clicked.connect(lambda: self._send_cmd("S"))
        h1.addWidget(self.btn_stop)
        v.addLayout(h1)

        # Frequency
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("Frequency (Hz):"))
        self.spin_freq = QDoubleSpinBox()
        self.spin_freq.setRange(1.0, 50.0)
        self.spin_freq.setSingleStep(0.5)
        self.spin_freq.setValue(10.0)
        self.spin_freq.setDecimals(2)
        h2.addWidget(self.spin_freq)
        btn_set_freq = QPushButton("Set")
        btn_set_freq.clicked.connect(self._set_frequency)
        h2.addWidget(btn_set_freq)
        btn_get_freq = QPushButton("Query")
        btn_get_freq.clicked.connect(lambda: self._send_cmd("D"))
        h2.addWidget(btn_get_freq)
        v.addLayout(h2)

        # Energy
        h3 = QHBoxLayout()
        h3.addWidget(QLabel("Energy (J):"))
        self.spin_energy = QDoubleSpinBox()
        self.spin_energy.setRange(0.0, 20.0)
        self.spin_energy.setSingleStep(0.1)
        self.spin_energy.setValue(6.0)
        self.spin_energy.setDecimals(2)
        h3.addWidget(self.spin_energy)
        btn_set_ej = QPushButton("Set")
        btn_set_ej.clicked.connect(self._set_energy)
        h3.addWidget(btn_set_ej)
        btn_get_ej = QPushButton("Query")
        btn_get_ej.clicked.connect(lambda: self._send_cmd("EJ"))
        h3.addWidget(btn_get_ej)
        v.addLayout(h3)

        # Bypass
        h4 = QHBoxLayout()
        btn_bypass_on  = QPushButton("Bypass ON")
        btn_bypass_on.clicked.connect(lambda: self._send_cmd("BYPASS1"))
        btn_bypass_off = QPushButton("Bypass OFF")
        btn_bypass_off.clicked.connect(lambda: self._send_cmd("BYPASS0"))
        btn_bypass_q   = QPushButton("Query Bypass")
        btn_bypass_q.clicked.connect(lambda: self._send_cmd("BYPASS"))
        h4.addWidget(btn_bypass_on)
        h4.addWidget(btn_bypass_off)
        h4.addWidget(btn_bypass_q)
        v.addLayout(h4)

        return box

    # ── Q-Switch panel ────────────────────────────────────────────────────────

    def _build_qswitch_panel(self):
        box = QGroupBox("Q-Switch")
        v = QVBoxLayout(box)
        v.setSpacing(6)

        # QS start / stop / single
        h1 = QHBoxLayout()
        self.btn_qs_start = QPushButton("▶ QS Start")
        self.btn_qs_start.setObjectName("btn_fire")
        self.btn_qs_start.clicked.connect(lambda: self._send_cmd("CC"))
        h1.addWidget(self.btn_qs_start)

        self.btn_qs_single = QPushButton("Single Shot")
        self.btn_qs_single.clicked.connect(lambda: self._send_cmd("OP"))
        h1.addWidget(self.btn_qs_single)

        self.btn_qs_stop = QPushButton("■ QS Stop")
        self.btn_qs_stop.setObjectName("btn_stop")
        self.btn_qs_stop.clicked.connect(lambda: self._send_cmd("CS"))
        h1.addWidget(self.btn_qs_stop)
        v.addLayout(h1)

        # Sync mode
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("Sync:"))
        btn_qs_int = QPushButton("Internal (QI)")
        btn_qs_int.clicked.connect(lambda: self._send_cmd("QI"))
        btn_qs_ext = QPushButton("External (QE)")
        btn_qs_ext.clicked.connect(lambda: self._send_cmd("QE"))
        btn_qs_sync_q = QPushButton("Query Sync")
        btn_qs_sync_q.clicked.connect(lambda: self._send_cmd("QSSYNC"))
        h2.addWidget(btn_qs_int)
        h2.addWidget(btn_qs_ext)
        h2.addWidget(btn_qs_sync_q)
        v.addLayout(h2)

        # QS delay
        h3 = QHBoxLayout()
        h3.addWidget(QLabel("Delay (µs):"))
        self.spin_qs_delay = QSpinBox()
        self.spin_qs_delay.setRange(50, 500)
        self.spin_qs_delay.setValue(144)
        h3.addWidget(self.spin_qs_delay)
        btn_set_delay = QPushButton("Set")
        btn_set_delay.clicked.connect(self._set_qs_delay)
        h3.addWidget(btn_set_delay)
        btn_get_delay = QPushButton("Query")
        btn_get_delay.clicked.connect(lambda: self._send_cmd("W"))
        h3.addWidget(btn_get_delay)
        v.addLayout(h3)

        # QS Mode
        h4 = QHBoxLayout()
        h4.addWidget(QLabel("Mode:"))
        self.combo_qs_mode = QComboBox()
        self.combo_qs_mode.addItems(["1 – Auto", "2 – Burst", "3 – Scan"])
        h4.addWidget(self.combo_qs_mode)
        btn_set_mode = QPushButton("Set Mode")
        btn_set_mode.clicked.connect(self._set_qs_mode)
        h4.addWidget(btn_set_mode)
        btn_get_mode = QPushButton("Query")
        btn_get_mode.clicked.connect(lambda: self._send_cmd("QSM"))
        h4.addWidget(btn_get_mode)
        v.addLayout(h4)

        # Auto ratio / Burst count
        h5 = QHBoxLayout()
        h5.addWidget(QLabel("Auto F/N ratio:"))
        self.spin_qs_ratio = QSpinBox()
        self.spin_qs_ratio.setRange(1, 99)
        self.spin_qs_ratio.setValue(1)
        h5.addWidget(self.spin_qs_ratio)
        btn_set_ratio = QPushButton("Set")
        btn_set_ratio.clicked.connect(lambda: self._send_cmd(f"QSF{self.spin_qs_ratio.value()}"))
        h5.addWidget(btn_set_ratio)

        h5.addSpacing(8)
        h5.addWidget(QLabel("Burst count:"))
        self.spin_burst = QSpinBox()
        self.spin_burst.setRange(1, 999)
        self.spin_burst.setValue(1)
        h5.addWidget(self.spin_burst)
        btn_set_burst = QPushButton("Set")
        btn_set_burst.clicked.connect(lambda: self._send_cmd(f"QSP{self.spin_burst.value():03d}"))
        h5.addWidget(btn_set_burst)
        v.addLayout(h5)

        # Scan params
        h6 = QHBoxLayout()
        h6.addWidget(QLabel("Scan (passive / active / total):"))
        self.spin_scan_p = QSpinBox(); self.spin_scan_p.setRange(1, 99); self.spin_scan_p.setValue(5)
        self.spin_scan_a = QSpinBox(); self.spin_scan_a.setRange(1, 99); self.spin_scan_a.setValue(5)
        self.spin_scan_t = QSpinBox(); self.spin_scan_t.setRange(1, 99); self.spin_scan_t.setValue(10)
        h6.addWidget(self.spin_scan_p)
        h6.addWidget(self.spin_scan_a)
        h6.addWidget(self.spin_scan_t)
        btn_set_scan = QPushButton("Set Scan")
        btn_set_scan.clicked.connect(self._set_scan)
        h6.addWidget(btn_set_scan)
        btn_get_scan = QPushButton("Query")
        btn_get_scan.clicked.connect(lambda: self._send_cmd("Q"))
        h6.addWidget(btn_get_scan)
        v.addLayout(h6)

        return box

    # ── Shutter panel ─────────────────────────────────────────────────────────

    def _build_shutter_panel(self):
        box = QGroupBox("Shutter")
        h = QHBoxLayout(box)
        self.btn_shutter_open = QPushButton("⬛ OPEN Shutter")
        self.btn_shutter_open.setObjectName("btn_shutter_open")
        self.btn_shutter_open.clicked.connect(lambda: self._send_cmd("SHC1"))
        self.btn_shutter_close = QPushButton("Close Shutter")
        self.btn_shutter_close.setObjectName("btn_shutter_close")
        self.btn_shutter_close.clicked.connect(lambda: self._send_cmd("SHC0"))
        btn_shutter_q = QPushButton("Query")
        btn_shutter_q.clicked.connect(lambda: self._send_cmd("SHC"))
        h.addWidget(self.btn_shutter_open)
        h.addWidget(self.btn_shutter_close)
        h.addWidget(btn_shutter_q)
        return box

    # ── Tabs (Interlock / Diagnostics / Raw) ──────────────────────────────────

    def _build_tabs(self):
        tabs = QTabWidget()

        # ── Interlock tab
        ilock_w = QWidget()
        iv = QVBoxLayout(ilock_w)
        iv.setSpacing(4)

        def ilock_row(label, cmd):
            h = QHBoxLayout()
            lmp = StatusLamp(10)
            lbl = QLabel(label)
            lbl.setStyleSheet("color:#909090; font-size:11px;")
            val = QLabel("—")
            val.setStyleSheet("font-size:11px; color:#c0c0c0;")
            btn = QPushButton("Query")
            btn.setMaximumWidth(60)
            btn.clicked.connect(lambda: self._send_cmd(cmd))
            h.addWidget(lmp); h.addWidget(lbl, 1); h.addWidget(val); h.addWidget(btn)
            return h, lmp, val

        for name, cmd, lamp_attr, val_attr in [
            ("IF1 – System Interlock Byte 1", "IF1", "lamp_if1", "lbl_if1"),
            ("IF2 – System Interlock Byte 2", "IF2", "lamp_if2", "lbl_if2"),
            ("IF3 – System Interlock Byte 3", "IF3", "lamp_if3", "lbl_if3"),
            ("IQS – Q-Switch Interlock",       "IQS", "lamp_iqs", "lbl_iqs"),
            ("IF? – Last Fault Interlock",      "IF?", "lamp_iff", "lbl_iff"),
        ]:
            row, lamp, val = ilock_row(name, cmd)
            setattr(self, lamp_attr, lamp)
            setattr(self, val_attr, val)
            iv.addLayout(row)

        btn_all_ilock = QPushButton("Query All Interlocks")
        btn_all_ilock.clicked.connect(self._query_all_interlocks)
        iv.addWidget(btn_all_ilock)
        iv.addStretch()
        tabs.addTab(ilock_w, "Interlocks")

        # ── Diagnostics tab
        diag_w = QWidget()
        dv = QVBoxLayout(diag_w)
        dv.setSpacing(6)

        g = QGridLayout()
        diags = [
            ("Firmware Version",    "VER"),
            ("Flashlamp Count",     "F"),
            ("User FL Count",       "UF"),
            ("Reset User FL Count", "UF0"),
            ("CG Temperature",      "TEMP"),
            ("CS Temperature",      "CST"),
            ("HG Temperature",      "HGT"),
            ("Coolant Flow Rate",   "FLOW"),
            ("QS Sync Query",       "QSSYNC"),
            ("QS Mode Query",       "QSM"),
            ("QS Burst Count",      "QSP"),
            ("QS Scan Params",      "Q"),
            ("QS Auto Ratio",       "QSF"),
        ]
        for i, (name, cmd) in enumerate(diags):
            lbl = QLabel(name)
            lbl.setStyleSheet("color:#909090; font-size:11px;")
            btn = QPushButton(cmd)
            btn.setMaximumWidth(120)
            btn.clicked.connect(lambda c=cmd: self._send_cmd(c))
            g.addWidget(lbl, i, 0)
            g.addWidget(btn, i, 1)

        dv.addLayout(g)
        dv.addStretch()
        tabs.addTab(diag_w, "Diagnostics")

        # ── Alignment Mode tab
        align_w = QWidget()
        av = QVBoxLayout(align_w)
        av.setSpacing(8)

        # Banner
        banner = QLabel(
            "⚠  ALIGNMENT MODE  —  Attenuated 266 nm output\n"
            "FLQS delay pushed above optimal (180 µs per Data Summary Sheet).\n"
            "300–400 µs gives reduced but usable 266 nm output for alignment."
        )
        banner.setStyleSheet(
            "background:#3d3110; color:#ffd54f; border:1px solid #5d4a1a;"
            "border-radius:4px; padding:8px; font-size:11px;"
        )
        banner.setWordWrap(True)
        av.addWidget(banner)

        # ── Enter / Exit alignment mode ──────────────────────────────────────
        h_enter = QHBoxLayout()
        self.btn_align_enter = QPushButton("▶  Enter Alignment Mode")
        self.btn_align_enter.setStyleSheet(
            "background:#e65100; border:1px solid #ef6c00; color:white;"
            "font-weight:bold; min-height:30px; font-size:12px;"
        )
        self.btn_align_enter.clicked.connect(self._enter_alignment_mode)
        h_enter.addWidget(self.btn_align_enter)

        self.btn_align_exit = QPushButton("■  Exit Alignment Mode (STOP)")
        self.btn_align_exit.setStyleSheet(
            "background:#1b5e20; border:1px solid #43a047; color:white;"
            "font-weight:bold; min-height:30px; font-size:12px;"
        )
        self.btn_align_exit.clicked.connect(self._exit_alignment_mode)
        h_enter.addWidget(self.btn_align_exit)
        av.addLayout(h_enter)

        # Alignment state lamp
        h_state = QHBoxLayout()
        self.lamp_align = StatusLamp(14)
        self.lbl_align_state = QLabel("Inactive")
        self.lbl_align_state.setStyleSheet("font-weight:bold; font-size:12px;")
        h_state.addWidget(self.lamp_align)
        h_state.addWidget(self.lbl_align_state)
        h_state.addStretch()
        av.addLayout(h_state)

        av.addWidget(self._hsep())

        # ── FLQS delay control ───────────────────────────────────────────────
        grp_delay = QGroupBox("FLQS Delay  (higher = lower output energy)")
        gd = QVBoxLayout(grp_delay)

        info_delay = QLabel(
            "Optimal delay for full power is system-specific (see Data Summary Sheet).\n"
            "Increasing well above optimal attenuates output. Quantel recommends this\n"
            "over reducing flashlamp energy, which distorts beam characteristics."
        )
        info_delay.setStyleSheet("color:#909090; font-size:10px;")
        info_delay.setWordWrap(True)
        gd.addWidget(info_delay)

        h_delay = QHBoxLayout()
        h_delay.addWidget(QLabel("FLQS Delay (µs):"))
        self.spin_align_delay = QSpinBox()
        self.spin_align_delay.setRange(50, 500)
        self.spin_align_delay.setValue(300)
        self.spin_align_delay.setToolTip(
            "Your system optimum is 180 µs (Data Summary Sheet).\n"
            "For alignment, 300–400 µs gives attenuated 266 nm output.\n"
            "Pure flashlamp-only (no QS) will not produce useful 266 nm — "
            "harmonic conversion requires Q-switched peak power."
        )
        h_delay.addWidget(self.spin_align_delay)

        btn_set_align_delay = QPushButton("Apply Delay")
        btn_set_align_delay.clicked.connect(
            lambda: self._send_cmd(f"W{self.spin_align_delay.value():03d}")
        )
        h_delay.addWidget(btn_set_align_delay)

        btn_query_delay = QPushButton("Query")
        btn_query_delay.clicked.connect(lambda: self._send_cmd("W"))
        h_delay.addWidget(btn_query_delay)
        gd.addLayout(h_delay)

        # Preset buttons
        h_presets = QHBoxLayout()
        h_presets.addWidget(QLabel("Presets:"))
        for label, val in [("Low (250 µs)", 250), ("Med (325 µs)", 325), ("High (400 µs)", 400)]:
            btn = QPushButton(label)
            btn.clicked.connect(
                lambda checked, v=val: (
                    self.spin_align_delay.setValue(v),
                    self._send_cmd(f"W{v:03d}")
                )
            )
            h_presets.addWidget(btn)
        gd.addLayout(h_presets)
        av.addWidget(grp_delay)

        # ── Scan mode for low duty-cycle lasing ─────────────────────────────
        grp_scan = QGroupBox("Scan Mode  (sparse Q-switch pulses for brief alignment shots)")
        gs = QVBoxLayout(grp_scan)

        info_scan = QLabel(
            "Scan mode fires the Q-Switch on only a few flashlamp pulses out of many.\n"
            "e.g. 1 active + 9 passive = laser fires 1-in-10 flashlamp pulses.\n"
            "QS must be started (CC) after entering scan mode for pulses to emit."
        )
        info_scan.setStyleSheet("color:#909090; font-size:10px;")
        info_scan.setWordWrap(True)
        gs.addWidget(info_scan)

        h_scan = QHBoxLayout()
        h_scan.addWidget(QLabel("Active:"))
        self.spin_align_active = QSpinBox()
        self.spin_align_active.setRange(1, 99)
        self.spin_align_active.setValue(1)
        h_scan.addWidget(self.spin_align_active)

        h_scan.addWidget(QLabel("Passive:"))
        self.spin_align_passive = QSpinBox()
        self.spin_align_passive.setRange(1, 99)
        self.spin_align_passive.setValue(9)
        h_scan.addWidget(self.spin_align_passive)

        h_scan.addWidget(QLabel("Total scans (99=∞):"))
        self.spin_align_scans = QSpinBox()
        self.spin_align_scans.setRange(1, 99)
        self.spin_align_scans.setValue(99)
        h_scan.addWidget(self.spin_align_scans)
        gs.addLayout(h_scan)

        h_scan_btns = QHBoxLayout()
        btn_apply_scan = QPushButton("Apply Scan Params + Start QS")
        btn_apply_scan.clicked.connect(self._apply_alignment_scan)
        btn_stop_qs = QPushButton("Stop QS Only")
        btn_stop_qs.clicked.connect(lambda: self._send_cmd("CS"))
        h_scan_btns.addWidget(btn_apply_scan)
        h_scan_btns.addWidget(btn_stop_qs)
        gs.addLayout(h_scan_btns)
        av.addWidget(grp_scan)

        av.addWidget(self._hsep())

        # ── Single-shot alignment pulse ──────────────────────────────────────
        grp_single = QGroupBox("Single Alignment Shot")
        gh = QVBoxLayout(grp_single)
        info_single = QLabel(
            "Fires exactly one Q-switch pulse. Flashlamp must already be running (Fire INT).\n"
            "Useful for marking / burn-paper checks with minimal exposure."
        )
        info_single.setStyleSheet("color:#909090; font-size:10px;")
        info_single.setWordWrap(True)
        gh.addWidget(info_single)
        btn_single = QPushButton("Fire Single Alignment Shot  (OP)")
        btn_single.setStyleSheet(
            "background:#b71c1c; border:1px solid #ef5350; color:white; font-weight:bold; min-height:28px;"
        )
        btn_single.clicked.connect(lambda: self._send_cmd("OP"))
        gh.addWidget(btn_single)
        av.addWidget(grp_single)

        av.addStretch()
        tabs.addTab(align_w, "🔦 Alignment")

        # ── Raw command tab
        raw_w = QWidget()
        rv = QVBoxLayout(raw_w)
        rv.addWidget(QLabel("Send raw command (CR+LF appended automatically):"))
        h = QHBoxLayout()
        self.raw_input = QLineEdit()
        self.raw_input.setPlaceholderText("e.g.  W144  or  QSM1  or  SHC1")
        self.raw_input.returnPressed.connect(self._send_raw)
        h.addWidget(self.raw_input)
        btn_raw = QPushButton("Send")
        btn_raw.clicked.connect(self._send_raw)
        h.addWidget(btn_raw)
        rv.addLayout(h)
        rv.addStretch()
        tabs.addTab(raw_w, "Raw Command")

        return tabs

    # ── Console ───────────────────────────────────────────────────────────────

    def _build_console(self):
        box = QGroupBox("Communication Log")
        v = QVBoxLayout(box)
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setMinimumHeight(160)
        v.addWidget(self.console)
        h = QHBoxLayout()
        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self.console.clear)
        h.addStretch()
        h.addWidget(btn_clear)
        v.addLayout(h)
        return box

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _hsep(self):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color:#ddd;")
        return line

    # ── Alignment mode actions ────────────────────────────────────────────────

    def _enter_alignment_mode(self):
        """
        ASE alignment mode — flashlamp fires, Q-switch explicitly disabled.
        Output is low-intensity amplified spontaneous emission only.
        No Q-switched pulse is possible as long as CC/OP are not sent.
        """
        if not self.worker.is_connected():
            self._log("err", "Not connected — cannot enter alignment mode.")
            return

        self._log("sys", "=== Entering Alignment Mode (ASE, no Q-switch) ===")
        steps = [
            ("CS",    "Disable Q-Switch"),
            ("SHC0",  "Close shutter"),
            ("QI",    "Set QS sync to Internal (keeps QS under software control)"),
            ("A",     "Start flashlamp — ASE output only, no Q-switched pulse"),
        ]

        def _run():
            for cmd, desc in steps:
                self._log("sys", f"  {desc}")
                self.worker.send(cmd)
            self.lamp_align.set("yellow")
            self.lbl_align_state.setText("ACTIVE — flashlamp running, Q-switch disabled (ASE only)")
            self._log("sys", "Open shutter when ready. Do NOT send CC or OP in this mode.")

        threading.Thread(target=_run, daemon=True).start()

    def _exit_alignment_mode(self):
        """Stop everything and return to safe standby."""
        self._log("sys", "=== Exiting Alignment Mode ===")

        def _run():
            for cmd, desc in [
                ("CS",    "Stop Q-Switch"),
                ("SHC0",  "Close shutter"),
                ("S",     "Stop flashlamp"),
            ]:
                self._log("sys", f"  {desc}")
                self.worker.send(cmd)
            self.lamp_align.set("grey")
            self.lbl_align_state.setText("Inactive — laser stopped")
            self._log("sys", "Alignment mode exited. System in standby.")

        threading.Thread(target=_run, daemon=True).start()

    def _apply_alignment_scan(self):
        """Set scan parameters and start Q-switch for sparse alignment pulses."""
        p = self.spin_align_passive.value()
        a = self.spin_align_active.value()
        t = self.spin_align_scans.value()
        self._log("sys", f"Scan mode: {a} active / {p} passive / {t} total — starting QS")

        def _run():
            self.worker.send(f"Q{p:02d}{a:02d}{t:02d}")
            self.worker.send("CC")   # Start Q-switching in scan mode

        threading.Thread(target=_run, daemon=True).start()

    # ── Actions ───────────────────────────────────────────────────────────────

    def _refresh_ports(self):
        self.port_combo.clear()
        ports = [p.device for p in serial.tools.list_ports.comports()]
        if ports:
            self.port_combo.addItems(ports)
        else:
            self.port_combo.addItem("(no ports found)")

    def _toggle_connect(self):
        if self.worker.is_connected():
            self._poll_timer.stop()
            self.worker.disconnect()
            self.conn_lamp.set("grey")
            self.btn_connect.setText("Connect")
            self.statusBar().showMessage("Disconnected")
            self._log("sys", "Disconnected.")
        else:
            port = self.port_combo.currentText()
            if self.worker.connect(port):
                self.conn_lamp.set("green")
                self.btn_connect.setText("Disconnect")
                self.statusBar().showMessage(f"Connected — {port}  |  9600 8N1")
                self._log("sys", f"Connected to {port}  (9600 8N1 no flow control)")
                if self.chk_poll.isChecked():
                    self._poll_timer.start(2000)
                self._manual_refresh()
            else:
                self.conn_lamp.set("red")

    def _on_poll_toggle(self, state):
        if state and self.worker.is_connected():
            self._poll_timer.start(2000)
        else:
            self._poll_timer.stop()

    def _send_cmd(self, cmd: str):
        if not self.worker.is_connected():
            self._log("err", "Not connected.")
            return
        self._log("tx", cmd)
        threading.Thread(target=self._bg_send, args=(cmd,), daemon=True).start()

    def _bg_send(self, cmd: str):
        resp = self.worker.send(cmd)
        # Signals emitted inside send() will reach _on_response on main thread

    def _send_raw(self):
        cmd = self.raw_input.text().strip()
        if cmd:
            self._send_cmd(cmd)
            self.raw_input.clear()

    def _set_frequency(self):
        hz = self.spin_freq.value()
        centihz = int(round(hz * 100))
        self._send_cmd(f"D{centihz:05d}")

    def _set_energy(self):
        joules = self.spin_energy.value()
        centij = int(round(joules * 100))
        self._send_cmd(f"EJ{centij:05d}")

    def _set_qs_delay(self):
        us = self.spin_qs_delay.value()
        self._send_cmd(f"W{us:03d}")

    def _set_qs_mode(self):
        mode = self.combo_qs_mode.currentIndex() + 1   # 1=auto, 2=burst, 3=scan
        self._send_cmd(f"QSM{mode}")

    def _set_scan(self):
        p = self.spin_scan_p.value()
        a = self.spin_scan_a.value()
        t = self.spin_scan_t.value()
        self._send_cmd(f"Q{p:02d}{a:02d}{t:02d}")

    def _query_all_interlocks(self):
        for cmd in ["IF1", "IF2", "IF3", "IQS", "IF?"]:
            self._send_cmd(cmd)
            time.sleep(0.18)

    def _manual_refresh(self):
        for cmd in ["VER", "SHC", "QSSYNC", "TEMP", "FLOW", "F"]:
            self._send_cmd(cmd)

    def _poll_status(self):
        """Lightweight periodic poll."""
        for cmd in ["TEMP", "FLOW", "IF2"]:
            self._send_cmd(cmd)

    # ── Response parsing ──────────────────────────────────────────────────────

    def _on_response(self, cmd: str, resp: str):
        self._log("rx", f"[{cmd}] → {resp}")
        cmd_upper = cmd.strip().upper()

        # State string parse
        state_keywords = ["standby", "simmer", "fire auto", "fire ext"]
        resp_lower = resp.lower()
        for kw in state_keywords:
            if kw in resp_lower:
                self.lbl_state.setText(resp.strip())
                color = "green" if "fire" in resp_lower else ("yellow" if "simmer" in resp_lower else "grey")
                self.lamp_state.set(color)
                break

        # Shutter
        if cmd_upper == "SHC" or (resp and "shc:" in resp_lower):
            if "open" in resp_lower:
                self.lbl_shutter.setText("OPEN")
                self.lamp_shutter.set("yellow")
            elif "close" in resp_lower:
                self.lbl_shutter.setText("closed")
                self.lamp_shutter.set("grey")

        # QS sync
        if "qs sync:" in resp_lower:
            self.lbl_qs_sync.setText(resp.strip())
            self.lamp_qs_sync.set("green" if "int" in resp_lower else "yellow")

        # Temperature
        if "temp" in resp_lower or cmd_upper in ("TEMP", "CST", "HGT"):
            if cmd_upper == "CST" and "cs" in resp_lower:
                self.lbl_temp_cs.setText(resp.strip())
            elif cmd_upper == "HGT" and "shg" in resp_lower:
                self.lbl_temp_hg.setText(resp.strip())
            elif cmd_upper == "TEMP":
                self.lbl_temp_cg.setText(resp.strip())
            elif "cg temp" in resp_lower or "temp" in resp_lower:
                self.lbl_temp_cg.setText(resp.strip())

        # Flow
        if "lpm" in resp_lower or cmd_upper == "FLOW":
            self.lbl_flow.setText(resp.strip())
            try:
                fval = float(resp.strip().split()[1])
                self.lamp_flow.set("green" if fval >= 1.5 else "red")
            except (ValueError, IndexError):
                self.lamp_flow.set("grey")

        # Flashlamp count
        if "ct lp" in resp_lower or cmd_upper == "F":
            self.lbl_fl_count.setText(resp.strip())

        # Version
        if "version" in resp_lower or cmd_upper == "VER":
            self.lbl_version.setText(resp.strip())

        # Interlock bytes
        ilock_fault = False
        if cmd_upper in ("IF1", "IF2", "IF3", "IQS", "IF?"):
            attr_map = {"IF1": ("lbl_if1", "lamp_if1"), "IF2": ("lbl_if2", "lamp_if2"),
                        "IF3": ("lbl_if3", "lamp_if3"), "IQS": ("lbl_iqs", "lamp_iqs"),
                        "IF?": ("lbl_iff", "lamp_iff")}
            lattr, lampattr = attr_map.get(cmd_upper, (None, None))
            if lattr:
                getattr(self, lattr).setText(resp.strip())
                # All zeros = OK
                bits = resp.replace(" ", "").replace(cmd_upper.lower(), "").strip()
                all_ok = all(c in "0 " for c in bits)
                getattr(self, lampattr).set("green" if all_ok else "red")
                if not all_ok:
                    ilock_fault = True

        if ilock_fault:
            self.lamp_interlock.set("red")
            self.lbl_interlock.setText("FAULT — see Interlocks tab")
        elif cmd_upper in ("IF1", "IF2", "IF3", "IQS"):
            self.lamp_interlock.set("green")
            self.lbl_interlock.setText("OK")

    def _on_error(self, msg: str):
        self._log("err", msg)
        self.conn_lamp.set("red")

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log(self, kind: str, msg: str):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        colors = {"tx": "#4dd0e1", "rx": "#81c784", "err": "#e57373", "sys": "#64b5f6"}
        prefixes = {"tx": "TX", "rx": "RX", "err": "!!", "sys": "SYS"}
        color = colors.get(kind, "#999")
        prefix = prefixes.get(kind, "??")
        html = f'<span style="color:#909090">{ts}</span> <span style="color:{color}">[{prefix}]</span> {msg}'
        self.console.append(html)
        self.console.moveCursor(QTextCursor.End)

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        self._poll_timer.stop()
        self.worker.disconnect()
        event.accept()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("CFR Laser Control")
    win = CFRLaserGUI()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
