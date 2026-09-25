# gui/scope_screen.py
"""
One Rigol-style screen for one scope.

White background, a 10 x 8 division graticule with a centre crosshair and
tick marks, a single vertical axis in divisions (-4 to +4), and every channel
placed where the scope's own screen puts it:

    position_div = (V + offset_v) / scale_v_div

with scale_v_div and offset_v from the settings read at arm time. That sign
follows the programming guide (2-228): YORigin = VerticalOffset / YINCrement
and the reference (128) is screen centre, so with the driver's
v = (code - yref - yorig) * yinc the centre of the screen sits at -offset and
a channel's 0 V sits offset/scale divisions above it. The plot window checks
this against the preamble of each real capture and logs the result.

A channel whose scale or offset is UNKNOWN is autoscaled to fill 8 divisions
and marked "auto" in the info bar - never a guessed default.

The x axis spans 10 divisions of timebase_scale_s_div centred on
timebase_offset_s, in engineering units; the trigger instant (t = 0 in the
capture's time axis) is marked at the top, at the edge if off screen.

Pure display: nothing here talks to hardware, changes capture, export or
logging.
"""

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from utils.downsample import visible_downsample

# Rigol channel order, darkened to stay readable on white.
CH_COLORS = {1: "#C9A000", 2: "#00A0B0", 3: "#D000D0", 4: "#1F3FBF"}
H_DIVS = 10          # horizontal divisions (time)
V_DIVS = 8           # vertical divisions (-4 .. +4)
TICKS_PER_DIV = 5    # small marks on the centre lines, as on the scope

GRID_COLOR = QColor(205, 205, 205)
CENTER_COLOR = QColor(140, 140, 140)


def fnum(value):
    """float from a SCPI reply, or None for UNKNOWN / blank / unparseable."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def eng(value, unit, precision=3):
    """Engineering notation with an SI prefix: 92.0 kV, 500 ns, 2.5 GSa/s."""
    if value is None:
        return "?"
    return pg.siFormat(value, suffix=unit, precision=precision)


def trigger_channel(source):
    """':TRIGger:EDGE:SOURce?' -> channel number, or None for EXT / AC line."""
    s = str(source or "").upper()
    for ch in (1, 2, 3, 4):
        if s in (f"CHAN{ch}", f"CHANNEL{ch}", f"CH{ch}"):
            return ch
    return None


class Placement:
    """Where one channel sits on the screen: divisions = (V + offset) / scale."""

    def __init__(self, scale, offset, auto=False):
        self.scale = float(scale)
        self.offset = float(offset)
        self.auto = auto

    def to_div(self, volts):
        return (np.asarray(volts, dtype=float) + self.offset) / self.scale

    def zero_div(self):
        """Screen position of this channel's 0 V - its ground marker."""
        return self.offset / self.scale


def placement_for(ch_settings, volts):
    """Placement from the arm-time settings, or an autoscale that fills 8
    divisions when scale or offset is UNKNOWN."""
    scale = fnum((ch_settings or {}).get("scale_v_div"))
    offset = fnum((ch_settings or {}).get("offset_v"))
    if scale is not None and scale > 0 and offset is not None:
        return Placement(scale, offset, auto=False)

    v = np.asarray(volts, dtype=float)
    v = v[np.isfinite(v)] if v.size else v
    if v.size == 0:
        return Placement(1.0, 0.0, auto=True)
    lo, hi = float(v.min()), float(v.max())
    span = hi - lo
    if span <= 0:
        span = abs(hi) * 2 or 1.0
    return Placement(span / V_DIVS, -(hi + lo) / 2.0, auto=True)


class ScopeScreen(QWidget):
    """One scope's screen: plot, markers, info bar and hover readout."""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.title = title
        self.settings = {}
        self.placements = {}          # ch -> Placement
        self.enabled = {ch: True for ch in (1, 2, 3, 4)}       # display = 1
        self.user_visible = {ch: True for ch in (1, 2, 3, 4)}  # checkboxes
        self.full = None              # ((t, v), ...) volts, full resolution
        self.display = None           # the display copy last given

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.setLayout(layout)

        self.plot = pg.PlotWidget(background="w")
        self.plot.setTitle(title, color="k", size="11pt")
        self.plot.showGrid(x=False, y=False)
        self.plot.setLabel("bottom", "Time", units="s")
        self.plot.setLabel("left", "div")
        self.plot.getAxis("bottom").enableAutoSIPrefix(True)
        left = self.plot.getAxis("left")
        left.setTicks([[(i, str(i)) for i in range(-4, 5)]])
        for name in ("left", "bottom"):
            ax = self.plot.getAxis(name)
            ax.setPen(pg.mkPen("k"))
            ax.setTextPen(pg.mkPen("k"))
        layout.addWidget(self.plot)

        self.vb = self.plot.getViewBox()
        self.vb.setMouseEnabled(x=True, y=True)
        self.vb.enableAutoRange(x=False, y=False)
        self.vb.setYRange(-4, 4, padding=0)

        # Graticule: dotted grid, darker centre crosshair, ticks on the centre
        # lines. Rebuilt whenever the time base changes.
        dotted = QPen(GRID_COLOR, 1, Qt.PenStyle.DotLine)
        dotted.setCosmetic(True)
        centre = QPen(CENTER_COLOR, 1, Qt.PenStyle.SolidLine)
        centre.setCosmetic(True)
        self.grid_item = pg.PlotCurveItem(pen=dotted, connect="pairs")
        self.centre_item = pg.PlotCurveItem(pen=centre, connect="pairs")
        self.tick_item = pg.PlotCurveItem(pen=centre, connect="pairs")
        for item in (self.grid_item, self.centre_item, self.tick_item):
            item.setZValue(-10)
            self.plot.addItem(item, ignoreBounds=True)

        # Channel curves, in Rigol order.
        self.curves = {}
        for ch in (1, 2, 3, 4):
            c = pg.PlotCurveItem(pen=pg.mkPen(CH_COLORS[ch], width=1.5), name=f"CH{ch}")
            c.setZValue(ch)
            self.plot.addItem(c)
            self.curves[ch] = c

        # Left-edge ground markers "1".."4" at each channel's zero level, and
        # a right-edge trigger-level marker in the source's colour. Invisible
        # infinite lines carrying labels: pyqtgraph keeps the labels on the
        # edge through any zoom or pan.
        no_pen = pg.mkPen(QColor(0, 0, 0, 0))
        self.zero_markers = {}
        for ch in (1, 2, 3, 4):
            line = pg.InfiniteLine(pos=0, angle=0, pen=no_pen, movable=False, label=str(ch),
                                   labelOpts={"position": 0.0, "color": "w",
                                              "fill": pg.mkBrush(CH_COLORS[ch]),
                                              "anchors": [(0, 0.5), (0, 0.5)]})
            line.setZValue(20)
            self.plot.addItem(line, ignoreBounds=True)
            self.zero_markers[ch] = line
        self.trig_marker = pg.InfiniteLine(pos=0, angle=0, pen=no_pen, movable=False, label="T",
                                           labelOpts={"position": 1.0, "color": "w",
                                                      "fill": pg.mkBrush("#606060"),
                                                      "anchors": [(1, 0.5), (1, 0.5)]})
        self.trig_marker.setZValue(20)
        self.trig_marker.setVisible(False)
        self.plot.addItem(self.trig_marker, ignoreBounds=True)

        # Trigger instant at the top of the screen.
        self.trig_time = pg.TextItem("T", color="#606060", anchor=(0.5, 0.0))
        self.trig_time.setZValue(21)
        self.plot.addItem(self.trig_time, ignoreBounds=True)
        self.vb.sigXRangeChanged.connect(lambda *_: self._place_trigger_time())
        self.vb.sigYRangeChanged.connect(lambda *_: self._place_trigger_time())

        # Bottom bar as on the scope's screen: one compact box per displayed
        # channel in its colour (name, V/div, offset), then the timebase box
        # and the trigger box at the right end. Rebuilt on every update.
        self.info = QWidget()
        self.info.setStyleSheet("background:white;")
        self.info_layout = QHBoxLayout()
        self.info_layout.setContentsMargins(4, 2, 4, 2)
        self.info_layout.setSpacing(6)
        self.info.setLayout(self.info_layout)
        layout.addWidget(self.info)
        self.boxes = {}                # ch -> QLabel, displayed channels only
        self.timebase_box = None
        self.trigger_box = None

        # Hover readout on its own line: the time, then each visible
        # channel's real volts in its colour.
        self.readout = QLabel("")
        self.readout.setStyleSheet("color:#222; background:white; padding:0 6px; font-size:9pt;")
        self.readout.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.readout)
        self._mouse_proxy = pg.SignalProxy(self.plot.scene().sigMouseMoved,
                                           rateLimit=30, slot=self._mouse_moved)

        self._build_graticule()
        self._place_trigger_time()

    # ------------------------------------------------------------ settings
    def set_settings(self, settings):
        """The arm-time settings dict {scope: {...}, channels: {ch: {...}}}."""
        self.settings = settings or {}
        chans = self.settings.get("channels") or {}
        for ch in (1, 2, 3, 4):
            entry = chans.get(ch) or chans.get(str(ch)) or {}
            disp = str(entry.get("display", "1")).strip().upper()
            self.enabled[ch] = disp not in ("0", "OFF")
        self._apply_time_axis()
        self._build_graticule()
        self._place_trigger_time()
        self._apply_visibility()

    def _scope(self):
        return self.settings.get("scope") or {}

    def _channel(self, ch):
        chans = self.settings.get("channels") or {}
        return chans.get(ch) or chans.get(str(ch)) or {}

    def time_window(self):
        """(x0, x1) of the scope screen, or None if the time base is unknown."""
        tb = fnum(self._scope().get("timebase_scale_s_div"))
        off = fnum(self._scope().get("timebase_offset_s"))
        if tb is None or tb <= 0:
            return None
        off = 0.0 if off is None else off
        return off - 5 * tb, off + 5 * tb

    def _apply_time_axis(self):
        win = self.time_window()
        if win is not None:
            self.vb.enableAutoRange(x=False)
            self.vb.setXRange(win[0], win[1], padding=0)
        else:
            self.vb.enableAutoRange(x=True)
        self.vb.setYRange(-4, 4, padding=0)

    # ----------------------------------------------------------- graticule
    def _build_graticule(self):
        win = self.time_window()
        if win is None:
            x0, x1 = self.vb.viewRange()[0]
        else:
            x0, x1 = win
        if not np.isfinite([x0, x1]).all() or x1 <= x0:
            x0, x1 = 0.0, 1.0
        div = (x1 - x0) / H_DIVS

        gx, gy = [], []
        for k in range(H_DIVS + 1):                 # vertical lines
            x = x0 + k * div
            gx += [x, x]
            gy += [-4, 4]
        for j in range(-4, 5):                      # horizontal lines
            gx += [x0, x1]
            gy += [j, j]
        self.grid_item.setData(np.array(gx), np.array(gy))

        xc = x0 + 5 * div
        self.centre_item.setData(np.array([xc, xc, x0, x1]), np.array([-4, 4, 0, 0]))

        tx, ty = [], []
        tick = div / TICKS_PER_DIV
        half_y = 0.08                                # in divisions
        half_x = 0.08 * div                          # in seconds
        for k in range(H_DIVS * TICKS_PER_DIV + 1):  # along the horizontal centre line
            x = x0 + k * tick
            tx += [x, x]
            ty += [-half_y, half_y]
        for k in range(V_DIVS * TICKS_PER_DIV + 1):  # along the vertical centre line
            y = -4 + k / TICKS_PER_DIV
            tx += [xc - half_x, xc + half_x]
            ty += [y, y]
        self.tick_item.setData(np.array(tx), np.array(ty))

    def _place_trigger_time(self):
        """'T' at the top of the screen at the trigger instant (t = 0), or at
        the edge pointing toward it when it is off screen."""
        (x0, x1), (y0, y1) = self.vb.viewRange()
        if not np.isfinite([x0, x1, y0, y1]).all():
            return
        if x0 <= 0.0 <= x1:
            self.trig_time.setText("T▼")
            self.trig_time.setAnchor((0.5, 0.0))
            self.trig_time.setPos(0.0, y1)
        elif 0.0 < x0:
            self.trig_time.setText("◀T")
            self.trig_time.setAnchor((0.0, 0.0))
            self.trig_time.setPos(x0, y1)
        else:
            self.trig_time.setText("T▶")
            self.trig_time.setAnchor((1.0, 0.0))
            self.trig_time.setPos(x1, y1)

    # ---------------------------------------------------------------- data
    def set_data(self, display_pairs, full_pairs=None):
        """display_pairs: ((t, v), ...) already downsampled, in VOLTS.
        full_pairs: the full-resolution arrays for zooming and the readout."""
        self.display = tuple((np.asarray(t, dtype=float), np.asarray(v, dtype=float))
                             for t, v in display_pairs)
        self.full = (tuple((np.asarray(t, dtype=float), np.asarray(v, dtype=float))
                           for t, v in full_pairs) if full_pairs is not None else None)
        self.placements = {}
        for ch, (t, v) in zip((1, 2, 3, 4), self.display):
            source = self.full[ch - 1][1] if self.full is not None else v
            self.placements[ch] = placement_for(self._channel(ch), source)
            if len(v) and self.enabled[ch]:
                self.curves[ch].setData(t, self.placements[ch].to_div(v))
            else:
                self.curves[ch].setData([], [])
            self.zero_markers[ch].setPos(self.placements[ch].zero_div())
        self._apply_visibility()
        self._place_trigger_level()
        self._apply_time_axis()
        self._build_graticule()
        self._place_trigger_time()
        self.update_info()
        # The scope screen is itself a zoom into the record: 10 divisions of
        # the time base, typically a few microseconds of a 400 us capture.
        # The display copy given above is the whole record in two points per
        # bin - a handful of bins across this window - so re-downsample the
        # visible slice from the full arrays now rather than after the first
        # zoom timer.
        self.refresh_visible()

    def set_user_visible(self, ch, visible):
        self.user_visible[ch] = bool(visible)
        self._apply_visibility()

    def _shown(self, ch):
        return self.enabled[ch] and self.user_visible[ch]

    def _apply_visibility(self):
        for ch in (1, 2, 3, 4):
            shown = self._shown(ch)
            self.curves[ch].setVisible(shown)
            self.zero_markers[ch].setVisible(shown and ch in self.placements)

    def _place_trigger_level(self):
        src = trigger_channel(self._scope().get("trigger_source"))
        level = fnum(self._scope().get("trigger_level_v"))
        if src is None or level is None or src not in self.placements:
            self.trig_marker.setVisible(False)
            return
        # Pinned to the top or bottom edge when the level is off screen, as
        # the scope pins its own "T".
        y = float(self.placements[src].to_div(level))
        self.trig_marker.setPos(max(-4.0, min(4.0, y)))
        self.trig_marker.label.fill = pg.mkBrush(CH_COLORS[src])
        self.trig_marker.setVisible(self._shown(src))

    def refresh_visible(self):
        """Zoomed: re-downsample the visible slice of the full arrays and
        re-place it in divisions. With X auto-range on, restore the display
        copy instead (see ScopePlotWindow._refresh_visible)."""
        if self.vb.autoRangeEnabled()[0]:
            if self.display:
                for ch, (t, v) in zip((1, 2, 3, 4), self.display):
                    if len(v) and self.enabled[ch] and ch in self.placements:
                        self.curves[ch].setData(t, self.placements[ch].to_div(v))
            return
        if not self.full:
            return
        x0, x1 = self.vb.viewRange()[0]
        for ch, (t, v) in zip((1, 2, 3, 4), self.full):
            if not len(v) or not self.enabled[ch] or ch not in self.placements:
                continue
            td, vd = visible_downsample(t, v, x0, x1)
            self.curves[ch].setData(td, self.placements[ch].to_div(vd))

    # ------------------------------------------------------------ info bar
    def channel_lines(self, ch):
        """The three lines of one channel's box, or None if it has no box.

        Name, V/div ("auto" when the settings were unreadable and the channel
        was fitted to the screen), offset. Nothing else: the scope's own bar
        is this terse.
        """
        if not self.enabled[ch]:
            return None
        p = self.placements.get(ch)
        if p is None:
            return [f"CH{ch}", "-", "-"]
        if p.auto:
            return [f"CH{ch}", "auto", "Ofs auto"]
        return [f"CH{ch}", f"{eng(p.scale, 'V')}/div", f"Ofs {eng(p.offset, 'V')}"]

    def timebase_lines(self):
        s = self._scope()
        tb = fnum(s.get("timebase_scale_s_div"))
        off = fnum(s.get("timebase_offset_s"))
        return [f"H {eng(tb, 's')}/div" if tb is not None else "H ?",
                f"Delay {eng(off, 's', 4)}" if off is not None else "Delay ?"]

    def trigger_lines(self):
        s = self._scope()
        src = str(s.get("trigger_source") or "").strip().upper()
        ch = trigger_channel(src)
        if ch is not None:
            name = f"CH{ch}"
        elif src.startswith("EXT"):
            name = "EXT"
        elif src.startswith("AC"):
            name = "AC"
        else:
            name = src if src and src != "UNKNOWN" else "?"
        slope = str(s.get("trigger_slope") or "").strip().upper()
        word = "rising" if slope.startswith("POS") else "falling" if slope.startswith("NEG") else ""
        level = fnum(s.get("trigger_level_v"))
        return [f"T {name} {word}".strip(), eng(level, "V") if level is not None else "?"]

    def trigger_color(self):
        ch = trigger_channel(self._scope().get("trigger_source"))
        return CH_COLORS[ch] if ch is not None else "#606060"

    @staticmethod
    def _make_box(lines, color):
        box = QLabel("\n".join(lines))
        box.setStyleSheet(f"QLabel {{ color: {color}; border: 1px solid {color}; "
                          f"border-radius: 3px; padding: 2px 6px; background: white; "
                          f"font-size: 9pt; font-weight: bold; }}")
        box.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return box

    def update_info(self):
        """Rebuild the bottom bar: channel boxes, a stretch, timebase, trigger."""
        while self.info_layout.count():
            item = self.info_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self.boxes = {}
        for ch in (1, 2, 3, 4):
            lines = self.channel_lines(ch)
            if lines is None:
                continue                      # hidden channels get no box
            box = self._make_box(lines, CH_COLORS[ch])
            self.info_layout.addWidget(box)
            self.boxes[ch] = box
        self.info_layout.addStretch()
        self.timebase_box = self._make_box(self.timebase_lines(), "#333333")
        self.info_layout.addWidget(self.timebase_box)
        self.trigger_box = self._make_box(self.trigger_lines(), self.trigger_color())
        self.info_layout.addWidget(self.trigger_box)

    def info_text(self):
        """The bar as plain text, boxes separated by ' || ', for tests."""
        parts = [self.boxes[ch].text().replace("\n", "|") for ch in sorted(self.boxes)]
        for box in (self.timebase_box, self.trigger_box):
            if box is not None:
                parts.append(box.text().replace("\n", "|"))
        return " || ".join(parts)

    # -------------------------------------------------------- hover readout
    def readout_at(self, x):
        """Real volts of each shown channel at time x, from the full arrays."""
        out = {}
        source = self.full if self.full is not None else self.display
        if not source:
            return out
        for ch, (t, v) in zip((1, 2, 3, 4), source):
            if not len(t) or not self._shown(ch):
                continue
            i = int(np.searchsorted(t, x))
            i = min(max(i, 0), len(t) - 1)
            out[ch] = float(v[i])
        return out

    def _mouse_moved(self, evt):
        pos = evt[0]
        if not self.plot.sceneBoundingRect().contains(pos):
            return
        x = self.vb.mapSceneToView(pos).x()
        volts = self.readout_at(x)
        if not volts:
            self.readout.setText("")
            return
        pieces = [f"t {eng(x, 's', 4)}"]
        for ch, v in volts.items():
            pieces.append(f'<span style="color:{CH_COLORS[ch]}"><b>CH{ch}</b> {eng(v, "V")}</span>')
        self.readout.setText("&nbsp;&nbsp;&nbsp;".join(pieces))

    # ---------------------------------------------------------------- misc
    def clear(self):
        for c in self.curves.values():
            c.setData([], [])
        self.full = None
        self.display = None
        self.placements = {}
        self._apply_visibility()
        self.trig_marker.setVisible(False)
        self.readout.setText("")
