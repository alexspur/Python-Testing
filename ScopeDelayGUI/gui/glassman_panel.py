# gui/glassman_panel.py
#
# Glassman WR125 helpers used by the unified WJ panel:
#   - GlassmanMegaReader: background thread that reads V_MON / I_MON /
#     HV state lines from the Mega and emits a parsed dict.
#   - GlassmanCalibrationDialog: V_MON / I_MON divider calibration sweep.
#
# All Glassman commands go through main_window.glassman_send_mega
# (the Mega owns the GP8413 DAC for the V-PROGRAM + pressure setpoints
# and the HV ENABLE relay via D7). The old Portenta path is gone.

import os
import re
import json

from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QDialog, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit, QMessageBox,
)
from PyQt6.QtCore import QThread, QTimer, pyqtSignal

from instruments.glassman import GlassmanSerial


# ── Marx- (A11) kV recompute ─────────────────────────────────────────
# The Mega prints "Marx- mon" = the recovered monitor voltage (0 V at rest,
# rising as the negative rail charges), but its own "Marx-:" kV has the wrong
# sign for the current divider wiring and clamps to 0. So we recompute Marx-
# kV here from the monitor voltage:  kV magnitude = mon * MARX_NEG_KV_PER_MON_V.
# Default 20 kV/V = 100 kV at mon=+5 V (ADC ~5 V); ADC 2.5 V = 0 kV. Adjust
# MARX_NEG_KV_PER_MON_V if you want a different full-scale calibration.
MARX_NEG_KV_PER_MON_V = 100.0 / 5.0   # 20 kV per monitor volt
MARX_NEG_FULL_SCALE_KV = 100.0


# ────────────────────────────────────────────────────────────────────
# Background reader thread for the Glassman Mega
# ────────────────────────────────────────────────────────────────────

class GlassmanMegaReader(QThread):
    """Reads V_MON / I_MON / output / HV-state lines from the Mega."""

    raw_line = pyqtSignal(str)
    parsed = pyqtSignal(dict)

    def __init__(self, device: GlassmanSerial):
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
            self._handle_line(raw)

    def _handle_line(self, line: str):
        # Mega lines from the combined V_MON / I_MON / pressure printout.
        # Gate on any of the known field tags so a single shared parser
        # handles every printReadings() variant the Mega might run.
        if ("V_MON pin:" not in line
                and "I_MON pin:" not in line
                and "P pin:" not in line
                and "Marx+:" not in line):
            self.raw_line.emit(line)
            return

        d: dict = {}
        try:
            if "HV=ON" in line:
                d["hv_on"] = True
            elif "HV=OFF" in line:
                d["hv_on"] = False

            m = re.search(r"V_MON pin:\s*([\d.]+)\s*V", line)
            if m:
                d["vmon_pin"] = float(m.group(1))
            m = re.search(r"I_MON pin:\s*([\d.]+)\s*V", line)
            if m:
                d["imon_pin"] = float(m.group(1))
            m = re.search(r"Glassman V_MON:\s*([\d.]+)\s*V", line)
            if m:
                d["vmon"] = float(m.group(1))
            m = re.search(r"Glassman I_MON:\s*([\d.]+)\s*V", line)
            if m:
                d["imon"] = float(m.group(1))
            m = re.search(r"Output:\s*([\d.]+)\s*kV", line)
            if m:
                d["kv"] = float(m.group(1))
            m = re.search(r"Output:\s*([\d.]+)\s*mA", line)
            if m:
                d["ma"] = float(m.group(1))

            # New pressure fields from the Mega (A3, 0-10 V sensor → 0-100 psi).
            m = re.search(r"P pin:\s*([\d.]+)\s*V", line)
            if m:
                d["pressure_pin"] = float(m.group(1))
            m = re.search(r"Sensor:\s*([\d.]+)\s*V", line)
            if m:
                d["pressure_v"] = float(m.group(1))
            m = re.search(r"Pressure:\s*([\d.]+)\s*psi", line, re.IGNORECASE)
            if m:
                d["psi"] = float(m.group(1))

            # Marx+ (A10) is a direct 0-5 V monitor:
            #   "Marx+: <pin> V -> <kV> kV"
            m = re.search(r"Marx\+:\s*([\d.]+)\s*V\s*->\s*([\d.]+)\s*kV", line)
            if m:
                d["marx_pos_pin"] = float(m.group(1))
                d["marx_pos_kv"] = float(m.group(2))

            # Marx- (A11) is read through a summing divider: the ADC pin sits
            # at ~2.5 V at rest and rises toward ~5 V as the negative rail
            # charges. The Mega prints three fields:
            #   "Marx- pin: <adcV> V | Marx- mon: <monV> V | Marx-: <kV> kV"
            # The Mega's "Marx-:" kV is wrong-signed for this wiring (clamps to
            # 0), so we IGNORE it and recompute kV from monV (see constants
            # above). Allow a leading minus so values still parse near zero.
            m = re.search(r"Marx-\s*pin:\s*(-?[\d.]+)\s*V", line)
            if m:
                d["marx_neg_pin"] = float(m.group(1))
            m = re.search(r"Marx-\s*mon:\s*(-?[\d.]+)\s*V", line)
            if m:
                mon = float(m.group(1))
                d["marx_neg_mon"] = mon
                kv_neg = mon * MARX_NEG_KV_PER_MON_V
                kv_neg = max(0.0, min(MARX_NEG_FULL_SCALE_KV, kv_neg))
                d["marx_neg_kv"] = kv_neg
        except (ValueError, IndexError):
            self.raw_line.emit(f"parse error: {line}")
            return

        if d:
            self.parsed.emit(d)

    def stop(self):
        self._running = False
        self.wait(2000)


# ────────────────────────────────────────────────────────────────────
# Calibration helpers
# ────────────────────────────────────────────────────────────────────

# Calibration JSON lives next to the standalone Glassman GUI so the
# two stay interchangeable.
_CAL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "Arduino Sketch", "TestingwithNewPowerSupply",
)
CAL_FILE = os.path.join(_CAL_DIR, "vmon_cal.json")

CAL_VOLTAGES = list(range(0, 11))
CAL_KV = [v * 12.5 for v in CAL_VOLTAGES]


def _linreg(x, y):
    n = len(x)
    if n < 2:
        return 0.0, 0.0, 0.0
    sx = sum(x); sy = sum(y)
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


# ────────────────────────────────────────────────────────────────────
# Calibration dialog
# ────────────────────────────────────────────────────────────────────

class GlassmanCalibrationDialog(QDialog):
    """Manual + auto V_MON/I_MON divider calibration. Talks to the system
    through main_window so it can drive self.glassman_mega (the Mega)."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main = main_window
        self.setWindowTitle("Glassman V/I Monitor Calibration")
        self.setMinimumSize(900, 600)

        self.points = []
        self.current_index = 0
        self.cal_results = None
        self._auto_running = False

        root = QVBoxLayout(self)

        self.lbl_step = QLabel("")
        self.lbl_step.setStyleSheet("font-size:14px;font-weight:bold;")
        root.addWidget(self.lbl_step)

        live_grp = QGroupBox("Live Mega Readings")
        live_lay = QHBoxLayout(live_grp)
        live_lay.addWidget(QLabel("V_MON pin:"))
        self.lbl_live_vmon = QLabel("- V")
        self.lbl_live_vmon.setStyleSheet("font-weight:bold;color:#1565C0;")
        live_lay.addWidget(self.lbl_live_vmon)
        live_lay.addSpacing(30)
        live_lay.addWidget(QLabel("I_MON pin:"))
        self.lbl_live_imon = QLabel("- V")
        self.lbl_live_imon.setStyleSheet("font-weight:bold;color:#C62828;")
        live_lay.addWidget(self.lbl_live_imon)
        live_lay.addStretch()
        root.addWidget(live_grp)

        input_grp = QGroupBox("Multimeter Readings (actual terminal voltage)")
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

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "Cmd (V)", "kV", "V_MON pin (V)", "V-MON terminal (V)",
            "I_MON pin (V)", "I-MON terminal (V)", "Status",
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        root.addWidget(self.table)

        self.txt_results = QTextEdit()
        self.txt_results.setReadOnly(True)
        self.txt_results.setMaximumHeight(200)
        self.txt_results.setStyleSheet("font-family:Consolas,monospace;font-size:11px;")
        root.addWidget(self.txt_results)

        self.live_timer = QTimer()
        self.live_timer.timeout.connect(self._update_live)
        self.live_timer.start(200)
        self._update_step_label()

    def _update_step_label(self):
        if self.current_index < len(CAL_VOLTAGES):
            v = CAL_VOLTAGES[self.current_index]
            kv = CAL_KV[self.current_index]
            self.lbl_step.setText(
                f"Step {self.current_index + 1}/{len(CAL_VOLTAGES)}: "
                f"Command {v} V ({kv:.1f} kV)"
            )
            self.btn_set_voltage.setEnabled(True)
            self.btn_record.setEnabled(True)
        else:
            self.lbl_step.setText(
                f"All {len(CAL_VOLTAGES)} points recorded. Click Compute Calibration."
            )
            self.btn_set_voltage.setEnabled(False)
            self.btn_record.setEnabled(False)
            self.btn_compute.setEnabled(True)

    def _update_live(self):
        self.lbl_live_vmon.setText(f"{self.main.glassman_vmon_pin:.4f} V")
        self.lbl_live_imon.setText(f"{self.main.glassman_imon_pin:.4f} V")

    def _set_current_voltage(self):
        if self.current_index >= len(CAL_VOLTAGES):
            return
        v = CAL_VOLTAGES[self.current_index]
        # Sweep the Mega's GP8413 V-PROGRAM DAC directly (0-10 V on the
        # DAC = 0-125 kV at the Glassman). Was Portenta HVVOLT before.
        self.main.glassman_send_mega(f"VDAC {v:.3f}")

    def _record_point(self):
        if self.current_index >= len(CAL_VOLTAGES):
            return
        try:
            vmon_terminal = float(self.edit_vmon.text())
            imon_terminal = float(self.edit_imon.text())
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Terminal voltages must be numbers.")
            return

        cmd_v = CAL_VOLTAGES[self.current_index]
        point = {
            "cmd_v": cmd_v,
            "cmd_kv": CAL_KV[self.current_index],
            "vmon_pin_v": self.main.glassman_vmon_pin,
            "vmon_terminal_v": vmon_terminal,
            "imon_pin_v": self.main.glassman_imon_pin,
            "imon_terminal_v": imon_terminal,
        }
        self.points.append(point)

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

        if self.current_index < len(CAL_VOLTAGES):
            self._set_current_voltage()

    def _compute_calibration(self):
        if len(self.points) < 2:
            QMessageBox.warning(self, "Not Enough Data", "Need at least 2 points.")
            return
        vpin = [p["vmon_pin_v"] for p in self.points]
        vterm = [p["vmon_terminal_v"] for p in self.points]
        v_slope, v_intercept, v_r2 = _linreg(vpin, vterm)
        ipin = [p["imon_pin_v"] for p in self.points]
        iterm = [p["imon_terminal_v"] for p in self.points]
        i_slope, i_intercept, i_r2 = _linreg(ipin, iterm)

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
            "V-MON CALIBRATION",
            f"  slope:     {v_slope:.6f}",
            f"  intercept: {v_intercept:.6f}",
            f"  R^2:       {v_r2:.6f}",
            "",
            "I-MON CALIBRATION",
            f"  slope:     {i_slope:.6f}",
            f"  intercept: {i_intercept:.6f}",
            f"  R^2:       {i_r2:.6f}",
        ]
        self.txt_results.setPlainText("\n".join(lines))
        self.btn_save.setEnabled(True)

    def _save_json(self):
        if not self.cal_results:
            return
        try:
            os.makedirs(os.path.dirname(CAL_FILE), exist_ok=True)
            with open(CAL_FILE, "w") as f:
                json.dump(self.cal_results, f, indent=2)
            QMessageBox.information(self, "Saved", f"Calibration saved to:\n{CAL_FILE}")
        except Exception as e:
            QMessageBox.warning(self, "Save Error", str(e))

    def _start_auto_calibration(self):
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

        if not self.main.glassman_mega.is_connected:
            QMessageBox.warning(self, "Not Connected", "Glassman Mega is not connected.")
            return

        reply = QMessageBox.warning(
            self, "HV Will Be Applied",
            "This will command real voltages on AO0 with HV ENABLE ON.\n"
            "The Glassman will output up to 125 kV.\n\nMake sure the load is safe. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.points.clear()
        self.table.setRowCount(0)
        self.current_index = 0
        self.txt_results.clear()
        self.cal_results = None
        self.btn_compute.setEnabled(False)
        self.btn_save.setEnabled(False)

        self._auto_json_points = json_points
        self._auto_samples = []
        self._auto_settle_remaining = 0
        self._auto_running = True

        self.btn_set_voltage.setEnabled(False)
        self.btn_record.setEnabled(False)
        self.btn_auto_cal.setEnabled(False)
        self.btn_stop_auto.setEnabled(True)

        self.main.glassman_send_mega("ON")

        self._auto_timer = QTimer()
        self._auto_timer.timeout.connect(self._auto_tick)
        self._auto_timer.start(200)
        self._auto_begin_point()

    def _stop_auto_calibration(self):
        self._auto_running = False
        if hasattr(self, "_auto_timer"):
            self._auto_timer.stop()
        # Zero the Mega DAC (was Portenta HVVOLT 0 before the move).
        self.main.glassman_send_mega("ZERO")
        self.main.glassman_send_mega("OFF")
        self.lbl_auto_status.setText("Auto-cal stopped.")
        self.btn_auto_cal.setEnabled(True)
        self.btn_stop_auto.setEnabled(False)
        self.btn_set_voltage.setEnabled(True)
        self.btn_record.setEnabled(True)
        self._update_step_label()

    def _auto_begin_point(self):
        if self.current_index >= len(CAL_VOLTAGES):
            self._auto_timer.stop()
            # Zero the Mega DAC (was Portenta HVVOLT 0 before the move).
            self.main.glassman_send_mega("ZERO")
            self.main.glassman_send_mega("OFF")
            self.lbl_auto_status.setText("Auto-cal complete!")
            self.btn_auto_cal.setEnabled(True)
            self.btn_stop_auto.setEnabled(False)
            self.btn_compute.setEnabled(True)
            self._update_step_label()
            return

        v = CAL_VOLTAGES[self.current_index]
        kv = CAL_KV[self.current_index]
        self.lbl_step.setText(
            f"Step {self.current_index + 1}/{len(CAL_VOLTAGES)}: "
            f"Command {v} V ({kv:.1f} kV)"
        )
        # Sweep the Mega's GP8413 V-PROGRAM DAC directly (0-10 V on the
        # DAC = 0-125 kV at the Glassman). Was Portenta HVVOLT before.
        self.main.glassman_send_mega(f"VDAC {v:.3f}")
        self._auto_settle_remaining = 25
        self._auto_samples.clear()
        self.lbl_auto_status.setText(f"Settling... {v} V (5.0s)")

    def _auto_tick(self):
        if not self._auto_running:
            return
        if self._auto_settle_remaining > 0:
            self._auto_settle_remaining -= 1
            secs_left = self._auto_settle_remaining * 0.2
            self.lbl_auto_status.setText(
                f"Settling... {CAL_VOLTAGES[self.current_index]} V ({secs_left:.1f}s)"
            )
            return

        self._auto_samples.append(
            (self.main.glassman_vmon_pin, self.main.glassman_imon_pin)
        )
        n = len(self._auto_samples)
        self.lbl_auto_status.setText(
            f"Sampling {n}/20  V_MON={self.main.glassman_vmon_pin:.4f}  "
            f"I_MON={self.main.glassman_imon_pin:.4f}"
        )

        if n >= 20:
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
        if hasattr(self, "_auto_timer"):
            self._auto_timer.stop()
        # Zero the Mega DAC (was Portenta HVVOLT 0 before the move).
        self.main.glassman_send_mega("ZERO")
        event.accept()
