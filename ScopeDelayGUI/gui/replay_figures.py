# gui/replay_figures.py
"""The ltgs_gui3 side of Shot Replay: trace / style / axes controls and the
multi-shot figures (overlay, grid, all-shots, peaks, spacing, tables).

Every figure opens in its own window, like a MATLAB figure; all of them are
interactive pyqtgraph plots (zoom with the wheel, drag to pan, right-click
for View All and export) and have a Save PNG button.
"""

import math

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from analysis import replay as R

PEN_STYLE = {"solid": Qt.PenStyle.SolidLine, "dash": Qt.PenStyle.DashLine,
             "dashdot": Qt.PenStyle.DashDotLine, "dot": Qt.PenStyle.DotLine}

DEFAULT_LIMITS = {"xmin": -4.7, "xmax": 4.7, "ymin": -660.0, "ymax": 100.0,
                  "qmin": -1.0, "qmax": 6.0}


# ===================================================================
# Traces / Style / Axes
# ===================================================================
class StylePanel(QWidget):
    """Show + colour per trace, line width and axis limits. Emits changed
    whenever anything is edited; the values are kept in QSettings."""

    changed = pyqtSignal()

    def __init__(self, qsettings, parent=None):
        super().__init__(parent)
        self.qs = qsettings
        g = QGridLayout(self)
        g.setVerticalSpacing(4)
        for c, h in enumerate(("Show", "Trace", "Color")):
            lab = QLabel(h)
            lab.setStyleSheet("font-weight: bold;")
            g.addWidget(lab, 0, c)
        self.show_boxes, self.color_boxes = {}, {}
        shown = set((self.qs.value("traces_shown", "") or ",".join(R.TRACE_KEYS)).split(","))
        for r, (key, label, *_rest) in enumerate(R.TRACES, start=1):
            default_color = R.TRACE[key][6]
            cb = QCheckBox()
            cb.setChecked(key in shown)
            cb.toggled.connect(self._emit)
            combo = QComboBox()
            combo.addItems(list(R.COLORS))
            combo.setCurrentText(self.qs.value(f"color_{key}", default_color) or default_color)
            combo.currentTextChanged.connect(self._emit)
            g.addWidget(cb, r, 0)
            g.addWidget(QLabel(label), r, 1)
            g.addWidget(combo, r, 2)
            self.show_boxes[key], self.color_boxes[key] = cb, combo
        r = len(R.TRACES) + 1
        g.addWidget(QLabel("Line width"), r, 0, 1, 2)
        self.width_box = QDoubleSpinBox()
        self.width_box.setRange(0.5, 6.0)
        self.width_box.setSingleStep(0.5)
        self.width_box.setValue(float(self.qs.value("line_width", 1.5)))
        self.width_box.valueChanged.connect(self._emit)
        g.addWidget(self.width_box, r, 2)
        self.limit_edits = {}
        for label, key in (("X min, us", "xmin"), ("X max, us", "xmax"),
                           ("Y min, kV", "ymin"), ("Y max, kV", "ymax"),
                           ("Q min, V", "qmin"), ("Q max, V", "qmax")):
            r += 1
            g.addWidget(QLabel(label), r, 0, 1, 2)
            ed = QLineEdit(str(self.qs.value(f"lim_{key}", DEFAULT_LIMITS[key])))
            ed.setAlignment(Qt.AlignmentFlag.AlignRight)
            ed.editingFinished.connect(self._emit)
            g.addWidget(ed, r, 2)
            self.limit_edits[key] = ed
        r += 1
        b = QPushButton("Default limits")
        b.clicked.connect(self.reset_limits)
        g.addWidget(b, r, 0, 1, 3)
        g.setRowStretch(r + 1, 1)

    # ------------------------------------------------------- values
    def visible(self):
        return [k for k in R.TRACE_KEYS if self.show_boxes[k].isChecked()]

    def color(self, key):
        return R.COLORS.get(self.color_boxes[key].currentText(), "#000000")

    def width(self):
        return self.width_box.value()

    def _lim(self, key):
        try:
            return float(self.limit_edits[key].text())
        except ValueError:
            return DEFAULT_LIMITS[key]

    def xlim(self):
        return self._lim("xmin"), self._lim("xmax")

    def ylim(self):
        return self._lim("ymin"), self._lim("ymax")

    def qlim(self):
        return self._lim("qmin"), self._lim("qmax")

    def pen(self, key, color=None, faint=False):
        c = QColor(color or self.color(key))
        if faint:
            c.setAlpha(110)
        return pg.mkPen(c, width=self.width(), style=PEN_STYLE[R.TRACE[key][7]])

    # ------------------------------------------------------- edits
    def set_visible(self, keys):
        """A preset: show exactly these traces."""
        for k, cb in self.show_boxes.items():
            cb.blockSignals(True)
            cb.setChecked(k in keys)
            cb.blockSignals(False)
        self._emit()

    def reset_limits(self):
        for k, ed in self.limit_edits.items():
            ed.setText(str(DEFAULT_LIMITS[k]))
        self._emit()

    def _emit(self, *_):
        self.qs.setValue("traces_shown", ",".join(self.visible()))
        for k, combo in self.color_boxes.items():
            self.qs.setValue(f"color_{k}", combo.currentText())
        self.qs.setValue("line_width", self.width())
        for k, ed in self.limit_edits.items():
            self.qs.setValue(f"lim_{k}", ed.text())
        self.changed.emit()


# ===================================================================
# Drawing helpers
# ===================================================================
def q_axis(p, label="Q-switch (V)"):
    """A right-hand axis with its own ViewBox, X-linked to plot p, for the
    Q-switch traces (volts) on a kV plot. p must already be in a layout."""
    vb = pg.ViewBox()
    p.showAxis("right")
    p.scene().addItem(vb)
    p.getAxis("right").linkToView(vb)
    p.getAxis("right").setLabel(label)
    vb.setXLink(p)

    def update():
        vb.setGeometry(p.vb.sceneBoundingRect())
        vb.linkedViewChanged(p.vb, vb.XAxis)
    p.vb.sigResized.connect(update)
    update()
    return vb


def curve(t, y, pen, name=None):
    item = pg.PlotDataItem(np.asarray(t, float), np.asarray(y, float), pen=pen, name=name)
    item.setDownsampling(auto=True, method="peak")
    return item


def draw_shot(p, S, keys, style, qvb=None, color=None, prefix="", legend=True):
    """Draw the chosen traces of one result on plot p (volts on qvb)."""
    for key in keys:
        xy = R.trace_xy(S, key)
        if xy is None:
            continue
        name = (prefix + R.TRACE[key][1]) if legend else None
        item = curve(xy[0], xy[1], style.pen(key, color), name)
        if R.TRACE[key][5] == "V":
            if qvb is None:
                continue
            qvb.addItem(item)
            if name and p.legend is not None:
                p.legend.addItem(item, name)
        else:
            p.addItem(item)


def shot_colors(n):
    return [pg.intColor(i, hues=max(n, 7), values=1, maxValue=220, minValue=150)
            for i in range(n)]


def shot_label(S):
    sp = (S.get("settings") or {}).get("pulse_spacing_cmd_ns")
    sp = f"  {sp:.0f} ns" if isinstance(sp, (int, float)) and np.isfinite(sp) else ""
    return f"{S.get('name', '')}{sp}"


def _f(x):
    return R._f(x)


# ===================================================================
# Figure windows
# ===================================================================
class FigureWindow(QWidget):
    """A top-level window holding one figure, with Save PNG."""

    def __init__(self, title, body, parent=None, copy_text=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(title)
        self.resize(1200, 800)
        v = QVBoxLayout(self)
        v.addWidget(body, 1)
        row = QHBoxLayout()
        row.addStretch()
        if copy_text is not None:
            b = QPushButton("Copy table")
            b.clicked.connect(lambda: QGuiApplication.clipboard().setText(copy_text))
            row.addWidget(b)
        b = QPushButton("Save PNG...")
        b.clicked.connect(lambda: self._save(body))
        row.addWidget(b)
        v.addLayout(row)

    def _save(self, body):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save figure", self.windowTitle().replace(":", "").replace(" ", "_") + ".png",
            "PNG (*.png)")
        if path:
            body.grab().save(path)


def _plot(glw, row, col, title, ylab, xlab="Time from pulse 1 (us)"):
    p = glw.addPlot(row=row, col=col, title=title)
    p.showGrid(x=True, y=True, alpha=0.25)
    p.setLabel("left", ylab)
    if xlab:
        p.setLabel("bottom", xlab)
    p.addLegend(offset=(-10, 10))
    return p


def _limits(p, style, qvb=None, y=True):
    p.setXRange(*style.xlim(), padding=0)
    if y:
        p.setYRange(*style.ylim(), padding=0)
    if qvb is not None:
        qvb.setYRange(*style.qlim(), padding=0)


def overlay_figure(shots, style):
    """Every checked shot on one plot. Colour = shot, line style = trace."""
    keys = style.visible()
    glw = pg.GraphicsLayoutWidget()
    glw.setBackground("w")
    p = _plot(glw, 0, 0, f"Overlay of {len(shots)} shot(s)", "Voltage (kV)")
    qvb = q_axis(p) if any(R.TRACE[k][5] == "V" for k in keys) else None
    for S, c in zip(shots, shot_colors(len(shots))):
        draw_shot(p, S, keys, style, qvb, color=c, prefix=f"{S.get('name', '')} ")
    _limits(p, style, qvb)
    return glw


def grid_figure(shots, style):
    """One panel per checked shot, traces in their own colours."""
    keys = style.visible()
    glw = pg.GraphicsLayoutWidget()
    glw.setBackground("w")
    ncol = max(1, math.ceil(math.sqrt(len(shots))))
    first = None
    for i, S in enumerate(shots):
        r, c = divmod(i, ncol)
        p = _plot(glw, r, c, shot_label(S) + ("" if S.get("status") == "ok"
                                              else f"  [{S.get('status')}]"),
                  "kV" if c == 0 else "", xlab="us" if r == (len(shots) - 1) // ncol else "")
        if i:
            p.legend.setVisible(False)
        qvb = q_axis(p, "V") if any(R.TRACE[k][5] == "V" for k in keys) else None
        draw_shot(p, S, keys, style, qvb, legend=(i == 0))
        _limits(p, style, qvb)
        if first is None:
            first = p
        else:
            p.setXLink(first)
            p.setYLink(first)
    return glw


def all_shots_figure(shots, keys, style, title):
    """One panel per trace in keys, every shot on it, colour = shot."""
    glw = pg.GraphicsLayoutWidget()
    glw.setBackground("w")
    colors = shot_colors(len(shots))
    first = None
    for row, key in enumerate(keys):
        unit = R.TRACE[key][5]
        p = _plot(glw, row, 0, f"{R.TRACE[key][1]}, {len(shots)} shot(s)",
                  "Q-switch (V)" if unit == "V" else "Voltage (kV)")
        for S, c in zip(shots, colors):
            xy = R.trace_xy(S, key)
            if xy is not None:
                p.addItem(curve(xy[0], xy[1], style.pen(key, c), shot_label(S)))
        p.setXRange(*style.xlim(), padding=0)
        if unit == "V":
            p.setYRange(*style.qlim(), padding=0)
        if first is None:
            first = p
        else:
            p.setXLink(first)
        if row:
            p.legend.setVisible(False)
    glw.setWindowTitle(title)
    return glw


def _index_axis(p, rows):
    ticks = [(i, str(r.get("label") or r.get("shot_number") or "")) for i, r in enumerate(rows)]
    step = max(1, len(ticks) // 25)
    p.getAxis("bottom").setTicks([ticks[::step], []])


PEAK_SETS = (
    ("Peak |V|, voltage monitors (kV)",
     (("LTGS1_Ddot_kV", "LTGS1-232 D-dot", "D1"), ("LTGS2_Ddot_kV", "LTGS2-232 D-dot", "D2"),
      ("C225_Ddot_kV", "C225 D-dot", "C225"), ("RVM1_kV", "RVM 1", "R1"),
      ("RVM2_kV", "RVM 2", "R2"))),
    ("Peak |Z*I|, current monitors (kV)",
     (("LTGS1_Bdot_kV", "LTGS1-007 B-dot", "B1"), ("LTGS2_Bdot_kV", "LTGS2-007 B-dot", "B2"),
      ("C315_Bdot_kV", "C315 B-dot", "C315"))),
)


def peaks_figure(rows, style, xfunc=None, xlabel="Shot"):
    """Peaks per shot (xfunc None) or against a shot quantity (pressure,
    charge kV). Only fired shots."""
    rows = [r for r in rows if r.get("status") == "ok"]
    glw = pg.GraphicsLayoutWidget()
    glw.setBackground("w")
    x = (np.arange(len(rows), dtype=float) if xfunc is None
         else np.array([xfunc(r) for r in rows], dtype=float))
    for i, (title, cols) in enumerate(PEAK_SETS):
        p = _plot(glw, i, 0, title + ("" if xfunc is None else f" vs {xlabel}"), "kV",
                  xlab=xlabel)
        for col, lab, key in cols:
            y = np.array([_f(r.get(col)) for r in rows])
            m = np.isfinite(x) & np.isfinite(y)
            p.plot(x[m], y[m], pen=None, symbol="o", symbolSize=9,
                   symbolBrush=style.color(key), symbolPen=None, name=lab)
        if xfunc is None:
            _index_axis(p, rows)
    if not rows:
        glw.addLabel("No fired (status ok) shots among the checked ones.", row=2, col=0)
    return glw


def spacing_figure(rows):
    """Measured minus commanded pulse spacing per shot, and measured against
    commanded. Dry shots count too: their Q-switch timing is still measured."""
    rows = [r for r in rows if np.isfinite(_f(r.get("spacing_cmd_ns")))]
    glw = pg.GraphicsLayoutWidget()
    glw.setBackground("w")
    x = np.arange(len(rows), dtype=float)
    cmd = np.array([_f(r.get("spacing_cmd_ns")) for r in rows])
    p = _plot(glw, 0, 0, "Pulse spacing error", "Measured - commanded (ns)", xlab="Shot")
    p.addItem(pg.InfiniteLine(0, angle=0, pen=pg.mkPen("k", width=1)))
    p2 = _plot(glw, 1, 0, "Measured vs commanded", "Measured (ns)", xlab="Commanded (ns)")
    for col, lab, color, sym in (("spacing_qsw_ns", "Q-switch rise", "#d9541a", "o"),
                                 ("spacing_rvm_ns", "RVM collapse", "#0000ff", "d")):
        y = np.array([_f(r.get(col)) for r in rows])
        m = np.isfinite(y)
        p.plot(x[m], (y - cmd)[m], pen=None, symbol=sym, symbolSize=9, symbolBrush=color,
               symbolPen=None, name=lab)
        p2.plot(cmd[m], y[m], pen=None, symbol=sym, symbolSize=9, symbolBrush=color,
                symbolPen=None, name=lab)
    if cmd.size:
        lo, hi = float(np.nanmin(cmd)), float(np.nanmax(cmd))
        pad = max(50.0, 0.1 * (hi - lo))
        p2.plot([lo - pad, hi + pad], [lo - pad, hi + pad], pen=pg.mkPen("k", width=1,
                style=Qt.PenStyle.DashLine), name="measured = commanded")
    _index_axis(p, rows)
    return glw


def table_widget(headers, rows):
    """(QTableWidget, tab-separated text for the clipboard)."""
    t = QTableWidget(len(rows), len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    for i, r in enumerate(rows):
        for j, v in enumerate(r):
            it = QTableWidgetItem(str(v))
            it.setToolTip(str(v))
            t.setItem(i, j, it)
    t.resizeColumnsToContents()
    text = "\n".join("\t".join(str(v) for v in r) for r in [headers] + list(rows))
    return t, text


SHOT_INFO_COLS = [
    ("shot", None), ("datetime", "datetime"), ("status", "status"),
    ("psi", "pressure_psi"), ("WJ1 kV", "wj1_charge_kv"), ("WJ2 kV", "wj2_charge_kv"),
    ("cmd ns", "spacing_cmd_ns"), ("Qsw ns", "spacing_qsw_ns"), ("RVM ns", "spacing_rvm_ns"),
    ("D1 kV", "LTGS1_Ddot_kV"), ("D2 kV", "LTGS2_Ddot_kV"), ("B1 kV", "LTGS1_Bdot_kV"),
    ("B2 kV", "LTGS2_Bdot_kV"), ("C225 kV", "C225_Ddot_kV"), ("RVM1 kV", "RVM1_kV"),
    ("RVM2 kV", "RVM2_kV"), ("gain 1", "rvm_gain_1"), ("gain 2", "rvm_gain_2"),
]
META_COLS = [("DG B us", "dg535_laser_B_delay_us"), ("DG D us", "dg535_laser_D_delay_us"),
             ("BNC A us", "bnc575_A_delay_us"), ("BNC B us", "bnc575_B_delay_us"),
             ("notes", "notes")]


def _short(v):
    x = _f(v)
    return f"{x:.4g}" if np.isfinite(x) else (v or "")


def shot_info_table(items):
    """items: [(ref, row)]. The settings and results of each checked shot."""
    headers = [h for h, _ in SHOT_INFO_COLS] + [h for h, _ in META_COLS] + ["error"]
    rows = []
    for ref, row in items:
        vals = [ref.name] + [_short(row.get(c, "")) if c not in ("datetime", "status")
                             else (row.get(c) or ref.meta.get(c, ""))[:19]
                             for _, c in SHOT_INFO_COLS[1:]]
        vals += [_short(ref.meta.get(c, "")) for _, c in META_COLS]
        vals.append(row.get("error", ""))
        rows.append(vals)
    return table_widget(headers, rows)


def group_stats_table(rows):
    stats = R.group_stats(rows)
    headers = ["cmd ns", "n", "n ok"] + [
        (c.replace("spacing_", "").replace("_ns", " err ns") if c.startswith("spacing_") else c)
        for c in R.STAT_COLS]
    out = []
    for s in stats:
        vals = [s["spacing_cmd_ns"], s["n"], s["n_ok"]]
        for c in R.STAT_COLS:
            v = s[c]
            vals.append("" if v is None else
                        f"{v[0]:.4g} ± {v[1]:.2g}  ({v[2]:.4g} .. {v[3]:.4g})")
        out.append(vals)
    return table_widget(headers, out)
