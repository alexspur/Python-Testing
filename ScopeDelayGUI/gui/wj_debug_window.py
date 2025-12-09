# gui/wj_debug_window.py

import time
from collections import deque

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QDoubleSpinBox, QTextEdit, QComboBox, QGroupBox
)
from PyQt6.QtCore import Qt, QTimer

import pyqtgraph as pg

from instruments.wj import WJPowerSupply


class WJDebugWindow(QWidget):
    """
    Standalone debug GUI for the WJ100P6.0 high-voltage power supply.

    Features:
      - COM port selection + Connect
      - Set Voltage (kV) / Current (mA)
      - HV ON / HV OFF / RESET
      - Auto-poll status (timer) to prevent 1.5 s timeout
      - Live decoded readout (kV, mA, HV ON, Fault, Mode)
      - Live plot of V and I vs time
      - Console log of all traffic
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("WJ100P6.0 Debug")
        self.wj = WJPowerSupply(vmax_kv=100.0, imax_ma=6.0)

        self._t0 = time.time()
        self.time_buf = deque(maxlen=500)
        self.v_buf = deque(maxlen=500)
        self.i_buf = deque(maxlen=500)

        self._build_ui()
        self._setup_timer()

    # ------------------------------------------------------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)
        self.setLayout(layout)

        # --------- Connection row ----------
        row = QHBoxLayout()
        self.cmb_ports = QComboBox()
        self._refresh_ports()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_connect = QPushButton("Connect")

        self.btn_refresh.clicked.connect(self._refresh_ports)
        self.btn_connect.clicked.connect(self._on_connect)

        row.addWidget(QLabel("COM:"))
        row.addWidget(self.cmb_ports)
        row.addWidget(self.btn_refresh)
        row.addWidget(self.btn_connect)
        layout.addLayout(row)

        # --------- Setpoints ----------
        gb_set = QGroupBox("Setpoints")
        lay_set = QHBoxLayout()
        gb_set.setLayout(lay_set)

        self.spn_kv = QDoubleSpinBox()
        self.spn_kv.setDecimals(2)
        self.spn_kv.setRange(0.0, 100.0)
        self.spn_kv.setSingleStep(1.0)
        self.spn_kv.setSuffix(" kV")

        self.spn_ma = QDoubleSpinBox()
        self.spn_ma.setDecimals(3)
        self.spn_ma.setRange(0.0, 6.0)
        self.spn_ma.setSingleStep(0.1)
        self.spn_ma.setSuffix(" mA")

        self.btn_send_set = QPushButton("Send V/I")

        self.btn_send_set.clicked.connect(self._on_send_set)

        lay_set.addWidget(QLabel("Voltage:"))
        lay_set.addWidget(self.spn_kv)
        lay_set.addWidget(QLabel("Current:"))
        lay_set.addWidget(self.spn_ma)
        lay_set.addWidget(self.btn_send_set)

        layout.addWidget(gb_set)

        # --------- Control buttons ----------
        row2 = QHBoxLayout()
        self.btn_hvon = QPushButton("HV ON")
        self.btn_hvoff = QPushButton("HV OFF")
        self.btn_reset = QPushButton("RESET")

        self.btn_hvon.clicked.connect(self._on_hvon)
        self.btn_hvoff.clicked.connect(self._on_hvoff)
        self.btn_reset.clicked.connect(self._on_reset)

        row2.addWidget(self.btn_hvon)
        row2.addWidget(self.btn_hvoff)
        row2.addWidget(self.btn_reset)
        layout.addLayout(row2)

        # --------- Status indicators ----------
        gb_status = QGroupBox("Status")
        lay_status = QHBoxLayout()
        gb_status.setLayout(lay_status)

        self.lbl_kv = QLabel("kV: 0.00")
        self.lbl_ma = QLabel("mA: 0.000")
        self.lbl_mode = QLabel("Mode: V")
        self.lbl_hv = QLabel("HV: OFF")
        self.lbl_fault = QLabel("Fault: NONE")

        for lbl in (self.lbl_kv, self.lbl_ma, self.lbl_mode, self.lbl_hv, self.lbl_fault):
            lbl.setMinimumWidth(100)
            lay_status.addWidget(lbl)

        layout.addWidget(gb_status)

        # --------- Plot ----------
        self.plot = pg.PlotWidget()
        self.plot.setLabel("bottom", "Time", "s")
        self.plot.setLabel("left", "Value")
        self.plot.addLegend()

        self.curve_v = self.plot.plot(pen="y", name="kV")
        self.curve_i = self.plot.plot(pen="c", name="mA")

        layout.addWidget(self.plot, stretch=1)

        # --------- Console ----------
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        layout.addWidget(self.console, stretch=0)

    # ------------------------------------------------------------------
    def _setup_timer(self):
        self.timer = QTimer(self)
        self.timer.setInterval(500)  # ms
        self.timer.timeout.connect(self._on_poll)

    # ------------------------------------------------------------------
    def _refresh_ports(self):
        self.cmb_ports.clear()
        for d in WJPowerSupply.list_ports():
            self.cmb_ports.addItem(d)

    # ------------------------------------------------------------------
    def log(self, msg: str):
        self.console.append(msg)

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------
    def _on_connect(self):
        port = self.cmb_ports.currentText()
        if not port:
            self.log("[WARN] No COM port selected.")
            return

        try:
            self.wj.connect(port)
            self.log(f"[OK] Connected to {port}")
            self.timer.start()
        except Exception as e:
            self.log(f"[ERROR] Connect failed: {e}")

    def _on_send_set(self):
        if not self.wj.is_connected:
            self.log("[WARN] Not connected.")
            return

        kv = self.spn_kv.value()
        ma = self.spn_ma.value()

        try:
            result = self.wj.set_program(kv, ma)
            self.log(f">> SET {kv:.2f} kV, {ma:.3f} mA → {result}")
        except Exception as e:
            self.log(f"[ERROR] SET failed: {e}")

    def _on_hvon(self):
        if not self.wj.is_connected:
            self.log("[WARN] Not connected.")
            return
        try:
            result = self.wj.hv_on_pulse()
            self.log(f">> HV ON → {result}")
        except Exception as e:
            self.log(f"[ERROR] HV ON failed: {e}")

    def _on_hvoff(self):
        if not self.wj.is_connected:
            self.log("[WARN] Not connected.")
            return
        try:
            result = self.wj.hv_off_pulse()
            self.log(f">> HV OFF → {result}")
        except Exception as e:
            self.log(f"[ERROR] HV OFF failed: {e}")

    def _on_reset(self):
        if not self.wj.is_connected:
            self.log("[WARN] Not connected.")
            return
        try:
            result = self.wj.reset_pulse()
            self.log(f">> RESET → {result}")
        except Exception as e:
            self.log(f"[ERROR] RESET failed: {e}")

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------
    def _on_poll(self):
        if not self.wj.is_connected:
            return
        try:
            data = self.wj.query()
        except Exception as e:
            self.log(f"[ERROR] Query failed: {e}")
            return

        if data.get("type") == "E":
            self.log(f"<< ERROR {data['code']}: {data['message']}")
            self.lbl_fault.setText(f"Fault: ERROR {data['code']}")
            return
        if data.get("type") != "R":
            # Ignore weird packets, but log once
            self.log(f"<< {data}")
            return

        kv = data["kv"]
        ma = data["ma"]
        hv_on = data["hv_on"]
        fault = data["fault"]
        mode = data["control_mode"]

        # Update labels
        self.lbl_kv.setText(f"kV: {kv:6.2f}")
        self.lbl_ma.setText(f"mA: {ma:6.3f}")
        self.lbl_mode.setText(f"Mode: {mode}")
        self.lbl_hv.setText("HV: ON" if hv_on else "HV: OFF")
        self.lbl_fault.setText("Fault: YES" if fault else "Fault: NONE")

        # Update buffers + plot
        t = time.time() - self._t0
        self.time_buf.append(t)
        self.v_buf.append(kv)
        self.i_buf.append(ma)

        self.curve_v.setData(list(self.time_buf), list(self.v_buf))
        self.curve_i.setData(list(self.time_buf), list(self.i_buf))
