# gui/replay_window.py
"""Shot Replay: load a recorded shot by number and re-run the analysis on it.

A bench tool for improving the post-shot analysis. It connects to nothing.
Loading a shot does what the live GUI does when a shot lands:

  1. the three scope records go into the same ScopePlotWindow the live GUI
     uses, with each scope's screen rebuilt from the settings read at arm
     time (they are in the shot row);
  2. the analysis runs (the same analysis.process_shots.process_one the CLI
     runs) and its figure is shown.

What it adds for development:
  * "Reload code && rerun" (F5) re-imports analysis/pipeline.py, plots.py
    and process_shots.py, so an edit is tested without restarting. The
    waveforms stay in memory, so a rerun costs only the analysis itself.
  * Results are compared three ways: the stored production result
    (processed_shots/summary_cache.json), the previous replay run, and this
    run. The Analysis tab can overlay the previous run's traces.
  * Calibration factors can be overridden per run without editing code.
  * Batch: rerun a range of shots with the current code and see what moved.

Nothing is written to the session folders or to processed_shots. Replay
output (.mat and PNGs) goes to ScopeDelayGUI/replay_output/<shot key>/.
"""

import csv
import shutil
import subprocess
import threading
import traceback
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QSettings, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QAbstractItemView, QCheckBox, QFileDialog, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QComboBox, QPushButton, QScrollArea, QSpinBox, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from analysis import replay as R
from gui import replay_figures as F
from gui.analysis_window import AnalysisPlotWindow, open_with_system
from gui.scope_plot_window import ScopePlotWindow
from utils.downsample import downsample_four
from utils.logger import LogPanel

ANALYSIS_DIR = Path(__file__).resolve().parent.parent / "analysis"
CHANGED = QColor("#fff2a8")
WORSE = QColor("#ffc9c9")


# ===================================================================
# Background work
# ===================================================================
class Job(QThread):
    """Run fn() off the GUI thread; done(result) or failed(traceback)."""
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            self.done.emit(self.fn())
        except Exception:  # noqa: BLE001
            self.failed.emit(traceback.format_exc())


class BatchJob(QThread):
    """Rerun several shots in turn. One row(dict) per shot; stoppable
    between shots."""
    row = pyqtSignal(dict)
    finished_all = pyqtSignal(int, bool)          # (shots done, stopped)

    def __init__(self, refs, stored, cal, plots, parent=None):
        super().__init__(parent)
        self.refs, self.stored, self.cal, self.plots = refs, stored, cal, plots
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        n = 0
        for ref in self.refs:
            if self._stop.is_set():
                break
            try:
                res = R.run_shot(ref, cache=None, cal_overrides=self.cal, plots=self.plots)
                new, err = res.row, ""
            except Exception as e:  # noqa: BLE001
                new, err = {}, f"{type(e).__name__}: {e}"
            self.row.emit({"ref": ref, "stored": self.stored.get(ref.key, {}),
                           "new": new, "crash": err})
            n += 1
        self.finished_all.emit(n, self._stop.is_set())


class _ReplayState:
    """Stands in for the live GUI's SystemState: ScopePlotWindow reads each
    scope's arm-time settings from parent.system_state.get('rigol<N>')."""

    def __init__(self):
        self.sections = {}

    def get(self, key):
        return self.sections.get(key)


# ===================================================================
# Analysis plots (interactive version of plots.analysis_figure)
# ===================================================================
class AnalysisPlots(pg.GraphicsLayoutWidget):
    """The four panels of the production analysis figure, zoomable, with
    the previous run drawn underneath as dashed lines."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from analysis import plots as PL
        self.PL = PL
        self.setBackground("w")
        self.panels = {}
        spec = (("V", 0, 0, "LTGS D-dots and RVMs", "Voltage (kV)"),
                ("B", 0, 1, "LTGS B-dots", "Z*I (kV)"),
                ("C", 1, 0, "C225 / C315 monitors", "Voltage (kV)"),
                ("Q", 1, 1, "Q-switch monitors", "Q-switch (V)"))
        first = None
        for key, r, c, title, ylab in spec:
            p = self.addPlot(row=r, col=c, title=title)
            p.showGrid(x=True, y=True, alpha=0.25)
            p.setLabel("left", ylab)
            p.setLabel("bottom", "Time from pulse 1 (us)")
            p.addLegend(offset=(-10, 10))
            if first is None:
                first = p
            else:
                p.setXLink(first)
            self.panels[key] = p
        self.info = pg.TextItem(anchor=(0, 0), color="k", fill=pg.mkBrush(255, 255, 255, 220))
        self.info.setFont(pg.QtGui.QFont("Consolas", 9))

    PANEL_OF = {"D1": "V", "D2": "V", "R1": "V", "R2": "V", "B1": "B", "B2": "B",
                "C225": "C", "C315": "C", "Q1": "Q", "Q2": "Q"}

    def _draw(self, S, style, faint=False):
        """The traces ticked in the style panel, in their chosen colours."""
        for key in style.visible():
            xy = R.trace_xy(S, key)
            if xy is None:
                continue
            item = pg.PlotDataItem(xy[0], xy[1], pen=style.pen(key, faint=faint),
                                   name=None if faint else R.TRACE[key][1])
            item.setDownsampling(auto=True, method="peak")
            self.panels[self.PANEL_OF[key]].addItem(item)
            item.setClipToView(True)            # only once it is inside a ViewBox

    def _clear_panels(self):
        for p in self.panels.values():
            # Clip-to-view off first: a clipping curve being unparented asks
            # its view for autoRangeEnabled() and pyqtgraph hands it this
            # widget instead of the ViewBox, which raises.
            for item in p.listDataItems():
                item.setClipToView(False)
            p.clear()
            if p.legend is not None:
                p.legend.clear()

    def show_result(self, S, style, previous=None, keep_view=False, note=""):
        views = {k: p.getViewBox().viewRange() for k, p in self.panels.items()}
        self._clear_panels()
        if S.get("status") != "ok":
            self.panels["V"].setTitle(f"No analysis traces: status {S.get('status')} "
                                      f"({S.get('error', '')})")
            return
        self.panels["V"].setTitle("LTGS D-dots and RVMs"
                                  + (f"  <span style='color:#c00000'>[{note}]</span>"
                                     if note else ""))
        if previous is not None and previous.get("status") == "ok":
            self._draw(previous, style, faint=True)
        self._draw(S, style)
        t_end = (S["tEnd"] - S["tPulse"]) * 1e6
        for p in self.panels.values():
            for x in (0.0, t_end):
                p.addItem(pg.InfiniteLine(x, angle=90, pen=pg.mkPen("#888", width=1,
                                                                     style=Qt.PenStyle.DotLine)))
        self.panels["Q"].addItem(self.info)
        self.info.setText(self.PL.spacing_text(S) + (f"\n{note}" if note else ""))
        if keep_view:
            for k, p in self.panels.items():
                (x0, x1), (y0, y1) = views[k]
                p.setXRange(x0, x1, padding=0)
                p.setYRange(y0, y1, padding=0)
        else:
            # Limits from the style panel: X on all (linked), Y (kV) on the
            # voltage panels, Q on the Q-switch panel. The B-dot Z*I panel
            # autoscales: its amplitude is not on the D-dot scale.
            self.panels["V"].setXRange(*style.xlim(), padding=0)
            for k in ("V", "C"):
                self.panels[k].setYRange(*style.ylim(), padding=0)
            self.panels["B"].enableAutoRange(axis="y")
            self.panels["Q"].setYRange(*style.qlim(), padding=0)
        vr = self.panels["Q"].getViewBox().viewRange()
        self.info.setPos(vr[0][0], vr[1][1])

    def clear_all(self):
        self._clear_panels()


# ===================================================================
# Main window
# ===================================================================
class ShotReplayWindow(QMainWindow):

    SETTINGS = ("MultiPulse", "ShotReplay")     # tests point this elsewhere

    def __init__(self, logs_root=None):
        super().__init__()
        self.setWindowTitle("Shot Replay (offline, no instruments)")
        self.resize(1750, 1000)
        self.qs = QSettings(*self.SETTINGS)

        self.system_state = _ReplayState()   # read by ScopePlotWindow
        self.cache = R.WaveformCache()
        self.index = []
        self.stored = {}
        self.ref = None                      # the loaded shot
        self.current = None                  # RunResult of the latest run
        self.previous = None                 # RunResult of the run before it
        self._job = None
        self._batch = None
        self._batch_rows = []
        self._pending_analyze = False
        self.checked = set()                 # keys of the ticked shots
        self.replay_rows = {}                # key -> summary row of the latest replay
        self._mat_cache = {}                 # (path, mtime) -> trimmed result
        self.fig_windows = []

        self._build_ui()
        root = logs_root or self.qs.value("logs_root", "") or R.guess_logs_root() or ""
        self.ed_root.setText(str(root))
        if root:
            self.rescan()

    # ------------------------------------------------------------- UI
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)

        # --- top bar: logs folder, shot number
        top = QHBoxLayout()
        top.addWidget(QLabel("Logs folder:"))
        self.ed_root = QLineEdit()
        self.ed_root.setMinimumWidth(380)
        self.ed_root.returnPressed.connect(self.rescan)
        top.addWidget(self.ed_root, 1)
        b = QPushButton("Browse...")
        b.clicked.connect(self.browse_root)
        top.addWidget(b)
        b = QPushButton("Rescan")
        b.clicked.connect(self.rescan)
        top.addWidget(b)
        top.addSpacing(24)
        top.addWidget(QLabel("Shot #"))
        self.spin_shot = QSpinBox()
        self.spin_shot.setRange(0, 999999)
        self.spin_shot.setMinimumWidth(90)
        self.spin_shot.lineEdit().returnPressed.connect(self.load_number)
        top.addWidget(self.spin_shot)
        self.btn_load = QPushButton("Load")
        self.btn_load.clicked.connect(self.load_number)
        top.addWidget(self.btn_load)
        self.btn_prev = QPushButton("< Prev")
        self.btn_prev.clicked.connect(lambda: self.step(-1))
        top.addWidget(self.btn_prev)
        self.btn_next = QPushButton("Next >")
        self.btn_next.clicked.connect(lambda: self.step(+1))
        top.addWidget(self.btn_next)
        outer.addLayout(top)

        self.lbl_status = QLabel("No shot loaded.")
        self.lbl_status.setStyleSheet("font-size: 13pt; padding: 2px;")
        outer.addWidget(self.lbl_status)

        split = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(split, 1)

        # --- left: shot list
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.ed_filter = QLineEdit()
        self.ed_filter.setPlaceholderText("Filter shots (number, date, status)")
        self.ed_filter.textChanged.connect(self._fill_list)
        ll.addWidget(self.ed_filter)
        self.list_shots = QListWidget()
        self.list_shots.itemActivated.connect(
            lambda it: self.load_ref(it.data(Qt.ItemDataRole.UserRole)))
        self.list_shots.itemDoubleClicked.connect(
            lambda it: self.load_ref(it.data(Qt.ItemDataRole.UserRole)))
        self.list_shots.itemChanged.connect(self._shot_checked)
        ll.addWidget(self.list_shots, 1)
        row = QHBoxLayout()
        for text, fn in (("Check all", lambda: self._check(lambda r: True)),
                         ("Uncheck all", lambda: self._check(lambda r: False))):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        ll.addLayout(row)
        ll.addWidget(QLabel("Tick shots for the multi-shot figures;\n"
                            "double-click one to load it."))
        left.setMinimumWidth(230)
        split.addWidget(left)
        split.setCollapsible(0, False)

        # --- centre: tabs
        self.tabs = QTabWidget()
        self.scope_view = ScopePlotWindow(parent=self)
        for btn in (self.scope_view.btn_r1_single, self.scope_view.btn_r1_capture,
                    self.scope_view.btn_r2_single, self.scope_view.btn_r2_capture,
                    self.scope_view.btn_r3_single, self.scope_view.btn_r3_capture):
            btn.hide()                       # nothing to arm or read offline
        self.tabs.addTab(self.scope_view, "Scopes (as the live GUI)")
        self.plots = AnalysisPlots()
        self.tabs.addTab(self.plots, "Analysis (interactive)")
        self.figure = AnalysisPlotWindow()
        self.figure.setWindowFlags(Qt.WindowType.Widget)
        fig_wrap = QWidget()
        fl = QVBoxLayout(fig_wrap)
        fl.setContentsMargins(0, 0, 0, 0)
        frow = QHBoxLayout()
        self.btn_fig_analysis = QPushButton("Analysis figure")
        self.btn_fig_analysis.clicked.connect(lambda: self._show_png("analysis_png"))
        self.btn_fig_raw = QPushButton("Raw 12-channel figure")
        self.btn_fig_raw.clicked.connect(lambda: self._show_png("raw_png"))
        frow.addWidget(self.btn_fig_analysis)
        frow.addWidget(self.btn_fig_raw)
        frow.addStretch()
        fl.addLayout(frow)
        fl.addWidget(self.figure, 1)
        self.tabs.addTab(fig_wrap, "Figures (production PNGs)")
        self.tabs.addTab(self._build_batch_tab(), "Batch rerun")
        split.addWidget(self.tabs)

        # --- right: run controls, results, shot info, calibration, log
        right = QSplitter(Qt.Orientation.Vertical)
        right.addWidget(self._build_run_box())
        right.addWidget(self._build_results_box())
        rtabs = QTabWidget()
        rtabs.addTab(self._build_info_tab(), "Shot row")
        rtabs.addTab(self._build_cal_tab(), "Calibration")
        self.log_panel = LogPanel()
        rtabs.addTab(self.log_panel, "Log")
        self.rtabs = rtabs
        right.addWidget(rtabs)
        right.setSizes([150, 420, 380])
        self.right_tabs = QTabWidget()
        self.right_tabs.addTab(right, "Replay")
        self.right_tabs.addTab(self._build_plot_controls(), "Plot controls")
        split.addWidget(self.right_tabs)
        split.setSizes([240, 1000, 560])

        QShortcut(QKeySequence("F5"), self, activated=self.rerun)
        QShortcut(QKeySequence("Ctrl+Right"), self, activated=lambda: self.step(+1))
        QShortcut(QKeySequence("Ctrl+Left"), self, activated=lambda: self.step(-1))

    def _build_run_box(self):
        box = QGroupBox("Analysis")
        v = QVBoxLayout(box)
        row = QHBoxLayout()
        self.btn_rerun = QPushButton("Reload code && rerun  (F5)")
        self.btn_rerun.setStyleSheet("font-weight: bold; padding: 6px;")
        self.btn_rerun.clicked.connect(self.rerun)
        row.addWidget(self.btn_rerun, 1)
        b = QPushButton("Edit pipeline.py")
        b.clicked.connect(lambda: self.open_in_editor(ANALYSIS_DIR / "pipeline.py"))
        row.addWidget(b)
        b = QPushButton("Output folder")
        b.clicked.connect(self.open_sandbox)
        row.addWidget(b)
        v.addLayout(row)
        row = QHBoxLayout()
        self.chk_auto = QCheckBox("Analyze on load")
        self.chk_auto.setChecked(self.qs.value("auto", "true") == "true")
        self.chk_png = QCheckBox("Make PNG figures")
        self.chk_png.setChecked(self.qs.value("png", "true") == "true")
        self.chk_overlay = QCheckBox("Overlay previous run")
        self.chk_overlay.setChecked(self.qs.value("overlay", "true") == "true")
        self.chk_overlay.toggled.connect(lambda _: self._show_plots(keep_view=True))
        for w in (self.chk_auto, self.chk_png, self.chk_overlay):
            row.addWidget(w)
        row.addStretch()
        v.addLayout(row)
        return box

    def _build_results_box(self):
        box = QGroupBox("Results: stored (production) vs previous replay vs this replay")
        v = QVBoxLayout(box)
        self.tbl_res = QTableWidget(0, 5)
        self.tbl_res.setHorizontalHeaderLabels(
            ["Field", "Stored", "Previous", "Current", "Current - stored"])
        self.tbl_res.verticalHeader().setVisible(False)
        self.tbl_res.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_res.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl_res.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.tbl_res)
        return box

    def _build_info_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        self.ed_info_filter = QLineEdit()
        self.ed_info_filter.setPlaceholderText("Filter columns, e.g. rigol2_ch or wj")
        self.ed_info_filter.textChanged.connect(self._fill_info)
        v.addWidget(self.ed_info_filter)
        self.tbl_info = QTableWidget(0, 2)
        self.tbl_info.setHorizontalHeaderLabels(["Column", "Value"])
        self.tbl_info.verticalHeader().setVisible(False)
        self.tbl_info.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_info.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.tbl_info)
        return w

    def _build_cal_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Override a calibration factor for replay runs only. "
                           "Blank = the value in pipeline.py. Nothing is saved to code."))
        self.tbl_cal = QTableWidget(0, 3)
        self.tbl_cal.setHorizontalHeaderLabels(["Key", "In code", "Override"])
        self.tbl_cal.verticalHeader().setVisible(False)
        self.tbl_cal.horizontalHeader().setStretchLastSection(True)
        self.tbl_cal.itemChanged.connect(self._cal_edited)
        v.addWidget(self.tbl_cal)
        row = QHBoxLayout()
        self.btn_cal_apply = QPushButton("Apply overrides && rerun")
        self.btn_cal_apply.setStyleSheet("font-weight: bold; padding: 6px;")
        self.btn_cal_apply.clicked.connect(self.apply_cal)
        row.addWidget(self.btn_cal_apply, 1)
        b = QPushButton("Clear overrides")
        b.clicked.connect(self._clear_cal)
        row.addWidget(b)
        v.addLayout(row)
        self.lbl_cal = QLabel("")
        self.lbl_cal.setWordWrap(True)
        v.addWidget(self.lbl_cal)
        self._fill_cal()
        return w

    def _build_batch_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        row = QHBoxLayout()
        row.addWidget(QLabel("Shots:"))
        self.ed_batch = QLineEdit(self.qs.value("batch", ""))
        self.ed_batch.setPlaceholderText("e.g. 40-46, 50   (blank = every numbered shot)")
        row.addWidget(self.ed_batch, 1)
        self.chk_batch_png = QCheckBox("PNGs")
        row.addWidget(self.chk_batch_png)
        self.btn_batch = QPushButton("Reload code && run batch")
        self.btn_batch.clicked.connect(self.start_batch)
        row.addWidget(self.btn_batch)
        self.btn_batch_stop = QPushButton("Stop")
        self.btn_batch_stop.setEnabled(False)
        self.btn_batch_stop.clicked.connect(self.stop_batch)
        row.addWidget(self.btn_batch_stop)
        b = QPushButton("Export CSV...")
        b.clicked.connect(self.export_batch)
        row.addWidget(b)
        v.addLayout(row)
        v.addWidget(QLabel("Each cell is the new value; yellow = changed from the stored "
                           "result, red = status got worse. Hover for the stored value. "
                           "Double-click a row to load that shot."))
        self.batch_cols = ["status", "spacing_qsw_ns", "spacing_rvm_ns", "LTGS1_Ddot_kV",
                           "LTGS2_Ddot_kV", "RVM1_kV", "RVM2_kV", "C225_Ddot_kV",
                           "rvm_gain_1", "rvm_gain_2", "error"]
        self.tbl_batch = QTableWidget(0, len(self.batch_cols) + 1)
        self.tbl_batch.setHorizontalHeaderLabels(["Shot"] + self.batch_cols)
        self.tbl_batch.verticalHeader().setVisible(False)
        self.tbl_batch.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_batch.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_batch.horizontalHeader().setStretchLastSection(True)
        self.tbl_batch.cellDoubleClicked.connect(self._batch_row_clicked)
        v.addWidget(self.tbl_batch, 1)
        self.lbl_batch = QLabel("")
        v.addWidget(self.lbl_batch)
        return w

    # ------------------------------------------------------------ log
    def log(self, msg):
        self.log_panel.log(msg)

    def status(self, msg, color="black"):
        self.lbl_status.setText(msg)
        self.lbl_status.setStyleSheet(f"font-size: 13pt; padding: 2px; color: {color};")

    # ------------------------------------------------------- shot index
    def browse_root(self):
        d = QFileDialog.getExistingDirectory(self, "Logs folder", self.ed_root.text())
        if d:
            self.ed_root.setText(d)
            self.rescan()

    def rescan(self):
        root = Path(self.ed_root.text().strip())
        if not root.is_dir():
            self.status(f"Logs folder not found: {root}", "red")
            return
        self.qs.setValue("logs_root", str(root))
        self.index = R.index_shots(root)
        self.stored = R.stored_results(root)
        self._fill_list()
        self._fill_groups()
        nums = [r.number for r in self.index if r.number is not None]
        self.log(f"[REPLAY] {len(self.index)} shot(s) under {root}"
                 + (f", numbers {min(nums)}-{max(nums)}" if nums else "")
                 + f"; {len(self.stored)} with a stored production result")
        if nums and not self.ref:
            self.spin_shot.setValue(max(nums))
        if not self.ref:
            self.status(f"{len(self.index)} shots found. Type a shot number and press Load.")

    def _fill_list(self):
        flt = self.ed_filter.text().strip().lower()
        self.list_shots.blockSignals(True)
        self.list_shots.clear()
        for ref in self.index:
            st = self.stored.get(ref.key, {}).get("status", "not processed")
            text = f"{ref.label()}   [{st}]"
            if flt and flt not in text.lower():
                continue
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, ref)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if ref.key in self.checked
                             else Qt.CheckState.Unchecked)
            if not all(Path(f).exists() for f in ref.files):
                it.setForeground(QColor("#999999"))
                it.setToolTip("one or more waveform files are missing")
            self.list_shots.addItem(it)
            if self.ref is not None and ref.key == self.ref.key:
                self.list_shots.setCurrentItem(it)
        self.list_shots.blockSignals(False)

    # ------------------------------------------------------------ loading
    def busy(self):
        return (self._job is not None and self._job.isRunning()) or (
            self._batch is not None and self._batch.isRunning())

    def _set_busy(self, on):
        for w in (self.btn_load, self.btn_prev, self.btn_next, self.btn_rerun,
                  self.btn_cal_apply, self.btn_batch, self.list_shots):
            w.setEnabled(not on)
        self.btn_batch_stop.setEnabled(self._batch is not None and self._batch.isRunning())

    def load_number(self):
        n = self.spin_shot.value()
        ref = R.find_shot(self.index, n)
        if ref is None:
            self.status(f"Shot {n} is not under {self.ed_root.text()}. "
                        "Check the logs folder, or Rescan.", "red")
            return
        self.load_ref(ref)

    def step(self, d):
        if not self.index:
            return
        keys = [r.key for r in self.index]
        i = keys.index(self.ref.key) + d if self.ref and self.ref.key in keys else 0
        if 0 <= i < len(self.index):
            self.load_ref(self.index[i])

    def load_ref(self, ref):
        if ref is None or self.busy():
            return
        self.ref = ref
        self.current = self.previous = None
        if ref.number is not None:
            self.spin_shot.setValue(ref.number)
        self.cache.clear()                   # one shot's records in memory at a time
        self.scope_view.clear_plots()
        self.plots.clear_all()
        self._fill_list()
        self._fill_info()
        self._fill_results()
        self._cal_edited()
        self.status(f"Loading {ref.name} from {ref.sdir.name} ...")
        self.log(f"[REPLAY] loading {ref.name}: {ref.sdir}")
        self._pending_analyze = self.chk_auto.isChecked()
        self._start(lambda: R.load_scopes(ref, self.cache), self._on_loaded)

    def _on_loaded(self, out):
        scopes, problems = out
        for p in problems:
            self.log(f"[REPLAY] {p}")
        for k in (1, 2, 3):
            self.system_state.sections[f"rigol{k}"] = {
                "settings": R.scope_settings(self.ref.meta, k)}
            M = scopes.get(k)
            if M is None:
                continue
            data = tuple((M[:, 0], M[:, c]) for c in (1, 2, 3, 4))
            d = downsample_four(data)
            self.scope_view.set_full_data(k, data)
            getattr(self.scope_view, f"update_r{k}")(
                d[0][0], d[0][1], d[1][0], d[1][1], d[2][0], d[2][1], d[3][0], d[3][1])
            self.log(f"[REPLAY] rigol{k}: {len(M)} points, "
                     f"{(M[-1, 0] - M[0, 0]) * 1e6:.1f} us"
                     + ("" if self.system_state.sections[f"rigol{k}"]["settings"]
                        else " (no arm-time settings in the shot row)"))
        self.status(f"{self.ref.name} loaded: {len(scopes)} of 3 scopes"
                    + (f", {len(problems)} problem(s), see Log" if problems else ""),
                    "black" if not problems else "#b36b00")
        if self._pending_analyze:
            self._pending_analyze = False
            self.rerun()

    # ------------------------------------------------------------ running
    def cal_overrides(self):
        out = {}
        for r in range(self.tbl_cal.rowCount()):
            key = self.tbl_cal.item(r, 0).text()
            it = self.tbl_cal.item(r, 2)
            txt = it.text().strip() if it else ""
            if txt:
                try:
                    out[key] = float(txt)
                except ValueError:
                    self.log(f"[REPLAY] calibration override for {key} is not a number: {txt!r}")
        return out

    def _reload(self):
        try:
            ver = R.reload_analysis()
        except Exception:  # noqa: BLE001
            tb = traceback.format_exc()
            self.log("[REPLAY] code reload FAILED, nothing was run:\n" + tb)
            self.status("Code reload failed (syntax error?). See Log.", "red")
            self.rtabs.setCurrentWidget(self.log_panel)
            return None
        self._fill_cal()
        return ver

    def rerun(self):
        if self.ref is None or self.busy():
            return
        ver = self._reload()
        if ver is None:
            return
        cal = self.cal_overrides()
        plots = self.chk_png.isChecked()
        ref = self.ref
        self.status(f"Analyzing {ref.name} with pipeline {ver}"
                    + (f", {len(cal)} calibration override(s)" if cal else "") + " ...")
        self._start(lambda: R.run_shot(ref, cache=self.cache, cal_overrides=cal, plots=plots),
                    self._on_ran)

    def _on_ran(self, res):
        if self.ref is None or res.S.get("key") != self.ref.key:
            return
        self.previous, self.current = self.current, res
        self.replay_rows[self.ref.key] = res.row
        S, row = res.S, res.row
        color = {"ok": "green", "no_fire": "#b36b00"}.get(S["status"], "red")
        used = self._cal_used_text(res)
        self.status(f"{S['name']}: {S['status']}   spacing cmd {row['spacing_cmd_ns'] or '--'} / "
                    f"Qsw {row['spacing_qsw_ns'] or '--'} / RVM {row['spacing_rvm_ns'] or '--'} ns"
                    f"   ({res.seconds:.1f} s, {row['pipeline_version']})"
                    + (f"   OVERRIDES: {used}" if used else "")
                    + (f"   {S['error']}" if S.get("error") else ""), color)
        self.log(f"[REPLAY] {S['name']}: {S['status']} in {res.seconds:.1f} s -> {res.out_dir}"
                 + (f"\n[REPLAY] calibration used: {used}" if used else
                    "\n[REPLAY] calibration used: code values (no overrides)"))
        self._cal_edited()
        self._fill_results()
        self._show_plots()
        png = row.get("analysis_png") or row.get("raw_png")
        if png:
            self._show_png("analysis_png" if row.get("analysis_png") else "raw_png")

    def _start(self, fn, on_done):
        job = Job(fn, self)
        job.done.connect(on_done)
        job.failed.connect(self._on_failed)
        job.finished.connect(lambda: self._set_busy(False))
        self._job = job
        self._set_busy(True)
        job.start()

    def _on_failed(self, tb):
        self._pending_analyze = False
        self.log("[REPLAY] ERROR\n" + tb)
        last = tb.strip().splitlines()[-1] if tb.strip() else "error"
        self.status(f"Failed: {last}  (full traceback in Log)", "red")
        self.rtabs.setCurrentWidget(self.log_panel)

    # ------------------------------------------------------------ display
    def _show_plots(self, keep_view=False):
        if self.current is None:
            return
        prev = self.previous.S if (self.previous and self.chk_overlay.isChecked()) else None
        used = self._cal_used_text(self.current)
        self.plots.show_result(self.current.S, self.style, prev,
                               keep_view=keep_view or prev is not None,
                               note=f"OVERRIDES: {used}" if used else "")

    def _show_png(self, which):
        if self.current is None:
            return
        png = self.current.row.get(which, "")
        if not png or not Path(png).exists():
            self.figure.caption.setText(f"No {which.replace('_png', '')} figure for this run"
                                        + ("" if self.chk_png.isChecked()
                                           else " ('Make PNG figures' is off)."))
            return
        self.figure.show_image(png, f"{self.current.S['name']}: {Path(png).name} (replay)")

    def _fill_results(self):
        stored = self.stored.get(self.ref.key, {}) if self.ref else {}
        prev = self.previous.row if self.previous else {}
        cur = self.current.row if self.current else {}
        rows = R.compare_rows(stored, cur)
        self.tbl_res.setRowCount(len(rows))
        for i, (c, s, n, d) in enumerate(rows):
            p = prev.get(c, "")
            vals = [c, s, p, n, d]
            for j, val in enumerate(vals):
                it = QTableWidgetItem(str(val))
                it.setToolTip(str(val))
                if j == 3 and cur and prev and str(n) != str(p):
                    it.setBackground(CHANGED)            # moved since the previous run
                self.tbl_res.setItem(i, j, it)
        self.tbl_res.resizeColumnToContents(0)

    def _fill_info(self):
        meta = self.ref.meta if self.ref else {}
        flt = self.ed_info_filter.text().strip().lower()
        items = [(k, v) for k, v in meta.items()
                 if (not flt or flt in k.lower() or flt in str(v).lower())]
        extra = []
        if self.ref and not flt:
            extra = [("(session folder)", str(self.ref.sdir))] + [
                (f"(file {k})", str(f)) for k, f in enumerate(self.ref.files, start=1)]
        items = extra + items
        self.tbl_info.setRowCount(len(items))
        for i, (k, v) in enumerate(items):
            self.tbl_info.setItem(i, 0, QTableWidgetItem(k))
            it = QTableWidgetItem(str(v))
            it.setToolTip(str(v))
            self.tbl_info.setItem(i, 1, it)
        self.tbl_info.resizeColumnToContents(0)

    def _fill_cal(self):
        """Code values from the (possibly just reloaded) pipeline; the
        overrides typed in are kept across reloads."""
        keep = {}
        for r in range(self.tbl_cal.rowCount()):
            it = self.tbl_cal.item(r, 2)
            if it and it.text().strip():
                keep[self.tbl_cal.item(r, 0).text()] = it.text().strip()
        cal = R.P.CAL
        self.tbl_cal.blockSignals(True)
        self.tbl_cal.setRowCount(len(cal))
        for i, (k, v) in enumerate(cal.items()):
            a = QTableWidgetItem(k)
            a.setFlags(a.flags() & ~Qt.ItemFlag.ItemIsEditable)
            b = QTableWidgetItem(f"{v:.6g}")
            b.setFlags(b.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl_cal.setItem(i, 0, a)
            self.tbl_cal.setItem(i, 1, b)
            self.tbl_cal.setItem(i, 2, QTableWidgetItem(keep.get(k, "")))
        self.tbl_cal.blockSignals(False)
        self.tbl_cal.resizeColumnToContents(0)
        self._cal_edited()

    def _clear_cal(self):
        self.tbl_cal.blockSignals(True)
        for r in range(self.tbl_cal.rowCount()):
            self.tbl_cal.setItem(r, 2, QTableWidgetItem(""))
        self.tbl_cal.blockSignals(False)
        self._cal_edited()

    def apply_cal(self):
        """Commit a cell still being typed in, then rerun with the overrides."""
        self.tbl_cal.setFocus()              # focus-out closes the editor and commits it
        if self.ref is None:
            self.lbl_cal.setText("Load a shot first; the overrides apply to the next run.")
            self.lbl_cal.setStyleSheet("color: #b36b00;")
            return
        self.rerun()

    def _cal_used_text(self, res):
        """'bScale = -4.5 (code -5.5), ...' for the values a run used that
        differ from the code; '' when it ran on the code values."""
        if res is None or not res.cal_used:
            return ""
        code = R.P.CAL
        return ", ".join(f"{k} = {v:.6g} (code {code[k]:.6g})"
                         for k, v in res.cal_used.items()
                         if k in code and v != code[k])

    def _cal_edited(self, *_):
        """Highlight overridden rows and say whether the latest run used them."""
        if not hasattr(self, "lbl_cal"):
            return
        code = R.P.CAL
        pending = {k: v for k, v in self.cal_overrides().items() if v != code.get(k)}
        self.tbl_cal.blockSignals(True)
        for r in range(self.tbl_cal.rowCount()):
            key = self.tbl_cal.item(r, 0).text()
            bg = CHANGED if key in pending else QColor(0, 0, 0, 0)
            for c in range(3):
                it = self.tbl_cal.item(r, c)
                if it:
                    it.setBackground(bg)
        self.tbl_cal.blockSignals(False)
        used = self.current.cal_used if self.current else {}
        ran = {k: v for k, v in used.items() if k in code and v != code[k]}
        if not pending and not ran:
            self.lbl_cal.setText("No overrides. Runs use the code values.")
            self.lbl_cal.setStyleSheet("color: black;")
        elif self.current is not None and pending == ran:
            self.lbl_cal.setText(f"APPLIED in the latest run: {self._cal_used_text(self.current)}")
            self.lbl_cal.setStyleSheet("color: green; font-weight: bold;")
        else:
            txt = ", ".join(f"{k} = {v:.6g}" for k, v in pending.items()) or "code values"
            self.lbl_cal.setText(f"NOT APPLIED YET: {txt}. Press 'Apply overrides & rerun'.")
            self.lbl_cal.setStyleSheet("color: #c00000; font-weight: bold;")

    # ------------------------------------------------------------ batch
    def start_batch(self):
        if self.busy():
            return
        text = self.ed_batch.text().strip()
        self.qs.setValue("batch", text)
        try:
            nums = R.parse_shot_range(text) if text else None
        except ValueError:
            self.lbl_batch.setText(f"Could not read the shot list: {text!r}")
            return
        refs = [r for r in self.index if r.number is not None
                and (nums is None or r.number in nums)]
        if not refs:
            self.lbl_batch.setText("No matching numbered shots under this logs folder.")
            return
        ver = self._reload()
        if ver is None:
            return
        self._batch_rows = []
        self.tbl_batch.setRowCount(0)
        self.lbl_batch.setText(f"Running {len(refs)} shot(s) with pipeline {ver} ...")
        self.log(f"[REPLAY] batch of {len(refs)} shot(s), pipeline {ver}")
        job = BatchJob(refs, self.stored, self.cal_overrides(), self.chk_batch_png.isChecked(),
                       self)
        job.row.connect(self._batch_row)
        job.finished_all.connect(self._batch_done)
        job.finished.connect(lambda: self._set_busy(False))
        self._batch = job
        self._set_busy(True)
        job.start()

    def stop_batch(self):
        if self._batch is not None:
            self._batch.stop()
            self.lbl_batch.setText(self.lbl_batch.text() + "  stopping after this shot ...")

    def _batch_row(self, d):
        self._batch_rows.append(d)
        if d["new"]:
            self.replay_rows[d["ref"].key] = d["new"]
        ref, stored, new = d["ref"], d["stored"], d["new"]
        r = self.tbl_batch.rowCount()
        self.tbl_batch.insertRow(r)
        it = QTableWidgetItem(ref.name)
        it.setData(Qt.ItemDataRole.UserRole, ref)
        self.tbl_batch.setItem(r, 0, it)
        rank = {"ok": 0, "no_fire": 1, "missing_waveforms": 2, "failed": 3}
        for j, c in enumerate(self.batch_cols, start=1):
            nv = d["crash"] if (c == "error" and d["crash"]) else new.get(c, "")
            sv = stored.get(c, "")
            txt = str(nv)
            a, b = R._f(sv), R._f(nv)
            if np.isfinite(a) and np.isfinite(b) and a != b:
                txt += f"  ({b - a:+.3g})"
            it = QTableWidgetItem(txt)
            it.setToolTip(f"stored: {sv}\nnew: {nv}")
            if c == "status" and stored and rank.get(nv, 4) > rank.get(sv, 4):
                it.setBackground(WORSE)
            elif stored and str(sv) != str(nv):
                it.setBackground(CHANGED)
            self.tbl_batch.setItem(r, j, it)
        self.lbl_batch.setText(f"{len(self._batch_rows)} done ...")

    def _batch_done(self, n, stopped):
        changed = sum(1 for d in self._batch_rows if d["stored"] and any(
            str(d["stored"].get(c, "")) != str(d["new"].get(c, "")) for c in self.batch_cols))
        worse = sum(1 for d in self._batch_rows if d["crash"] or (
            d["new"].get("status") == "failed" and d["stored"].get("status") != "failed"))
        self.lbl_batch.setText(f"{'Stopped' if stopped else 'Done'}: {n} shot(s), "
                               f"{changed} changed vs stored, {worse} newly failed/crashed.")
        self.log(f"[REPLAY] batch {self.lbl_batch.text()}")
        self.tbl_batch.resizeColumnsToContents()

    def _batch_row_clicked(self, r, _c):
        it = self.tbl_batch.item(r, 0)
        if it is not None:
            self.tabs.setCurrentIndex(1)
            self.load_ref(it.data(Qt.ItemDataRole.UserRole))

    def export_batch(self):
        if not self._batch_rows:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export batch comparison", str(R.SANDBOX_BASE / "batch_compare.csv"),
            "CSV (*.csv)")
        if not path:
            return
        cols = R.COMPARE_COLS
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["shot", "key"] + [f"stored_{c}" for c in cols]
                       + [f"new_{c}" for c in cols] + ["crash"])
            for d in self._batch_rows:
                w.writerow([d["ref"].number, d["ref"].key]
                           + [d["stored"].get(c, "") for c in cols]
                           + [d["new"].get(c, "") for c in cols] + [d["crash"]])
        self.log(f"[REPLAY] batch comparison written to {path}")

    # ------------------------------------------------------------ plot controls
    def _build_plot_controls(self):
        """The ltgs_gui3 panel: a column of actions beside Traces / Style / Axes."""
        w = QWidget()
        h = QHBoxLayout(w)
        col = QVBoxLayout()
        col.setSpacing(4)

        def button(text, fn, tip=""):
            b = QPushButton(text)
            b.clicked.connect(fn)
            if tip:
                b.setToolTip(tip)
            col.addWidget(b)
            return b

        col.addWidget(QLabel("Results from:"))
        self.cmb_source = QComboBox()
        self.cmb_source.addItems(["Stored (production)", "Replay where run, else stored"])
        self.cmb_source.setCurrentIndex(int(self.qs.value("source", 0)))
        self.cmb_source.setToolTip(
            "Stored: processed_shots, what the lab GUI produced.\n"
            "Replay: this tool's runs (single shots and Batch rerun) with your current code.")
        self.cmb_source.currentIndexChanged.connect(self._source_changed)
        col.addWidget(self.cmb_source)
        col.addSpacing(6)
        button("Overlay checked", lambda: self._trace_fig("Overlay", F.overlay_figure),
               "Ticked traces of every checked shot on one plot; colour = shot")
        button("Grid checked", lambda: self._trace_fig("Grid", F.grid_figure),
               "One panel per checked shot, ticked traces in their own colours")
        self.cmb_group = QComboBox()
        self.cmb_group.setToolTip("Commanded pulse spacing groups")
        col.addWidget(self.cmb_group)
        button("Select spacing group", self.select_spacing_group,
               "Check exactly the shots commanded at this spacing")
        button("Select all healthy", self.select_healthy,
               "Check shots that fired, analysed with no warning and have both RVM gains")
        col.addSpacing(6)
        button("LTGS only", lambda: self.style.set_visible(["D1", "D2", "B1", "B2"]),
               "Show the LTGS D-dots and B-dots only")
        button("RVM overlay", lambda: self.style.set_visible(["D1", "D2", "R1", "R2"]),
               "Show the LTGS D-dots with the RVMs over them")
        button("Q-switch overlay", lambda: self.style.set_visible(["D1", "D2", "Q1", "Q2"]),
               "Show the LTGS D-dots with the Q-switch monitors (right axis)")
        col.addSpacing(6)
        button("RVM all shots", lambda: self._all_shots_fig(["R1", "R2"], "RVM all shots"))
        button("D1 all shots", lambda: self._all_shots_fig(["D1"], "D1 all shots"))
        button("D2 all shots", lambda: self._all_shots_fig(["D2"], "D2 all shots"))
        button("B-dots all shots", lambda: self._all_shots_fig(["B1", "B2"], "B-dots all shots"))
        col.addSpacing(6)
        button("Peaks figure", lambda: self._row_fig(
            "Peaks", lambda rows: F.peaks_figure(rows, self.style)))
        button("Peaks vs pressure", lambda: self._row_fig(
            "Peaks vs pressure", lambda rows: F.peaks_figure(
                rows, self.style, lambda r: R._f(r.get("pressure_psi")), "Pressure (psi)")))
        button("Peaks vs charge kV", lambda: self._row_fig(
            "Peaks vs charge kV", lambda rows: F.peaks_figure(
                rows, self.style, R.charge_kv, "Charge (kV, mean of WJ1/WJ2)")))
        button("Spacing check", lambda: self._row_fig("Spacing check", F.spacing_figure))
        button("Shot info", self.shot_info)
        button("Group stats", self.group_stats)
        col.addSpacing(6)
        button("Close all figures", self.close_figures)
        button("Rescan folder", self.rescan)
        col.addStretch()
        h.addLayout(col)

        box = QGroupBox("Traces / Style / Axes")
        bl = QVBoxLayout(box)
        self.style = F.StylePanel(self.qs)
        self.style.changed.connect(lambda: self._show_plots(keep_view=False))
        bl.addWidget(self.style)
        h.addWidget(box, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(w)
        return scroll

    # which result each shot uses
    def _use_replay(self):
        return self.cmb_source.currentIndex() == 1

    def row_for(self, ref):
        if self._use_replay() and ref.key in self.replay_rows:
            return self.replay_rows[ref.key]
        return self.stored.get(ref.key, {})

    def _mat_for(self, ref):
        if self._use_replay():
            p = R.SANDBOX_BASE / ref.key / f"{ref.key}.mat"
            if p.exists():
                return p
        p = Path(self.ed_root.text().strip()) / "processed_shots" / f"{ref.key}.mat"
        return p if p.exists() else None

    def result_for(self, ref):
        """The trimmed result of one shot, from its .mat, cached."""
        p = self._mat_for(ref)
        if p is None:
            return None
        k = (str(p), p.stat().st_mtime_ns)
        if k not in self._mat_cache:
            if len(self._mat_cache) > 200:
                self._mat_cache.clear()
            self._mat_cache[k] = R.load_mat_result(p)
        return self._mat_cache[k]

    def _source_changed(self, i):
        self.qs.setValue("source", i)
        self._fill_groups()

    # selection
    def _shot_checked(self, it):
        ref = it.data(Qt.ItemDataRole.UserRole)
        if it.checkState() == Qt.CheckState.Checked:
            self.checked.add(ref.key)
        else:
            self.checked.discard(ref.key)

    def _check(self, pred):
        self.checked = {r.key for r in self.index if pred(r)}
        self._fill_list()
        self.status(f"{len(self.checked)} shot(s) checked.")

    def checked_refs(self):
        return [r for r in self.index if r.key in self.checked]

    def _spacing(self, ref):
        return (R.spacing_of(self.row_for(ref))
                or R.spacing_of({"spacing_cmd_ns": ref.meta.get("pulse_spacing_ns")}))

    def _fill_groups(self):
        cur = self.cmb_group.currentText()
        groups = sorted({g for g in (self._spacing(r) for r in self.index) if g is not None})
        self.cmb_group.clear()
        self.cmb_group.addItems([f"{g} ns" for g in groups])
        if cur:
            self.cmb_group.setCurrentText(cur)

    def select_spacing_group(self):
        txt = self.cmb_group.currentText().replace("ns", "").strip()
        if txt:
            g = int(txt)
            self._check(lambda r: self._spacing(r) == g)

    def select_healthy(self):
        self._check(lambda r: R.is_healthy(self.row_for(r)))

    # figures
    def _need_checked(self):
        refs = self.checked_refs()
        if not refs:
            self.status("Tick some shots in the list first (or Select spacing group / "
                        "Select all healthy).", "#b36b00")
        return refs

    def _open_fig(self, title, body, copy_text=None):
        win = F.FigureWindow(title, body, copy_text=copy_text)
        win.destroyed.connect(lambda *_: self.fig_windows.remove(win)
                              if win in self.fig_windows else None)
        self.fig_windows.append(win)
        win.show()
        win.raise_()
        return win

    def _results(self, refs):
        """Load the results of refs; report the ones without a .mat."""
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            out, missing = [], []
            for r in refs:
                try:
                    S = self.result_for(r)
                except Exception as e:  # noqa: BLE001
                    self.log(f"[REPLAY] could not read the result of {r.name}: {e}")
                    S = None
                if S is None:
                    missing.append(r.name)
                else:
                    out.append(S)
        finally:
            QApplication.restoreOverrideCursor()
        if missing:
            self.log(f"[REPLAY] no processed result (.mat) for: {', '.join(missing)}. "
                     "Run Analyze all shots in the lab GUI, or Batch rerun here.")
        return out, missing

    def _trace_fig(self, what, builder):
        refs = self._need_checked()
        if not refs:
            return
        shots, missing = self._results(refs)
        shots = [S for S in shots if S.get("status") == "ok"]
        if not shots:
            self.status("None of the checked shots has analysis traces (fired + processed).",
                        "#b36b00")
            return
        self._open_fig(f"{what}: {len(shots)} shot(s)", builder(shots, self.style))
        self.status(f"{what}: {len(shots)} shot(s)"
                    + (f", {len(missing)} without a result (see Log)" if missing else ""))

    def _all_shots_fig(self, keys, title):
        refs = self._need_checked()
        if not refs:
            return
        shots = [S for S in self._results(refs)[0] if S.get("status") == "ok"]
        if shots:
            self._open_fig(f"{title}: {len(shots)} shot(s)",
                           F.all_shots_figure(shots, keys, self.style, title))

    def _rows(self, refs):
        rows = []
        for r in refs:
            row = dict(self.row_for(r))
            row.setdefault("status", "not processed")
            row["label"] = str(r.number) if r.number is not None else r.name
            for c, m in (("pressure_psi", "pressure_psi"), ("wj1_charge_kv", "wj1_charge_kv"),
                         ("wj2_charge_kv", "wj2_charge_kv"),
                         ("spacing_cmd_ns", "pulse_spacing_ns"), ("datetime", "datetime")):
                if not row.get(c):
                    row[c] = r.meta.get(m, "")
            rows.append(row)
        return rows

    def _row_fig(self, title, builder):
        refs = self._need_checked()
        if refs:
            self._open_fig(f"{title}: {len(refs)} shot(s)", builder(self._rows(refs)))

    def shot_info(self):
        refs = self._need_checked()
        if refs:
            t, text = F.shot_info_table(list(zip(refs, self._rows(refs))))
            self._open_fig(f"Shot info: {len(refs)} shot(s)", t, copy_text=text)

    def group_stats(self):
        refs = self._need_checked()
        if refs:
            t, text = F.group_stats_table(self._rows(refs))
            self._open_fig(f"Group stats: {len(refs)} shot(s)", t, copy_text=text)

    def close_figures(self):
        for w in list(self.fig_windows):
            w.close()
        self.fig_windows.clear()

    # ------------------------------------------------------------ misc
    def open_in_editor(self, path):
        """VS Code when it is on PATH, else the folder. Never os.startfile
        on a .py: on many Windows setups that runs it."""
        code = shutil.which("code")
        try:
            if code:
                subprocess.Popen([code, "-g", str(path)])
            else:
                open_with_system(Path(path).parent)
        except OSError as e:
            self.log(f"[REPLAY] could not open {path}: {e}")

    def open_sandbox(self):
        d = self.current.out_dir if self.current else R.SANDBOX_BASE
        d.mkdir(parents=True, exist_ok=True)
        open_with_system(d)

    def closeEvent(self, event):
        self.close_figures()
        for k, w in (("auto", self.chk_auto), ("png", self.chk_png),
                     ("overlay", self.chk_overlay)):
            self.qs.setValue(k, "true" if w.isChecked() else "false")
        if self._batch is not None and self._batch.isRunning():
            self._batch.stop()
            self._batch.wait(60000)
        if self._job is not None and self._job.isRunning():
            self._job.wait(60000)
        super().closeEvent(event)
