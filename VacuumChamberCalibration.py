"""
Vacuum chamber calibration: capture and export from Rigol scope 3 over USB.

Standalone GUI. Imports nothing from ScopeDelayGUI and opens only the one scope.

    python VacuumChamberCalibration.py

The scope list shows every USB instrument and preselects rigol3 by serial.
Picking a different scope is allowed but deliberate, and its files are then
named scope_<serial>_... rather than rigol3_..., so calibration data can never
be silently attributed to the wrong scope.

Each capture writes, into <save folder>/YYYY.MM.DD/:
    rigol3_<stamp>[_label].csv         Time (s), Voltage_CH<n> (V)
    rigol3_<stamp>[_label].json        IDN, timebase, per-channel setup,
                                       preamble and ADC clip counts
    rigol3_<stamp>[_label].png         preview (untick "Save PNG" to skip)

Only displayed channels are read, at full memory depth (RAW mode). Nothing
in the scope's setup is changed: the script writes :SINGle, :STOP and the
:WAVeform:* readout commands, nothing else.

Do not run this while the main GUI is capturing on rigol3 over Ethernet.
Both would be driving :WAVeform:SOURce on the same scope.
"""

import json
import os
import re
import sys
import threading
import time
from datetime import datetime

import numpy as np
import pandas as pd
import pyqtgraph as pg
import pyvisa
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
    QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
    QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)


RIGOL3_SERIAL = "DS7A233300256"     # from *IDN? in the GUI session logs

OUT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "VacuumChamberCalibration_data")

DATA_TIMEOUT_MS = 30000      # one 250k-point chunk is far under this on USB
QUERY_TIMEOUT_MS = 3000      # settings answer in ms, or never
CHUNK_POINTS = 250000        # Rigol caps a single :WAVeform:DATA? in BYTE mode

ADC_MIN, ADC_MAX = 0, 255

# Same channel colours as the main GUI's scope screen (white background).
CH_COLORS = {1: "#C9A000", 2: "#00A0B0", 3: "#D000D0", 4: "#1F3FBF"}

STATE_COLORS = {"off": "#757575", "idle": "#2E7D32", "armed": "#B26A00",
                "busy": "#1565C0", "error": "#C62828"}

SCOPE_QUERIES = {
    "idn": "*IDN?",
    "memory_depth": ":ACQuire:MDEPth?",
    "sample_rate_sa_s": ":ACQuire:SRATe?",
    "acquisition_type": ":ACQuire:TYPE?",
    "timebase_scale_s_div": ":TIMebase:MAIN:SCALe?",
    "timebase_offset_s": ":TIMebase:MAIN:OFFSet?",
    "trigger_source": ":TRIGger:EDGE:SOURce?",
    "trigger_slope": ":TRIGger:EDGE:SLOPe?",
    "trigger_level_v": ":TRIGger:EDGE:LEVel?",
}

# No :LABel? - R2's firmware never answers it, and these scopes get swapped.
CHANNEL_QUERIES = {
    "scale_v_div": ":CHANnel{ch}:SCALe?",
    "offset_v": ":CHANnel{ch}:OFFSet?",
    "probe_ratio": ":CHANnel{ch}:PROBe?",
    "coupling": ":CHANnel{ch}:COUPling?",
    "impedance": ":CHANnel{ch}:IMPedance?",
    "bandwidth_limit": ":CHANnel{ch}:BWLimit?",
    "invert": ":CHANnel{ch}:INVert?",
    "units": ":CHANnel{ch}:UNITs?",
}

_SI = {"": 1, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9}
_PREFIX = {-15: "f", -12: "p", -9: "n", -6: "µ", -3: "m",
           0: "", 3: "k", 6: "M", 9: "G", 12: "T"}


def parse_points(text):
    """':ACQuire:MDEPth?' -> int. Replies look like '1M', '125M', '1000000'."""
    m = re.fullmatch(r"([0-9.]+(?:[eE][+-]?\d+)?)\s*([kKMG]?)(?:pts)?",
                     (text or "").strip())
    return int(float(m.group(1)) * _SI[m.group(2)]) if m else None


def eng(x, unit=""):
    """1.234e-6, 's' -> '1.234 µs'."""
    if x is None or not np.isfinite(x):
        return "-"
    if abs(x) < 1e-15:      # float noise around zero, e.g. a cursor at t = 0
        return f"0 {unit}"
    exp = int(np.floor(np.log10(abs(x)) / 3) * 3)
    exp = max(-15, min(12, exp))
    return f"{x / 10 ** exp:.4g} {_PREFIX[exp]}{unit}"


def make_resource_manager():
    """pyvisa-py first, since that is what reaches rigol3 on the chamber PC;
    the system VISA (NI/Keysight) where pyvisa-py is not installed."""
    try:
        return pyvisa.ResourceManager("@py"), "pyvisa-py"
    except (ValueError, OSError):
        return pyvisa.ResourceManager(), "system VISA"


def find_usb_instruments(rm):
    """{serial: resource} for every USB instrument.

    Not filtered by vendor ID: pyvisa-py writes the IDs in decimal
    (USB0::6833::1300::...) where NI-VISA writes 0x1AB1, so a Rigol pattern
    match misses the scope on one backend or the other.
    """
    found = {}
    for res in rm.list_resources():
        if not res.upper().startswith("USB"):
            continue
        parts = res.split("::")
        if len(parts) >= 4:
            found[parts[3]] = res
    return found


def minmax_decimate(t, v, bins=4000):
    """Keep each bin's min and max, so a narrow pulse survives decimation."""
    n = len(v)
    if n <= 2 * bins:
        return t, v
    step = n // bins
    m = step * bins
    vv = v[:m].reshape(bins, step)
    out_v = np.empty(2 * bins)
    out_v[0::2] = vv.min(axis=1)
    out_v[1::2] = vv.max(axis=1)
    return np.repeat(t[:m:step], 2), out_v


class Rigol3:
    def __init__(self, rm, resource):
        self.rm = rm
        self.resource = resource
        self.inst = None
        self.idn = ""
        self.log = print

    def connect(self):
        self.inst = self.rm.open_resource(self.resource)
        self.inst.read_termination = "\n"
        self.inst.write_termination = "\n"
        self.inst.chunk_size = 1024 * 1024
        self.inst.timeout = 5000        # a silent scope fails fast at connect
        try:
            self.idn = self.query("*IDN?")
        except Exception:
            self.close()
            raise
        self.inst.timeout = DATA_TIMEOUT_MS
        return self.idn

    @property
    def serial(self):
        parts = [p.strip() for p in self.idn.split(",")]
        return parts[2] if len(parts) > 2 else ""

    def close(self):
        if self.inst is not None:
            try:
                self.inst.close()
            finally:
                self.inst = None

    def write(self, cmd):
        self.inst.write(cmd)

    def query(self, cmd):
        return self.inst.query(cmd).strip()

    def query_quick(self, cmd):
        """Settings read: short timeout, None instead of raising."""
        saved = self.inst.timeout
        self.inst.timeout = QUERY_TIMEOUT_MS
        try:
            return self.query(cmd)
        except pyvisa.errors.VisaIOError:
            return None
        finally:
            self.inst.timeout = saved

    def trigger_status(self):
        return self.query(":TRIGger:STATus?")

    def arm_and_wait(self, timeout_s, abort, on_status=None):
        """:SINGle, then poll until the acquisition is finished (STOP).

        Returns 'done', 'timeout' or 'aborted'.

        TD means triggered but the post-trigger record may still be filling,
        so keep polling for STOP rather than reading at TD. *OPC? makes sure
        the scope has processed :SINGle before the first poll, or the STOP
        left over from the previous capture reads as an instant trigger.
        """
        self.write(":SINGle")
        self.query_quick("*OPC?")
        t0 = time.monotonic()
        seen_td = None
        while True:
            if abort.is_set():
                return "aborted"
            elapsed = time.monotonic() - t0
            if elapsed >= timeout_s:
                return "timeout"
            status = self.trigger_status()
            if status == "STOP":
                return "done"
            if status == "TD" and seen_td is None:
                seen_td = time.monotonic()
            # Should never stick at TD in single mode; don't hang on it if it does.
            if seen_td is not None and time.monotonic() - seen_td > 5.0:
                return "done"
            if on_status:
                on_status(status, elapsed)
            time.sleep(0.05)

    def displayed_channels(self):
        return [ch for ch in range(1, 5)
                if self.query(f":CHANnel{ch}:DISPlay?") in ("1", "ON")]

    def settings(self, channels):
        out = {"scope": {k: self.query_quick(c) for k, c in SCOPE_QUERIES.items()},
               "channels": {}}
        for ch in channels:
            out["channels"][ch] = {k: self.query_quick(c.format(ch=ch))
                                   for k, c in CHANNEL_QUERIES.items()}
        return out

    def _preamble(self):
        p = self.query(":WAVeform:PREamble?").split(",")
        return {"format": int(p[0]), "type": int(p[1]), "points": int(p[2]),
                "count": int(p[3]), "xincrement": float(p[4]),
                "xorigin": float(p[5]), "xreference": float(p[6]),
                "yincrement": float(p[7]), "yorigin": float(p[8]),
                "yreference": float(p[9])}

    def read_channel(self, ch, total):
        """Full memory of one channel in RAW/BYTE, walked in chunks.

        Returns (time, volts, codes, preamble). The scope must be stopped.
        """
        self.write(f":WAVeform:SOURce CHANnel{ch}")
        self.write(":WAVeform:MODE RAW")
        self.write(":WAVeform:FORMat BYTE")
        self.write(":WAVeform:STARt 1")
        self.write(f":WAVeform:STOP {min(CHUNK_POINTS, total)}")
        pre = self._preamble()
        if pre["format"] != 0:
            raise RuntimeError(f"CH{ch}: preamble format {pre['format']}, expected BYTE (0)")

        chunks = []
        start = 1
        while start <= total:
            stop = min(start + CHUNK_POINTS - 1, total)
            self.write(f":WAVeform:STARt {start}")
            self.write(f":WAVeform:STOP {stop}")
            vals = self.inst.query_binary_values(
                ":WAVeform:DATA?", datatype="B", container=np.array,
                header_fmt="ieee", expect_termination=True)
            if vals.size == 0:
                break
            chunks.append(vals.astype(np.uint8))
            start += vals.size

        codes = np.concatenate(chunks) if chunks else np.array([], dtype=np.uint8)
        volts = (codes.astype(float) - pre["yreference"] - pre["yorigin"]) * pre["yincrement"]
        t = pre["xorigin"] + (np.arange(codes.size) - pre["xreference"]) * pre["xincrement"]
        return t, volts, codes, pre

    def capture(self, on_progress=None):
        """Stop, then read every displayed channel at full depth."""
        self.write(":STOP")
        channels = self.displayed_channels()
        if not channels:
            raise RuntimeError("No channels displayed on the scope")

        total = parse_points(self.query_quick(":ACQuire:MDEPth?"))
        if not total:
            # AUTO depth: ask the preamble how much is there.
            self.write(f":WAVeform:SOURce CHANnel{channels[0]}")
            self.write(":WAVeform:MODE RAW")
            total = self._preamble()["points"]

        info = self.settings(channels)
        info["capture"] = {"expected_points": total, "channels": {}}
        data = {}
        for ch in channels:
            if on_progress:
                on_progress(f"reading CH{ch} ({total:,} points)")
            t, v, codes, pre = self.read_channel(ch, total)
            low = int(np.count_nonzero(codes <= ADC_MIN))
            high = int(np.count_nonzero(codes >= ADC_MAX))
            info["capture"]["channels"][ch] = {
                "points": int(v.size), "preamble": pre,
                "clipped_low": low, "clipped_high": high,
                "v_min": float(v.min()) if v.size else None,
                "v_max": float(v.max()) if v.size else None,
            }
            data[ch] = (t, v)
            if v.size == 0:
                self.log(f"CH{ch}: no data returned")
                continue
            note = ""
            if v.size < total:
                note += f"  SHORT ({v.size} of {total})"
            if low or high:
                note += f"  CLIPPED ({low} low, {high} high)"
            self.log(f"CH{ch}: {v.size} pts, {v.min():+.4g} .. {v.max():+.4g} V{note}")
        return data, info


def export(data, info, label, out_root, prefix, save_png):
    stamp = datetime.now()
    out_dir = os.path.join(out_root, stamp.strftime("%Y.%m.%d"))
    os.makedirs(out_dir, exist_ok=True)
    name = prefix + "_" + stamp.strftime("%Y%m%d_%H%M%S")
    if label:
        name += "_" + re.sub(r"[^A-Za-z0-9._-]+", "_", label).strip("_")
    base = os.path.join(out_dir, name)

    # All channels share one timebase; pad a short channel with NaN.
    n = max(len(t) for t, _ in data.values())
    t_axis = next(t for t, _ in data.values() if len(t) == n)
    cols = {"Time (s)": t_axis}
    for ch, (_, v) in data.items():
        col = np.full(n, np.nan)
        col[:len(v)] = v
        cols[f"Voltage_CH{ch} (V)"] = col
    pd.DataFrame(cols).to_csv(base + ".csv", index=False)

    info["captured_at"] = stamp.isoformat(timespec="seconds")
    info["label"] = label or ""
    with open(base + ".json", "w") as f:
        json.dump(info, f, indent=2, default=str)

    if save_png:
        # Figure without pyplot: no GUI backend, safe off the Qt thread.
        from matplotlib.figure import Figure
        fig = Figure(figsize=(11, 5))
        ax = fig.add_subplot()
        for ch, (t, v) in data.items():
            if len(v):
                ax.plot(*minmax_decimate(t, v), lw=0.8, color=CH_COLORS[ch], label=f"CH{ch}")
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Voltage (V)")
        ax.set_title(name)
        ax.grid(True, alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(base + ".png", dpi=110)

    return base


class CaptureWorker(QThread):
    """Arm/wait/read/save off the GUI thread. One scope, one worker at a time."""

    status = pyqtSignal(str, str)               # state key, text
    log = pyqtSignal(str)
    captured = pyqtSignal(object, object, str)  # data, info, file base

    def __init__(self, scope, arm, shots, label, timeout_s, out_root, prefix, save_png):
        super().__init__()
        self.scope = scope
        self.arm = arm
        self.shots = shots
        self.label = label
        self.timeout_s = timeout_s
        self.out_root = out_root
        self.prefix = prefix
        self.save_png = save_png
        self.abort = threading.Event()
        self.failed = False

    def run(self):
        self.scope.log = self.log.emit
        try:
            for i in range(1, self.shots + 1):
                if self.abort.is_set():
                    break
                label, tag = self.label, ""
                if self.shots > 1:
                    label = f"{label}_{i:03d}" if label else f"{i:03d}"
                    tag = f"Shot {i}/{self.shots}: "

                if self.arm:
                    self.status.emit("armed", f"{tag}armed, waiting for trigger")
                    result = self.scope.arm_and_wait(
                        self.timeout_s, self.abort,
                        lambda s, e: self.status.emit(
                            "armed", f"{tag}armed, waiting for trigger  [{s}, {e:.0f} s]"))
                    if result == "aborted":
                        self.log.emit("Aborted; nothing saved. The scope is still armed.")
                        break
                    if result == "timeout":
                        self.log.emit(f"No trigger within {self.timeout_s:g} s; nothing saved.")
                        break
                    self.log.emit(f"{tag}triggered")

                t0 = time.monotonic()
                data, info = self.scope.capture(
                    lambda msg: self.status.emit("busy", tag + msg))
                self.log.emit(f"Read in {time.monotonic() - t0:.1f} s")
                self.status.emit("busy", f"{tag}saving")
                base = export(data, info, label, self.out_root, self.prefix, self.save_png)
                self.log.emit(f"Saved {base}.csv")
                self.captured.emit(data, info, base)
        except Exception as e:
            self.failed = True
            self.log.emit(f"ERROR: {type(e).__name__}: {e}")
            self.status.emit("error", f"Error: {e}")
        finally:
            self.scope.log = print


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Vacuum Chamber Calibration - Rigol 3")
        self.resize(1200, 820)

        self.rm, self.backend = make_resource_manager()
        self.scope = None
        self.prefix = "rigol3"
        self.worker = None
        self.last_data = {}
        self.out_root = OUT_ROOT

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # ---- scope ----
        box = QGroupBox("Scope (USB)")
        lay = QGridLayout(box)
        self.combo = QComboBox()
        self.combo.setMinimumWidth(380)
        self.btn_rescan = QPushButton("Rescan")
        self.btn_connect = QPushButton("Connect")
        self.btn_connect.setMinimumWidth(110)
        self.idn_label = QLabel("Not connected")
        self.idn_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(QLabel("Instrument"), 0, 0)
        lay.addWidget(self.combo, 0, 1)
        lay.addWidget(self.btn_rescan, 0, 2)
        lay.addWidget(self.btn_connect, 0, 3)
        lay.addWidget(self.idn_label, 1, 1, 1, 3)
        lay.setColumnStretch(1, 1)
        root.addWidget(box)

        # ---- capture ----
        box = QGroupBox("Capture")
        lay = QGridLayout(box)
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("added to the file name, e.g. 1e-5 torr run 3")
        self.shots = QSpinBox()
        self.shots.setRange(1, 10000)
        self.shots.setToolTip("Arm & Capture repeats this many times; files get _001, _002 ...")
        self.timeout = QDoubleSpinBox()
        self.timeout.setRange(1, 86400)
        self.timeout.setDecimals(0)
        self.timeout.setValue(600)
        self.timeout.setSuffix(" s")
        self.png_check = QCheckBox("Save PNG preview")
        self.png_check.setChecked(True)
        self.btn_arm = QPushButton("Arm && Capture")
        self.btn_arm.setToolTip("SINGLE, wait for a trigger, read all displayed channels, save")
        self.btn_arm.setStyleSheet("font-weight: bold; padding: 6px 16px;")
        self.btn_now = QPushButton("Capture Now")
        self.btn_now.setToolTip("STOP and save whatever is in the scope's memory now")
        self.btn_abort = QPushButton("Abort")
        self.btn_abort.setToolTip("Stop waiting for a trigger (a read in progress finishes first)")
        self.dir_edit = QLineEdit(self.out_root)
        self.dir_edit.setReadOnly(True)
        self.btn_browse = QPushButton("Browse...")
        self.btn_open = QPushButton("Open Folder")

        lay.addWidget(QLabel("Label"), 0, 0)
        lay.addWidget(self.label_edit, 0, 1, 1, 3)
        lay.addWidget(QLabel("Shots"), 0, 4)
        lay.addWidget(self.shots, 0, 5)
        lay.addWidget(QLabel("Trigger timeout"), 0, 6)
        lay.addWidget(self.timeout, 0, 7)
        buttons = QHBoxLayout()
        for b in (self.btn_arm, self.btn_now, self.btn_abort):
            buttons.addWidget(b)
        buttons.addSpacing(20)
        buttons.addWidget(self.png_check)
        buttons.addStretch(1)
        lay.addLayout(buttons, 1, 0, 1, 8)
        lay.addWidget(QLabel("Save to"), 2, 0)
        lay.addWidget(self.dir_edit, 2, 1, 1, 5)
        lay.addWidget(self.btn_browse, 2, 6)
        lay.addWidget(self.btn_open, 2, 7)
        lay.setColumnStretch(1, 1)
        root.addWidget(box)

        self.state_label = QLabel()
        self.state_label.setStyleSheet("font-size: 11pt; padding: 2px 4px;")
        root.addWidget(self.state_label)

        # ---- plot ----
        pg.setConfigOptions(antialias=False)
        self.plot = pg.PlotWidget(background="w")
        pi = self.plot.getPlotItem()
        pi.showGrid(x=True, y=True, alpha=0.25)
        pi.setLabel("bottom", "Time", units="s", color="#333")
        pi.setLabel("left", "Voltage", units="V", color="#333")
        for ax in ("left", "bottom"):
            pi.getAxis(ax).setPen("#888")
            pi.getAxis(ax).setTextPen("#333")
        pi.setDownsampling(auto=True, mode="peak")
        pi.setClipToView(True)
        self.legend = pi.addLegend(offset=(10, 10), labelTextColor="#222")
        self.curves = {ch: pi.plot([], [], pen=pg.mkPen(CH_COLORS[ch], width=1.5))
                       for ch in CH_COLORS}
        self.vline = pg.InfiniteLine(angle=90, movable=False,
                                     pen=pg.mkPen("#888", style=Qt.PenStyle.DashLine))
        self.vline.hide()
        pi.addItem(self.vline, ignoreBounds=True)
        self.plot.scene().sigMouseMoved.connect(self.on_mouse)
        self.readout = QLabel("Move the cursor over the plot to read values")
        self.readout.setStyleSheet("color: #333; padding: 2px 6px;")
        self.readout.setTextFormat(Qt.TextFormat.RichText)

        plot_box = QWidget()
        pl = QVBoxLayout(plot_box)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.addWidget(self.plot, 1)
        pl.addWidget(self.readout)

        # ---- per-channel table + log ----
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Channel", "Points", "Min", "Max", "Vpp", "Mean", "Clipped"])
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)

        bottom = QSplitter(Qt.Orientation.Horizontal)
        bottom.addWidget(self.table)
        bottom.addWidget(self.log_view)
        bottom.setSizes([700, 500])
        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(plot_box)
        split.addWidget(bottom)
        split.setSizes([560, 220])
        root.addWidget(split, 1)

        self.btn_rescan.clicked.connect(self.rescan)
        self.btn_connect.clicked.connect(self.toggle_connect)
        self.btn_arm.clicked.connect(lambda: self.start_capture(arm=True))
        self.btn_now.clicked.connect(lambda: self.start_capture(arm=False))
        self.btn_abort.clicked.connect(self.abort_capture)
        self.btn_browse.clicked.connect(self.browse)
        self.btn_open.clicked.connect(self.open_folder)

        self.log(f"VISA backend: {self.backend}")
        self.set_state("off", "Not connected")
        self.rescan()
        self.update_controls()

    # ---- helpers ----

    def log(self, msg):
        self.log_view.appendPlainText(f"{datetime.now():%H:%M:%S}  {msg}")

    def set_state(self, state, text):
        self.state_label.setText(
            f'<span style="color:{STATE_COLORS[state]}">●</span> {text}')

    def busy(self):
        return self.worker is not None

    def update_controls(self):
        connected, busy = self.scope is not None, self.busy()
        self.combo.setEnabled(not connected and not busy)
        self.btn_rescan.setEnabled(not connected and not busy)
        self.btn_connect.setEnabled(not busy and (connected or self.combo.currentData() is not None))
        self.btn_connect.setText("Disconnect" if connected else "Connect")
        self.btn_arm.setEnabled(connected and not busy)
        self.btn_now.setEnabled(connected and not busy)
        self.btn_abort.setEnabled(busy)
        self.btn_browse.setEnabled(not busy)

    # ---- connection ----

    def rescan(self):
        self.combo.clear()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            found = find_usb_instruments(self.rm)
        except Exception as e:
            self.log(f"USB scan failed: {e}")
            found = {}
        finally:
            QApplication.restoreOverrideCursor()

        for serial, res in found.items():
            text = f"{serial}   (rigol3)" if serial == RIGOL3_SERIAL else serial
            self.combo.addItem(text, res)
            self.combo.setItemData(self.combo.count() - 1, res, Qt.ItemDataRole.ToolTipRole)

        if RIGOL3_SERIAL in found:
            self.combo.setCurrentIndex(self.combo.findData(found[RIGOL3_SERIAL]))
            self.log(f"rigol3 found: {found[RIGOL3_SERIAL]}")
        elif found:
            self.log(f"rigol3 ({RIGOL3_SERIAL}) is not on USB. Found: {', '.join(found)}. "
                     f"Pick one on purpose if you mean a different scope.")
        else:
            self.combo.addItem("No USB instruments found", None)
            self.log("No USB instruments found. Check the cable and that the scope's "
                     "USB device port is enabled (Utility > IO).")
        self.update_controls()

    def toggle_connect(self):
        if self.scope is not None:
            self.scope.close()
            self.scope = None
            self.idn_label.setText("Not connected")
            self.log("Disconnected")
            self.set_state("off", "Not connected")
            self.update_controls()
            return

        res = self.combo.currentData()
        if not res:
            return
        scope = Rigol3(self.rm, res)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            idn = scope.connect()
        except Exception as e:
            self.log(f"Connect failed on {res}: {e}")
            self.set_state("error", "Connect failed")
            QMessageBox.warning(self, "Connect failed", f"{res}\n\n{e}")
            return
        finally:
            QApplication.restoreOverrideCursor()

        self.scope = scope
        self.log(f"Connected: {idn}")
        if scope.serial == RIGOL3_SERIAL:
            self.prefix = "rigol3"
            self.idn_label.setText(idn)
        else:
            self.prefix = f"scope_{scope.serial or 'unknown'}"
            self.idn_label.setText(f"{idn}   <b>- not rigol3</b>")
            self.log(f"WARNING: this is not rigol3 ({RIGOL3_SERIAL}); "
                     f"files will be named {self.prefix}_...")
        self.set_state("idle", "Ready")
        self.update_controls()

    # ---- capture ----

    def start_capture(self, arm):
        if self.scope is None or self.busy():
            return
        self.worker = CaptureWorker(
            self.scope, arm, self.shots.value() if arm else 1,
            self.label_edit.text().strip(), self.timeout.value(),
            self.out_root, self.prefix, self.png_check.isChecked())
        self.worker.status.connect(self.set_state)
        self.worker.log.connect(self.log)
        self.worker.captured.connect(self.on_captured)
        self.worker.finished.connect(self.on_worker_finished)
        self.log("Arming SINGLE" if arm else "Capturing what is in memory now")
        self.set_state("armed" if arm else "busy", "starting")
        self.worker.start()
        self.update_controls()

    def abort_capture(self):
        if self.worker is not None:
            self.worker.abort.set()
            self.set_state("busy", "aborting...")

    def on_worker_finished(self):
        failed = self.worker.failed
        self.worker.deleteLater()
        self.worker = None
        if not failed:
            self.set_state("idle", "Ready")
        self.update_controls()

    def on_captured(self, data, info, base):
        self.last_data = {ch: tv for ch, tv in data.items() if len(tv[1])}
        self.legend.clear()
        for ch, curve in self.curves.items():
            if ch in self.last_data:
                curve.setData(*self.last_data[ch])
                self.legend.addItem(curve, f"CH{ch}")
            else:
                curve.setData([], [])
        pi = self.plot.getPlotItem()
        pi.setTitle(os.path.basename(base), color="#222", size="10pt")
        pi.enableAutoRange()

        chans = info["capture"]["channels"]
        self.table.setRowCount(len(data))
        for row, (ch, (_, v)) in enumerate(data.items()):
            c = chans[ch]
            pm = QPixmap(12, 12)
            pm.fill(QColor(CH_COLORS[ch]))
            name = QTableWidgetItem(QIcon(pm), f"CH{ch}")
            clipped = c["clipped_low"] + c["clipped_high"]
            clip_text = (f"⚠ {clipped:,} ({c['clipped_low']:,} low, {c['clipped_high']:,} high)"
                         if clipped else "0")
            if len(v):
                vmin, vmax, mean = float(v.min()), float(v.max()), float(v.mean())
            else:
                vmin = vmax = mean = float("nan")
            cells = [name, QTableWidgetItem(f"{c['points']:,}"),
                     QTableWidgetItem(eng(vmin, "V")), QTableWidgetItem(eng(vmax, "V")),
                     QTableWidgetItem(eng(vmax - vmin, "V")), QTableWidgetItem(eng(mean, "V")),
                     QTableWidgetItem(clip_text)]
            if clipped:
                cells[-1].setToolTip("Samples on the ADC rail: the signal went off screen. "
                                     "Increase V/div for this channel.")
            for col, item in enumerate(cells):
                self.table.setItem(row, col, item)

    def on_mouse(self, pos):
        if not self.last_data:
            return
        vb = self.plot.getPlotItem().vb
        if not vb.sceneBoundingRect().contains(pos):
            return
        x = vb.mapSceneToView(pos).x()
        self.vline.setPos(x)
        self.vline.show()
        parts = [f"t = {eng(x, 's')}"]
        for ch, (t, v) in self.last_data.items():
            i = int(np.clip(np.searchsorted(t, x), 0, len(t) - 1))
            parts.append(f'<span style="color:{CH_COLORS[ch]}">■</span> CH{ch} {eng(v[i], "V")}')
        self.readout.setText("&nbsp;&nbsp;&nbsp;&nbsp;".join(parts))

    # ---- output folder ----

    def browse(self):
        d = QFileDialog.getExistingDirectory(self, "Save captures to", self.out_root)
        if d:
            self.out_root = d
            self.dir_edit.setText(d)

    def open_folder(self):
        os.makedirs(self.out_root, exist_ok=True)
        os.startfile(self.out_root)

    def closeEvent(self, event):
        if self.worker is not None:
            if QMessageBox.question(self, "Capture in progress",
                                    "A capture is running. Abort it and quit?") \
                    != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.worker.abort.set()
            self.worker.wait(60000)     # a read in progress finishes first
        if self.scope is not None:
            self.scope.close()
        event.accept()


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
