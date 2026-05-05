"""
Glassman WR125 + Portenta Machine Control Test GUI

Connects to two Arduinos over serial:
  1. Portenta Machine Control — pressure regulator (AO2), Glassman V/I program
     (AO0/AO1), digital outputs, and analog-input streaming.
  2. Arduino Mega — Glassman HV monitor (V-MON / I-MON) and HV ENABLE relay.

Requirements:  PyQt6, pyserial
"""

import sys
import re
import json
import time
import os
import serial
import serial.tools.list_ports
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QPushButton, QDoubleSpinBox, QComboBox,
    QTextEdit, QGridLayout, QMessageBox, QSizePolicy, QDialog,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import QFont, QColor


# ═══════════════════════════════════════════════════════════════════════
# Serial helpers
# ═══════════════════════════════════════════════════════════════════════

def list_serial_ports():
    return [p.device for p in serial.tools.list_ports.comports()]


class SerialDevice:
    """Thin wrapper around pyserial with send/receive helpers."""

    def __init__(self):
        self.ser: serial.Serial | None = None

    @property
    def is_connected(self):
        return self.ser is not None and self.ser.is_open

    def connect(self, port: str, baud: int = 115200):
        if self.is_connected:
            self.ser.close()
        self.ser = serial.Serial(port, baud, timeout=0.1, write_timeout=0.1)
        time.sleep(2.0)  # wait for Arduino reset
        self.ser.reset_input_buffer()

    def send(self, cmd: str):
        if not self.is_connected:
            raise RuntimeError("Not connected")
        self.ser.write((cmd + "\n").encode("ascii"))

    def send_recv(self, cmd: str) -> str:
        self.send(cmd)
        return self.readline()

    def readline(self) -> str:
        if not self.is_connected:
            return ""
        try:
            return self.ser.readline().decode(errors="ignore").strip()
        except Exception:
            return ""

    def read_all_lines(self) -> list[str]:
        lines = []
        if not self.is_connected:
            return lines
        while self.ser.in_waiting:
            line = self.readline()
            if line:
                lines.append(line)
        return lines

    def close(self):
        if self.is_connected:
            self.ser.close()
            self.ser = None


# ═══════════════════════════════════════════════════════════════════════
# Stream reader thread for Portenta DATA lines
# ═══════════════════════════════════════════════════════════════════════

class SerialReaderThread(QThread):
    """Background thread that reads lines from a serial device."""
    line_received = pyqtSignal(str)

    def __init__(self, device: SerialDevice):
        super().__init__()
        self.device = device
        self._running = True

    def run(self):
        while self._running:
            if not self.device.is_connected:
                self.msleep(100)
                continue
            try:
                raw = self.device.readline()
            except Exception:
                self.msleep(50)
                continue
            if not raw:
                self.msleep(10)
                continue
            self.line_received.emit(raw)

    def stop(self):
        self._running = False
        self.wait(2000)


class PortentaStreamThread(SerialReaderThread):
    """Reads serial lines from the Portenta and emits DATA rows."""
    data_received = pyqtSignal(dict)

    def run(self):
        while self._running:
            if not self.device.is_connected:
                self.msleep(100)
                continue
            try:
                raw = self.device.readline()
            except Exception:
                self.msleep(50)
                continue
            if not raw:
                self.msleep(10)
                continue

            self.line_received.emit(raw)

            if raw.startswith("DATA,"):
                parts = raw.split(",")
                if len(parts) >= 13:
                    try:
                        d = {
                            "count":        int(parts[1]),
                            "mA0":          float(parts[2]),
                            "mA1":          float(parts[3]),
                            "raw2":         int(parts[4]),
                            "measured_psi": float(parts[5]),
                            "target_psi":   float(parts[6]),
                            "ao2_v":        float(parts[7]),
                            "expected_psi": float(parts[8]),
                            "ao0_v":        float(parts[9]),
                            "hv_kv_set":    float(parts[10]),
                            "ao1_v":        float(parts[11]),
                            "hv_ma_set":    float(parts[12]),
                        }
                        self.data_received.emit(d)
                    except (ValueError, IndexError):
                        pass


# ═══════════════════════════════════════════════════════════════════════
# Main window
# ═══════════════════════════════════════════════════════════════════════

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "port_memory.json")


def _load_port_memory() -> dict:
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_port_memory(data: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)


class GlassmanTestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Glassman WR125 Test GUI")
        self.setGeometry(100, 100, 1100, 750)

        self._port_memory = _load_port_memory()
        self.portenta = SerialDevice()
        self.mega = SerialDevice()
        self.stream_thread: PortentaStreamThread | None = None
        self.mega_thread: SerialReaderThread | None = None

        # Live raw pin voltages from Mega (used by calibration dialog)
        self.mega_vmon_pin = 0.0
        self.mega_imon_pin = 0.0

        # Calibration constants: terminal_v = slope * pin_v + intercept
        # Defaults assume divider ratio of 3.0, zero intercept
        self.vmon_cal_slope = 3.0
        self.vmon_cal_intercept = 0.0
        self.imon_cal_slope = 3.0
        self.imon_cal_intercept = 0.0
        self.vmon_full_scale_v = 10.0   # terminal V at full-scale (cmd=10V)
        self.imon_full_scale_v = 10.0

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # ── Connection bar ──
        root.addWidget(self._build_connection_bar())

        # ── Main body: left = controls, right = readings ──
        body = QHBoxLayout()
        root.addLayout(body)

        left = QVBoxLayout()
        left.addWidget(self._build_pressure_group())
        left.addWidget(self._build_glassman_command_group())
        left.addWidget(self._build_digital_output_group())
        left.addStretch()
        body.addLayout(left, stretch=1)

        right = QVBoxLayout()
        right.addWidget(self._build_hv_monitor_group())
        right.addWidget(self._build_portenta_readings_group())
        right.addWidget(self._build_log_group())
        body.addLayout(right, stretch=1)

        # Recompute calibration from existing JSON if present
        self._recompute_cal_from_json()

    # ───────────────────────────── Connection bar ─────────────────────
    def _build_connection_bar(self) -> QGroupBox:
        grp = QGroupBox("Connections")
        lay = QHBoxLayout(grp)

        # Portenta
        lay.addWidget(QLabel("Portenta:"))
        self.combo_portenta = QComboBox()
        self.combo_portenta.setMinimumWidth(120)
        lay.addWidget(self.combo_portenta)
        self.btn_connect_portenta = QPushButton("Connect")
        self.btn_connect_portenta.clicked.connect(self._connect_portenta)
        lay.addWidget(self.btn_connect_portenta)
        self.lbl_portenta_status = QLabel("⬤ Disconnected")
        self.lbl_portenta_status.setStyleSheet("color: red;")
        lay.addWidget(self.lbl_portenta_status)

        lay.addSpacing(30)

        # Mega
        lay.addWidget(QLabel("Mega:"))
        self.combo_mega = QComboBox()
        self.combo_mega.setMinimumWidth(120)
        lay.addWidget(self.combo_mega)
        self.btn_connect_mega = QPushButton("Connect")
        self.btn_connect_mega.clicked.connect(self._connect_mega)
        lay.addWidget(self.btn_connect_mega)
        self.lbl_mega_status = QLabel("⬤ Disconnected")
        self.lbl_mega_status.setStyleSheet("color: red;")
        lay.addWidget(self.lbl_mega_status)

        lay.addSpacing(30)

        self.btn_refresh_ports = QPushButton("Refresh Ports")
        self.btn_refresh_ports.clicked.connect(self._refresh_ports)
        lay.addWidget(self.btn_refresh_ports)

        lay.addStretch()
        self._refresh_ports()
        return grp

    # ───────────────────────────── Pressure (Portenta AO2) ───────────
    def _build_pressure_group(self) -> QGroupBox:
        grp = QGroupBox("Pressure Regulator (Portenta AO2)")
        lay = QVBoxLayout(grp)

        row = QHBoxLayout()
        row.addWidget(QLabel("Setpoint:"))
        self.spin_psi = QDoubleSpinBox()
        self.spin_psi.setRange(0, 24.49)
        self.spin_psi.setDecimals(2)
        self.spin_psi.setSingleStep(0.5)
        self.spin_psi.setSuffix(" PSI")
        row.addWidget(self.spin_psi)
        self.btn_set_psi = QPushButton("Set PSI")
        self.btn_set_psi.setStyleSheet("background-color:#4CAF50;color:white;font-weight:bold;padding:4px 10px;")
        self.btn_set_psi.clicked.connect(self._set_pressure)
        row.addWidget(self.btn_set_psi)
        self.btn_zero_pressure = QPushButton("ZERO")
        self.btn_zero_pressure.setStyleSheet("background-color:#f44336;color:white;font-weight:bold;padding:4px 10px;")
        self.btn_zero_pressure.clicked.connect(lambda: self._send_portenta("PSI 0"))
        row.addWidget(self.btn_zero_pressure)
        row.addStretch()
        lay.addLayout(row)

        self.lbl_pressure_out = QLabel("Output: — V  (— PSI)")
        self.lbl_pressure_out.setStyleSheet("font-weight:bold;")
        lay.addWidget(self.lbl_pressure_out)
        return grp

    # ───────────────────── Glassman V/I commands (Portenta AO0/AO1) ──
    def _build_glassman_command_group(self) -> QGroupBox:
        grp = QGroupBox("Glassman Commands (Portenta AO0 / AO1)")
        lay = QVBoxLayout(grp)

        # --- Voltage command row ---
        volt_row = QHBoxLayout()
        volt_row.addWidget(QLabel("HV Voltage:"))
        self.spin_hv_volt = QDoubleSpinBox()
        self.spin_hv_volt.setRange(0, 10)
        self.spin_hv_volt.setDecimals(3)
        self.spin_hv_volt.setSingleStep(0.1)
        self.spin_hv_volt.setSuffix(" V")
        volt_row.addWidget(self.spin_hv_volt)
        btn = QPushButton("Set")
        btn.clicked.connect(lambda: self._send_portenta(f"HVVOLT {self.spin_hv_volt.value():.3f}"))
        volt_row.addWidget(btn)
        self.lbl_hv_volt_cmd = QLabel("—")
        volt_row.addWidget(self.lbl_hv_volt_cmd)
        volt_row.addStretch()
        lay.addLayout(volt_row)

        # --- Voltage preset buttons (1-10 V → 12.5-125 kV) ---
        vpreset_row = QHBoxLayout()
        vpreset_row.addWidget(QLabel("kV presets:"))
        for v in range(1, 11):
            kv = v * 12.5
            btn_p = QPushButton(f"{kv:.1f}\nkV")
            btn_p.setFixedSize(52, 40)
            btn_p.setStyleSheet("font-size:10px;")
            btn_p.clicked.connect(lambda checked, volts=v: self._set_hv_volt_preset(volts))
            vpreset_row.addWidget(btn_p)
        vpreset_row.addStretch()
        lay.addLayout(vpreset_row)

        lay.addSpacing(6)

        # --- Current command row ---
        curr_row = QHBoxLayout()
        curr_row.addWidget(QLabel("HV Current:"))
        self.spin_hv_curr = QDoubleSpinBox()
        self.spin_hv_curr.setRange(0, 10)
        self.spin_hv_curr.setDecimals(3)
        self.spin_hv_curr.setSingleStep(0.1)
        self.spin_hv_curr.setSuffix(" V")
        curr_row.addWidget(self.spin_hv_curr)
        btn2 = QPushButton("Set")
        btn2.clicked.connect(lambda: self._send_portenta(f"HVCURR {self.spin_hv_curr.value():.3f}"))
        curr_row.addWidget(btn2)
        self.lbl_hv_curr_cmd = QLabel("—")
        curr_row.addWidget(self.lbl_hv_curr_cmd)
        curr_row.addStretch()
        lay.addLayout(curr_row)

        # --- Current preset buttons (1-10 V → 0.2-2.0 mA) ---
        ipreset_row = QHBoxLayout()
        ipreset_row.addWidget(QLabel("mA presets:"))
        for v in range(1, 11):
            ma = v * 0.2
            btn_p = QPushButton(f"{ma:.1f}\nmA")
            btn_p.setFixedSize(52, 40)
            btn_p.setStyleSheet("font-size:10px;")
            btn_p.clicked.connect(lambda checked, volts=v: self._set_hv_curr_preset(volts))
            ipreset_row.addWidget(btn_p)
        ipreset_row.addStretch()
        lay.addLayout(ipreset_row)

        lay.addSpacing(6)

        # Zero all
        zero_row = QHBoxLayout()
        btn_zero_hv = QPushButton("Zero HV Commands")
        btn_zero_hv.setStyleSheet("background-color:#f44336;color:white;font-weight:bold;padding:4px 10px;")
        btn_zero_hv.clicked.connect(self._zero_hv_commands)
        zero_row.addWidget(btn_zero_hv)
        zero_row.addStretch()
        lay.addLayout(zero_row)

        return grp

    # ───────────────────── Digital outputs (Portenta DO0-DO7) ────────
    def _build_digital_output_group(self) -> QGroupBox:
        grp = QGroupBox("Digital Outputs (Portenta DO0-DO7)")
        lay = QHBoxLayout(grp)
        self.do_buttons: list[QPushButton] = []
        for ch in range(8):
            btn = QPushButton(f"DO{ch}\nOFF")
            btn.setCheckable(True)
            btn.setFixedSize(60, 50)
            btn.setStyleSheet("background-color:#ccc;font-weight:bold;")
            btn.clicked.connect(lambda checked, c=ch: self._toggle_do(c, checked))
            lay.addWidget(btn)
            self.do_buttons.append(btn)

        btn_all_off = QPushButton("ALL\nOFF")
        btn_all_off.setFixedSize(60, 50)
        btn_all_off.setStyleSheet("background-color:#f44336;color:white;font-weight:bold;")
        btn_all_off.clicked.connect(self._all_do_off)
        lay.addWidget(btn_all_off)
        lay.addStretch()
        return grp

    # ───────────────────── HV Monitor (Mega) ─────────────────────────
    def _build_hv_monitor_group(self) -> QGroupBox:
        grp = QGroupBox("HV Monitor (Arduino Mega)")
        lay = QVBoxLayout(grp)

        grid = QGridLayout()
        grid.addWidget(QLabel("Output Voltage:"), 0, 0)
        self.lbl_hv_kv = QLabel("— kV")
        self.lbl_hv_kv.setStyleSheet("font-size:18px;font-weight:bold;color:#1565C0;")
        grid.addWidget(self.lbl_hv_kv, 0, 1)

        grid.addWidget(QLabel("V-MON:"), 0, 2)
        self.lbl_vmon = QLabel("— V")
        grid.addWidget(self.lbl_vmon, 0, 3)

        grid.addWidget(QLabel("Output Current:"), 1, 0)
        self.lbl_hv_ma = QLabel("— mA")
        self.lbl_hv_ma.setStyleSheet("font-size:18px;font-weight:bold;color:#C62828;")
        grid.addWidget(self.lbl_hv_ma, 1, 1)

        grid.addWidget(QLabel("I-MON:"), 1, 2)
        self.lbl_imon = QLabel("— V")
        grid.addWidget(self.lbl_imon, 1, 3)

        lay.addLayout(grid)

        hv_row = QHBoxLayout()
        self.btn_hv_on = QPushButton("HV ENABLE ON")
        self.btn_hv_on.setStyleSheet("background-color:#4CAF50;color:white;font-weight:bold;padding:6px 16px;")
        self.btn_hv_on.clicked.connect(lambda: self._send_mega("ON"))
        hv_row.addWidget(self.btn_hv_on)

        self.btn_hv_off = QPushButton("HV ENABLE OFF")
        self.btn_hv_off.setStyleSheet("background-color:#f44336;color:white;font-weight:bold;padding:6px 16px;")
        self.btn_hv_off.clicked.connect(lambda: self._send_mega("OFF"))
        hv_row.addWidget(self.btn_hv_off)

        self.lbl_hv_enable = QLabel("HV: —")
        self.lbl_hv_enable.setStyleSheet("font-weight:bold;font-size:14px;")
        hv_row.addWidget(self.lbl_hv_enable)
        hv_row.addStretch()
        lay.addLayout(hv_row)

        # Raw pin voltage display + calibrate button
        pin_row = QHBoxLayout()
        pin_row.addWidget(QLabel("V_MON pin:"))
        self.lbl_vmon_pin = QLabel("— V")
        self.lbl_vmon_pin.setStyleSheet("font-weight:bold;")
        pin_row.addWidget(self.lbl_vmon_pin)
        pin_row.addSpacing(20)
        pin_row.addWidget(QLabel("I_MON pin:"))
        self.lbl_imon_pin = QLabel("— V")
        self.lbl_imon_pin.setStyleSheet("font-weight:bold;")
        pin_row.addWidget(self.lbl_imon_pin)
        pin_row.addSpacing(20)
        self.btn_calibrate = QPushButton("Calibrate V/I Monitor")
        self.btn_calibrate.setStyleSheet("background-color:#FF9800;color:white;font-weight:bold;padding:4px 12px;")
        self.btn_calibrate.clicked.connect(self._open_calibration_dialog)
        pin_row.addWidget(self.btn_calibrate)
        pin_row.addStretch()
        lay.addLayout(pin_row)

        return grp

    # ───────────────────── Portenta live readings ────────────────────
    def _build_portenta_readings_group(self) -> QGroupBox:
        grp = QGroupBox("Portenta Live Readings")
        lay = QGridLayout(grp)

        labels = [
            ("AI0 (mA):", "lbl_ai0"),
            ("AI1 (mA):", "lbl_ai1"),
            ("Measured PSI:", "lbl_meas_psi"),
            ("Target PSI:", "lbl_tgt_psi"),
            ("AO2 (V):", "lbl_ao2"),
            ("HV kV set:", "lbl_hv_kv_set"),
            ("HV mA set:", "lbl_hv_ma_set"),
        ]
        for i, (text, attr) in enumerate(labels):
            lay.addWidget(QLabel(text), i, 0)
            lbl = QLabel("—")
            lbl.setStyleSheet("font-weight:bold;")
            setattr(self, attr, lbl)
            lay.addWidget(lbl, i, 1)
        return grp

    # ───────────────────── Log console ───────────────────────────────
    def _build_log_group(self) -> QGroupBox:
        grp = QGroupBox("Log")
        lay = QVBoxLayout(grp)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(180)
        self.log_text.setStyleSheet("font-family:Consolas,monospace;font-size:11px;")
        lay.addWidget(self.log_text)

        row = QHBoxLayout()
        btn_clear = QPushButton("Clear Log")
        btn_clear.clicked.connect(self.log_text.clear)
        row.addWidget(btn_clear)
        row.addStretch()
        lay.addLayout(row)
        return grp

    # ═══════════════════════════════════════════════════════════════════
    # Actions
    # ═══════════════════════════════════════════════════════════════════

    def _log(self, msg: str):
        self.log_text.append(msg)
        sb = self.log_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _refresh_ports(self):
        ports = list_serial_ports()
        mem = self._port_memory
        for combo, key in ((self.combo_portenta, "portenta"), (self.combo_mega, "mega")):
            prev = combo.currentText()
            combo.clear()
            combo.addItems(ports)
            if prev in ports:
                combo.setCurrentText(prev)
            elif mem.get(key) in ports:
                combo.setCurrentText(mem[key])

    def _connect_portenta(self):
        port = self.combo_portenta.currentText()
        if not port:
            return
        if self.portenta.is_connected:
            self._stop_stream()
            self.portenta.close()
            self.btn_connect_portenta.setText("Connect")
            self.lbl_portenta_status.setText("⬤ Disconnected")
            self.lbl_portenta_status.setStyleSheet("color:red;")
            self._log(f"Portenta disconnected ({port})")
            return
        try:
            self.portenta.connect(port)
            self.btn_connect_portenta.setText("Disconnect")
            self.lbl_portenta_status.setText(f"⬤ {port}")
            self.lbl_portenta_status.setStyleSheet("color:green;")
            self._log(f"Portenta connected on {port}")
            self._port_memory["portenta"] = port
            _save_port_memory(self._port_memory)
            # drain banner
            for line in self.portenta.read_all_lines():
                self._log(f"[PMC] {line}")
            self._start_stream()
        except Exception as e:
            QMessageBox.warning(self, "Connection Error", str(e))

    def _connect_mega(self):
        port = self.combo_mega.currentText()
        if not port:
            return
        if self.mega.is_connected:
            self._stop_mega_thread()
            self.mega.close()
            self.btn_connect_mega.setText("Connect")
            self.lbl_mega_status.setText("⬤ Disconnected")
            self.lbl_mega_status.setStyleSheet("color:red;")
            self._log(f"Mega disconnected ({port})")
            return
        try:
            self.mega.connect(port)
            self.btn_connect_mega.setText("Disconnect")
            self.lbl_mega_status.setText(f"⬤ {port}")
            self.lbl_mega_status.setStyleSheet("color:green;")
            self._log(f"Mega connected on {port}")
            self._port_memory["mega"] = port
            _save_port_memory(self._port_memory)
            self._start_mega_thread()
        except Exception as e:
            QMessageBox.warning(self, "Connection Error", str(e))

    # ── Portenta stream ──────────────────────────────────────────────
    def _start_stream(self):
        self.stream_thread = PortentaStreamThread(self.portenta)
        self.stream_thread.data_received.connect(self._on_portenta_data)
        self.stream_thread.line_received.connect(self._on_portenta_line)
        self.stream_thread.start()

    def _stop_stream(self):
        if self.stream_thread:
            self.stream_thread.stop()
            self.stream_thread = None

    def _on_portenta_line(self, line: str):
        if not line.startswith("DATA,"):
            self._log(f"[PMC] {line}")

    def _on_portenta_data(self, d: dict):
        self.lbl_ai0.setText(f"{d['mA0']:.3f} mA")
        self.lbl_ai1.setText(f"{d['mA1']:.3f} mA")
        self.lbl_meas_psi.setText(f"{d['measured_psi']:.3f} PSI")
        self.lbl_tgt_psi.setText(f"{d['target_psi']:.2f} PSI")
        self.lbl_ao2.setText(f"{d['ao2_v']:.2f} V")
        self.lbl_hv_kv_set.setText(f"{d['hv_kv_set']:.2f} kV")
        self.lbl_hv_ma_set.setText(f"{d['hv_ma_set']:.4f} mA")
        self.lbl_pressure_out.setText(
            f"Output: {d['ao2_v']:.3f} V  ({d['measured_psi']:.2f} PSI measured, "
            f"{d['target_psi']:.2f} PSI target)"
        )
        self.lbl_hv_volt_cmd.setText(f"{d['ao0_v']:.3f} V → {d['hv_kv_set']:.2f} kV")
        self.lbl_hv_curr_cmd.setText(f"{d['ao1_v']:.3f} V → {d['hv_ma_set']:.4f} mA")

    # ── Mega stream ───────────────────────────────────────────────────
    def _start_mega_thread(self):
        self.mega_thread = SerialReaderThread(self.mega)
        self.mega_thread.line_received.connect(self._on_mega_line)
        self.mega_thread.start()

    def _stop_mega_thread(self):
        if self.mega_thread:
            self.mega_thread.stop()
            self.mega_thread = None

    def _on_mega_line(self, line: str):
        self._parse_mega_line(line)

    def _parse_mega_line(self, line: str):
        # Mega format: HV=ON | V_MON pin: X.XXXX V | Glassman V_MON: X.XXXX V | Output: X.XX kV || I_MON pin: X.XXXX V | ...
        if "V_MON pin:" not in line and "I_MON pin:" not in line:
            self._log(f"[MEGA] {line}")
            return

        try:
            # HV enable state
            if "HV=ON" in line:
                self.lbl_hv_enable.setText("HV: ON")
                self.lbl_hv_enable.setStyleSheet("font-weight:bold;font-size:14px;color:green;")
            elif "HV=OFF" in line:
                self.lbl_hv_enable.setText("HV: OFF")
                self.lbl_hv_enable.setStyleSheet("font-weight:bold;font-size:14px;color:red;")

            # Raw pin voltages
            m = re.search(r'V_MON pin:\s*([\d.]+)\s*V', line)
            if m:
                self.mega_vmon_pin = float(m.group(1))
                self.lbl_vmon_pin.setText(f"{self.mega_vmon_pin:.4f} V")

            m = re.search(r'I_MON pin:\s*([\d.]+)\s*V', line)
            if m:
                self.mega_imon_pin = float(m.group(1))
                self.lbl_imon_pin.setText(f"{self.mega_imon_pin:.4f} V")

            # Calibrated Glassman V_MON (computed on Mega)
            m = re.search(r'Glassman V_MON:\s*([\d.]+)\s*V', line)
            if m:
                self.lbl_vmon.setText(f"{float(m.group(1)):.3f} V")

            # Output kV (computed on Mega)
            m = re.search(r'Output:\s*([\d.]+)\s*kV', line)
            if m:
                self.lbl_hv_kv.setText(f"{float(m.group(1)):.2f} kV")

            # I_MON — Mega sends "N/A" for now, so just show pin voltage
            m = re.search(r'Glassman I_MON:\s*([\d.]+)\s*V', line)
            if m:
                self.lbl_imon.setText(f"{float(m.group(1)):.3f} V")

            m = re.search(r'Output:\s*([\d.]+)\s*mA', line)
            if m:
                self.lbl_hv_ma.setText(f"{float(m.group(1)):.4f} mA")
        except (ValueError, IndexError):
            self._log(f"[MEGA] parse error: {line}")

    # ── Send helpers ─────────────────────────────────────────────────
    def _send_portenta(self, cmd: str):
        if not self.portenta.is_connected:
            self._log("ERROR: Portenta not connected")
            return
        self.portenta.send(cmd)
        self._log(f"→ PMC: {cmd}")

    def _send_mega(self, cmd: str):
        if not self.mega.is_connected:
            self._log("ERROR: Mega not connected")
            return
        self.mega.send(cmd)
        self._log(f"→ MEGA: {cmd}")

    # ── Pressure ─────────────────────────────────────────────────────
    def _set_pressure(self):
        psi = self.spin_psi.value()
        self._send_portenta(f"PSI {psi:.2f}")

    # ── HV presets ────────────────────────────────────────────────────
    def _set_hv_volt_preset(self, volts: int):
        self.spin_hv_volt.setValue(float(volts))
        self._send_portenta(f"HVVOLT {volts:.3f}")

    def _set_hv_curr_preset(self, volts: int):
        self.spin_hv_curr.setValue(float(volts))
        self._send_portenta(f"HVCURR {volts:.3f}")

    # ── HV command zero ──────────────────────────────────────────────
    def _zero_hv_commands(self):
        self._send_portenta("HVVOLT 0")
        self._send_portenta("HVCURR 0")
        self.spin_hv_volt.setValue(0)
        self.spin_hv_curr.setValue(0)

    # ── Digital outputs ──────────────────────────────────────────────
    def _toggle_do(self, ch: int, state: bool):
        cmd = f"ON {ch}" if state else f"OFF {ch}"
        self._send_portenta(cmd)
        btn = self.do_buttons[ch]
        if state:
            btn.setText(f"DO{ch}\nON")
            btn.setStyleSheet("background-color:#4CAF50;color:white;font-weight:bold;")
        else:
            btn.setText(f"DO{ch}\nOFF")
            btn.setStyleSheet("background-color:#ccc;font-weight:bold;")

    def _all_do_off(self):
        self._send_portenta("ALL OFF")
        for ch, btn in enumerate(self.do_buttons):
            btn.setChecked(False)
            btn.setText(f"DO{ch}\nOFF")
            btn.setStyleSheet("background-color:#ccc;font-weight:bold;")

    # ── Recompute calibration from saved JSON ──────────────────────────
    def _recompute_cal_from_json(self):
        """Recompute V-MON / I-MON calibration from existing vmon_cal.json.

        Uses the commanded voltage (cmd_v) and measured terminal voltages,
        then reconstructs pin voltages via the known 3:1 resistor divider
        (Glassman internal 10K + two external 10K).
        """
        cal_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vmon_cal.json")
        try:
            with open(cal_path, "r") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return

        points = data.get("points", [])
        if len(points) < 2:
            return

        DIVIDER_RATIO = 3.0  # Glassman 10K internal + 10K + 10K external

        # Step 1: linear regression of cmd_v vs vmon_terminal_v
        cmd_v = [p["cmd_v"] for p in points]
        vterm = [p["vmon_terminal_v"] for p in points]
        iterm = [p["imon_terminal_v"] for p in points]

        vt_slope, vt_intercept, vt_r2 = _linreg(cmd_v, vterm)
        it_slope, it_intercept, it_r2 = _linreg(cmd_v, iterm)

        # Step 2: compute expected Arduino pin voltage at each point
        vpin = [t / DIVIDER_RATIO for t in vterm]
        ipin = [t / DIVIDER_RATIO for t in iterm]

        # Step 3: linear regression of pin voltage vs terminal voltage
        # terminal = SLOPE * pin + INTERCEPT
        v_div_slope, v_div_intercept, v_div_r2 = _linreg(vpin, vterm)
        i_div_slope, i_div_intercept, i_div_r2 = _linreg(ipin, iterm)

        # Full-scale: at cmd_v=10, what terminal voltage does the Glassman produce?
        vmon_full_scale = vt_slope * 10.0 + vt_intercept
        imon_full_scale = it_slope * 10.0 + it_intercept

        # Store calibration constants for live GUI use
        self.vmon_cal_slope = v_div_slope
        self.vmon_cal_intercept = v_div_intercept
        self.imon_cal_slope = i_div_slope
        self.imon_cal_intercept = i_div_intercept

        lines = [
            "═══════════ CALIBRATION RECOMPUTED FROM vmon_cal.json ═══════════",
            "",
            f"  Divider ratio: {DIVIDER_RATIO:.1f}  (Glassman 10K internal + 10K + 10K external)",
            "",
            "  ── CMD_V → TERMINAL TRANSFER FUNCTION ──",
            f"  V-MON: terminal = {vt_slope:.6f} × cmd_v + {vt_intercept:.6f}   R² = {vt_r2:.6f}",
            f"  I-MON: terminal = {it_slope:.6f} × cmd_v + {it_intercept:.6f}   R² = {it_r2:.6f}",
            "",
            f"  V-MON full-scale at 10V cmd: {vmon_full_scale:.4f} V terminal",
            f"  I-MON full-scale at 10V cmd: {imon_full_scale:.4f} V terminal",
            "",
            "  ── PIN → TERMINAL (DIVIDER CALIBRATION) ──",
            f"  V-MON: terminal = {v_div_slope:.6f} × pin + {v_div_intercept:.6f}   R² = {v_div_r2:.6f}",
            f"  I-MON: terminal = {i_div_slope:.6f} × pin + {i_div_intercept:.6f}   R² = {i_div_r2:.6f}",
            "",
            "  ── ARDUINO SKETCH CONSTANTS ──",
            f"  const float DIVIDER_RATIO    = {DIVIDER_RATIO:.1f}f;",
            f"  const float VMON_FULL_SCALE_V = {vmon_full_scale:.4f}f;   // terminal V at cmd=10V",
            f"  const float IMON_FULL_SCALE_V = {imon_full_scale:.4f}f;   // terminal V at cmd=10V",
            "",
            "  // outputKV = (vMonPinVolts * DIVIDER_RATIO / VMON_FULL_SCALE_V) * 125.0;",
            "  // outputMA = (iMonPinVolts * DIVIDER_RATIO / IMON_FULL_SCALE_V) * 2.0;",
            "",
            "  ── GUI LIVE CONVERSION (pin → kV / mA) ──",
            f"  kV = (pin × {v_div_slope:.4f} + {v_div_intercept:.4f}) / {vmon_full_scale:.4f} × 125.0",
            f"  mA = (pin × {i_div_slope:.4f} + {i_div_intercept:.4f}) / {imon_full_scale:.4f} × 2.0",
            "═══════════════════════════════════════════════════════════════════",
        ]

        # Store full-scale for live kV/mA conversion
        self.vmon_full_scale_v = vmon_full_scale
        self.imon_full_scale_v = imon_full_scale

        for line in lines:
            self._log(line)

    # ── Calibration dialog ─────────────────────────────────────────────
    def _open_calibration_dialog(self):
        dlg = CalibrationDialog(self)
        dlg.show()

    # ── Cleanup ──────────────────────────────────────────────────────
    def closeEvent(self, event):
        self._stop_stream()
        self._stop_mega_thread()
        self.portenta.close()
        self.mega.close()
        event.accept()


# ═══════════════════════════════════════════════════════════════════════
# Linear regression (no numpy dependency)
# ═══════════════════════════════════════════════════════════════════════

def _linreg(x: list[float], y: list[float]) -> tuple[float, float, float]:
    """Least-squares linear fit y = slope*x + intercept.  Returns (slope, intercept, r_squared)."""
    n = len(x)
    if n < 2:
        return 0.0, 0.0, 0.0
    sx = sum(x)
    sy = sum(y)
    sxx = sum(xi * xi for xi in x)
    sxy = sum(xi * yi for xi, yi in zip(x, y))
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-15:
        return 0.0, 0.0, 0.0
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    ss_res = sum((yi - (slope * xi + intercept)) ** 2 for xi, yi in zip(x, y))
    mean_y = sy / n
    ss_tot = sum((yi - mean_y) ** 2 for yi in y)
    r2 = 1.0 - ss_res / ss_tot if abs(ss_tot) > 1e-15 else 0.0
    return slope, intercept, r2


# ═══════════════════════════════════════════════════════════════════════
# Calibration dialog
# ═══════════════════════════════════════════════════════════════════════

CAL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vmon_cal.json")

# Calibration points: commanded voltage on AO0 (0-10 V)
CAL_VOLTAGES = list(range(0, 11))  # 0, 1, 2, ... 10
CAL_KV = [v * 12.5 for v in CAL_VOLTAGES]  # 0, 12.5, 25, ... 125


class CalibrationDialog(QDialog):
    def __init__(self, parent: GlassmanTestWindow):
        super().__init__(parent)
        self.main = parent
        self.setWindowTitle("V-MON / I-MON Calibration")
        self.setMinimumSize(900, 600)

        # Collected data: list of dicts
        self.points: list[dict] = []
        self.current_index = 0

        root = QVBoxLayout(self)

        # ── Status row ───────────────────────────────────────────────
        status_row = QHBoxLayout()
        self.lbl_step = QLabel("")
        self.lbl_step.setStyleSheet("font-size:14px;font-weight:bold;")
        status_row.addWidget(self.lbl_step)
        status_row.addStretch()
        root.addLayout(status_row)

        # ── Live readings ────────────────────────────────────────────
        live_grp = QGroupBox("Live Mega Readings")
        live_lay = QHBoxLayout(live_grp)
        live_lay.addWidget(QLabel("V_MON pin:"))
        self.lbl_live_vmon = QLabel("— V")
        self.lbl_live_vmon.setStyleSheet("font-weight:bold;font-size:14px;color:#1565C0;")
        live_lay.addWidget(self.lbl_live_vmon)
        live_lay.addSpacing(30)
        live_lay.addWidget(QLabel("I_MON pin:"))
        self.lbl_live_imon = QLabel("— V")
        self.lbl_live_imon.setStyleSheet("font-weight:bold;font-size:14px;color:#C62828;")
        live_lay.addWidget(self.lbl_live_imon)
        live_lay.addStretch()
        root.addWidget(live_grp)

        # ── User input row ───────────────────────────────────────────
        input_grp = QGroupBox("Multimeter Readings (enter actual terminal strip voltage)")
        input_lay = QHBoxLayout(input_grp)
        input_lay.addWidget(QLabel("V-MON terminal (V):"))
        self.edit_vmon = QLineEdit("0.000")
        self.edit_vmon.setFixedWidth(100)
        input_lay.addWidget(self.edit_vmon)
        input_lay.addSpacing(20)
        input_lay.addWidget(QLabel("I-MON terminal (V):"))
        self.edit_imon = QLineEdit("0.000")
        self.edit_imon.setFixedWidth(100)
        input_lay.addWidget(self.edit_imon)
        input_lay.addStretch()
        root.addWidget(input_grp)

        # ── Buttons ──────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self.btn_set_voltage = QPushButton("Set Voltage && Advance")
        self.btn_set_voltage.setStyleSheet("background-color:#1565C0;color:white;font-weight:bold;padding:6px 16px;")
        self.btn_set_voltage.clicked.connect(self._set_current_voltage)
        btn_row.addWidget(self.btn_set_voltage)

        self.btn_record = QPushButton("Record Point")
        self.btn_record.setStyleSheet("background-color:#4CAF50;color:white;font-weight:bold;padding:6px 16px;")
        self.btn_record.clicked.connect(self._record_point)
        btn_row.addWidget(self.btn_record)

        self.btn_compute = QPushButton("Compute Calibration")
        self.btn_compute.setStyleSheet("background-color:#FF9800;color:white;font-weight:bold;padding:6px 16px;")
        self.btn_compute.clicked.connect(self._compute_calibration)
        self.btn_compute.setEnabled(False)
        btn_row.addWidget(self.btn_compute)

        self.btn_save = QPushButton("Save to JSON")
        self.btn_save.setStyleSheet("background-color:#9C27B0;color:white;font-weight:bold;padding:6px 16px;")
        self.btn_save.clicked.connect(self._save_json)
        self.btn_save.setEnabled(False)
        btn_row.addWidget(self.btn_save)

        btn_row.addStretch()
        root.addLayout(btn_row)

        # ── Auto-calibrate row ───────────────────────────────────────
        auto_row = QHBoxLayout()
        self.btn_auto_cal = QPushButton("Auto Calibrate (from JSON + live pin voltages)")
        self.btn_auto_cal.setStyleSheet("background-color:#E65100;color:white;font-weight:bold;padding:6px 16px;")
        self.btn_auto_cal.clicked.connect(self._start_auto_calibration)
        auto_row.addWidget(self.btn_auto_cal)
        self.btn_stop_auto = QPushButton("Stop")
        self.btn_stop_auto.setStyleSheet("background-color:#f44336;color:white;font-weight:bold;padding:6px 16px;")
        self.btn_stop_auto.clicked.connect(self._stop_auto_calibration)
        self.btn_stop_auto.setEnabled(False)
        auto_row.addWidget(self.btn_stop_auto)
        self.lbl_auto_status = QLabel("")
        self.lbl_auto_status.setStyleSheet("font-weight:bold;")
        auto_row.addWidget(self.lbl_auto_status)
        auto_row.addStretch()
        root.addLayout(auto_row)

        # ── Data table ───────────────────────────────────────────────
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "Cmd (V)", "kV", "V_MON pin (V)", "V-MON terminal (V)",
            "I_MON pin (V)", "I-MON terminal (V)", "Status",
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        root.addWidget(self.table)

        # ── Results text ─────────────────────────────────────────────
        self.txt_results = QTextEdit()
        self.txt_results.setReadOnly(True)
        self.txt_results.setMaximumHeight(200)
        self.txt_results.setStyleSheet("font-family:Consolas,monospace;font-size:11px;")
        root.addWidget(self.txt_results)

        # Calibration results storage
        self.cal_results: dict | None = None

        # Timer to update live readings
        self.live_timer = QTimer()
        self.live_timer.timeout.connect(self._update_live)
        self.live_timer.start(200)

        self._update_step_label()

    def _update_step_label(self):
        if self.current_index < len(CAL_VOLTAGES):
            v = CAL_VOLTAGES[self.current_index]
            kv = CAL_KV[self.current_index]
            self.lbl_step.setText(
                f"Step {self.current_index + 1}/{len(CAL_VOLTAGES)}:  "
                f"Command {v} V  ({kv:.1f} kV)"
            )
            self.btn_set_voltage.setEnabled(True)
            self.btn_record.setEnabled(True)
        else:
            self.lbl_step.setText(f"All {len(CAL_VOLTAGES)} points recorded.  Click Compute Calibration.")
            self.btn_set_voltage.setEnabled(False)
            self.btn_record.setEnabled(False)
            self.btn_compute.setEnabled(True)

    def _update_live(self):
        self.lbl_live_vmon.setText(f"{self.main.mega_vmon_pin:.4f} V")
        self.lbl_live_imon.setText(f"{self.main.mega_imon_pin:.4f} V")

    def _set_current_voltage(self):
        if self.current_index >= len(CAL_VOLTAGES):
            return
        v = CAL_VOLTAGES[self.current_index]
        self.main._send_portenta(f"HVVOLT {v:.3f}")
        self.main.spin_hv_volt.setValue(float(v))

    def _record_point(self):
        if self.current_index >= len(CAL_VOLTAGES):
            return

        try:
            vmon_terminal = float(self.edit_vmon.text())
        except ValueError:
            QMessageBox.warning(self, "Input Error", "V-MON terminal voltage must be a number.")
            return
        try:
            imon_terminal = float(self.edit_imon.text())
        except ValueError:
            QMessageBox.warning(self, "Input Error", "I-MON terminal voltage must be a number.")
            return

        cmd_v = CAL_VOLTAGES[self.current_index]
        point = {
            "cmd_v": cmd_v,
            "cmd_kv": CAL_KV[self.current_index],
            "vmon_pin_v": self.main.mega_vmon_pin,
            "vmon_terminal_v": vmon_terminal,
            "imon_pin_v": self.main.mega_imon_pin,
            "imon_terminal_v": imon_terminal,
        }
        self.points.append(point)

        # Add to table
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(f"{cmd_v}"))
        self.table.setItem(row, 1, QTableWidgetItem(f"{point['cmd_kv']:.1f}"))
        self.table.setItem(row, 2, QTableWidgetItem(f"{point['vmon_pin_v']:.4f}"))
        self.table.setItem(row, 3, QTableWidgetItem(f"{vmon_terminal:.4f}"))
        self.table.setItem(row, 4, QTableWidgetItem(f"{point['imon_pin_v']:.4f}"))
        self.table.setItem(row, 5, QTableWidgetItem(f"{imon_terminal:.4f}"))
        self.table.setItem(row, 6, QTableWidgetItem("OK"))

        self.current_index += 1
        self.edit_vmon.setText("0.000")
        self.edit_imon.setText("0.000")
        self._update_step_label()

        # Auto-advance to next voltage if not done
        if self.current_index < len(CAL_VOLTAGES):
            self._set_current_voltage()

    def _compute_calibration(self):
        if len(self.points) < 2:
            QMessageBox.warning(self, "Not Enough Data", "Need at least 2 points to compute calibration.")
            return

        # V-MON: linear regression of terminal voltage vs pin voltage
        vpin = [p["vmon_pin_v"] for p in self.points]
        vterm = [p["vmon_terminal_v"] for p in self.points]
        v_slope, v_intercept, v_r2 = _linreg(vpin, vterm)

        # I-MON: linear regression of terminal voltage vs pin voltage
        ipin = [p["imon_pin_v"] for p in self.points]
        iterm = [p["imon_terminal_v"] for p in self.points]
        i_slope, i_intercept, i_r2 = _linreg(ipin, iterm)

        # Full-scale values at 10V monitor output (pin sees ~5V through 1:1 divider)
        v_full_scale_v = v_slope * 5.0 + v_intercept
        i_full_scale_v = i_slope * 5.0 + i_intercept

        self.cal_results = {
            "points": self.points,
            "vmon": {
                "divider_ratio_slope": round(v_slope, 6),
                "intercept": round(v_intercept, 6),
                "r_squared": round(v_r2, 6),
                "full_scale_terminal_v_at_5v_pin": round(v_full_scale_v, 4),
            },
            "imon": {
                "divider_ratio_slope": round(i_slope, 6),
                "intercept": round(i_intercept, 6),
                "r_squared": round(i_r2, 6),
                "full_scale_terminal_v_at_5v_pin": round(i_full_scale_v, 4),
            },
        }

        lines = [
            "═══════════════════════════════════════════════════════",
            "  V-MON CALIBRATION",
            "═══════════════════════════════════════════════════════",
            f"  Divider ratio (slope):  {v_slope:.6f}  (terminal = {v_slope:.4f} × pin + {v_intercept:.4f})",
            f"  R²:                     {v_r2:.6f}",
            f"  Full-scale terminal V at pin=5V: {v_full_scale_v:.4f} V",
            "",
            "═══════════════════════════════════════════════════════",
            "  I-MON CALIBRATION",
            "═══════════════════════════════════════════════════════",
            f"  Divider ratio (slope):  {i_slope:.6f}  (terminal = {i_slope:.4f} × pin + {i_intercept:.4f})",
            f"  R²:                     {i_r2:.6f}",
            f"  Full-scale terminal V at pin=5V: {i_full_scale_v:.4f} V",
            "",
            "═══════════════════════════════════════════════════════",
            "  ARDUINO CODE (paste into sketch)",
            "═══════════════════════════════════════════════════════",
            f"  const float VMON_DIVIDER_SLOPE     = {v_slope:.6f};",
            f"  const float VMON_DIVIDER_INTERCEPT  = {v_intercept:.6f};",
            f"  const float IMON_DIVIDER_SLOPE      = {i_slope:.6f};",
            f"  const float IMON_DIVIDER_INTERCEPT   = {i_intercept:.6f};",
            "",
            "  // Usage:  actual_terminal_V = SLOPE * pin_V + INTERCEPT",
            f"  // V-MON R² = {v_r2:.6f},  I-MON R² = {i_r2:.6f}",
        ]
        self.txt_results.setPlainText("\n".join(lines))
        self.btn_save.setEnabled(True)

    def _save_json(self):
        if not self.cal_results:
            return
        try:
            with open(CAL_FILE, "w") as f:
                json.dump(self.cal_results, f, indent=2)
            QMessageBox.information(self, "Saved", f"Calibration saved to:\n{CAL_FILE}")
        except Exception as e:
            QMessageBox.warning(self, "Save Error", str(e))

    # ── Auto-calibration ───────────────────────────────────────────────
    def _start_auto_calibration(self):
        # Load existing terminal voltages from JSON
        try:
            with open(CAL_FILE, "r") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            QMessageBox.warning(self, "No Data", "vmon_cal.json not found. Run manual calibration first.")
            return

        json_points = data.get("points", [])
        if len(json_points) != len(CAL_VOLTAGES):
            QMessageBox.warning(self, "Data Mismatch",
                                f"Expected {len(CAL_VOLTAGES)} points in JSON, found {len(json_points)}.")
            return

        if not self.main.mega.is_connected:
            QMessageBox.warning(self, "Not Connected", "Mega is not connected.")
            return
        if not self.main.portenta.is_connected:
            QMessageBox.warning(self, "Not Connected", "Portenta is not connected.")
            return

        # Confirm HV will be enabled
        reply = QMessageBox.warning(
            self, "HV Will Be Applied",
            "This will command real voltages on AO0 with HV ENABLE ON.\n"
            "The Glassman will output up to 125 kV.\n\n"
            "Make sure the load is safe. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Reset state
        self.points.clear()
        self.table.setRowCount(0)
        self.current_index = 0
        self.txt_results.clear()
        self.cal_results = None
        self.btn_compute.setEnabled(False)
        self.btn_save.setEnabled(False)

        self._auto_json_points = json_points
        self._auto_samples: list[tuple[float, float]] = []  # (vmon, imon) samples
        self._auto_settle_remaining = 0
        self._auto_running = True

        # Disable manual controls during auto-cal
        self.btn_set_voltage.setEnabled(False)
        self.btn_record.setEnabled(False)
        self.btn_auto_cal.setEnabled(False)
        self.btn_stop_auto.setEnabled(True)

        # Enable HV
        self.main._send_mega("ON")

        # Timer drives the state machine (200ms ticks)
        self._auto_timer = QTimer()
        self._auto_timer.timeout.connect(self._auto_tick)
        self._auto_timer.start(200)

        # Start first point
        self._auto_begin_point()

    def _stop_auto_calibration(self):
        self._auto_running = False
        if hasattr(self, '_auto_timer'):
            self._auto_timer.stop()
        # Zero output and disable HV for safety
        self.main._send_portenta("HVVOLT 0")
        self.main.spin_hv_volt.setValue(0)
        self.main._send_mega("OFF")
        self.lbl_auto_status.setText("Auto-cal stopped.")
        self.btn_auto_cal.setEnabled(True)
        self.btn_stop_auto.setEnabled(False)
        self.btn_set_voltage.setEnabled(True)
        self.btn_record.setEnabled(True)
        self._update_step_label()

    def _auto_begin_point(self):
        if self.current_index >= len(CAL_VOLTAGES):
            # All done
            self._auto_timer.stop()
            self.main._send_portenta("HVVOLT 0")
            self.main.spin_hv_volt.setValue(0)
            self.main._send_mega("OFF")
            self.lbl_auto_status.setText("Auto-cal complete!")
            self.btn_auto_cal.setEnabled(True)
            self.btn_stop_auto.setEnabled(False)
            self.btn_compute.setEnabled(True)
            self._update_step_label()
            return

        v = CAL_VOLTAGES[self.current_index]
        kv = CAL_KV[self.current_index]
        self.lbl_step.setText(
            f"Step {self.current_index + 1}/{len(CAL_VOLTAGES)}:  "
            f"Command {v} V  ({kv:.1f} kV)"
        )

        # Send voltage command
        self.main._send_portenta(f"HVVOLT {v:.3f}")
        self.main.spin_hv_volt.setValue(float(v))

        # Wait 5 seconds to settle (25 ticks at 200ms)
        self._auto_settle_remaining = 25
        self._auto_samples.clear()
        self.lbl_auto_status.setText(f"Settling... {v} V  (5.0s)")

    def _auto_tick(self):
        if not self._auto_running:
            return

        if self._auto_settle_remaining > 0:
            self._auto_settle_remaining -= 1
            secs_left = self._auto_settle_remaining * 0.2
            self.lbl_auto_status.setText(
                f"Settling... {CAL_VOLTAGES[self.current_index]} V  ({secs_left:.1f}s)"
            )
            return

        # Collecting samples
        self._auto_samples.append((self.main.mega_vmon_pin, self.main.mega_imon_pin))
        n = len(self._auto_samples)
        self.lbl_auto_status.setText(
            f"Sampling {n}/20  V_MON={self.main.mega_vmon_pin:.4f}  I_MON={self.main.mega_imon_pin:.4f}"
        )

        if n >= 20:
            # Average the 20 samples
            avg_vmon = sum(s[0] for s in self._auto_samples) / 20.0
            avg_imon = sum(s[1] for s in self._auto_samples) / 20.0

            jp = self._auto_json_points[self.current_index]
            point = {
                "cmd_v": CAL_VOLTAGES[self.current_index],
                "cmd_kv": CAL_KV[self.current_index],
                "vmon_pin_v": round(avg_vmon, 6),
                "vmon_terminal_v": jp["vmon_terminal_v"],
                "imon_pin_v": round(avg_imon, 6),
                "imon_terminal_v": jp["imon_terminal_v"],
            }
            self.points.append(point)

            # Add to table
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(f"{point['cmd_v']}"))
            self.table.setItem(row, 1, QTableWidgetItem(f"{point['cmd_kv']:.1f}"))
            self.table.setItem(row, 2, QTableWidgetItem(f"{avg_vmon:.4f}"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{point['vmon_terminal_v']:.4f}"))
            self.table.setItem(row, 4, QTableWidgetItem(f"{avg_imon:.4f}"))
            self.table.setItem(row, 5, QTableWidgetItem(f"{point['imon_terminal_v']:.4f}"))
            self.table.setItem(row, 6, QTableWidgetItem("AUTO"))

            self.current_index += 1
            self._auto_begin_point()

    def closeEvent(self, event):
        self.live_timer.stop()
        if hasattr(self, '_auto_timer'):
            self._auto_timer.stop()
        # Zero the HV voltage command on close for safety
        self.main._send_portenta("HVVOLT 0")
        self.main.spin_hv_volt.setValue(0)
        event.accept()


# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = QApplication(sys.argv)
    font = QFont("Times New Roman")
    font.setBold(True)
    app.setFont(font)
    app.setStyleSheet("* { font-family: 'Times New Roman'; font-weight: bold; color: black; }")

    win = GlassmanTestWindow()
    win.show()
    sys.exit(app.exec())
