"""
Plot one shot on the T0 time axis and compare it with the timing map.

T0 is the instant BNC 575 channel A asserts at its own connector. Every
trace is shifted from scope record time to "time at the sensor, after T0":

    t_sensor = t_record + trigger_arrival[scope] + scope_offset[scope]
               - cable_one_way[scope, channel]

Then the script draws where the timing map says each trigger edge should
be (dashed lines) and where the data says each event happened (markers),
and prints both side by side.

Usage, from the folder that holds the shot log and the rigol CSV files:

    python shot_timing.py --shot-log shot_log_20260924_170806.csv --shot 43
    python shot_timing.py --shot-log shot_log_20260924_170806.csv --shot 43 --show
    python shot_timing.py --shot-log ... --shot 43 --marx-delay-us 180

Or name the three files yourself, with the settings on the command line:

    python shot_timing.py --rigol1 a.csv --rigol2 b.csv --rigol3 c.csv \
        --bnc-a-us 0 --bnc-b-us 3.025 --qsw1-us 180.5 --qsw2-us 181.5

With no arguments at all, for example from an editor's Run button, it uses
DEFAULT_SHOT_LOG and DEFAULT_SHOT near the top of this file.

The screen room DG535 delay is not in the shot log, so it is an option
(--marx-delay-us, default 180). If it is wrong, the Trig Sync row shows it:
the measured edge will sit far from the predicted one.

Every shot in a session at once, as one table plus a CSV:

    python shot_timing.py --shot-log shot_log_20260924_170806.csv --all

Debug helpers:
    --raw            plot scope record time with no corrections
    --no-detect      skip the event finder and only draw traces and predictions
    --zoom 183.8 184.3   extra figure of every channel in that window (us after T0)
"""

import argparse
import csv
import json
import os
import sys

import numpy as np

# ----------------------------------------------------------------------------
# RUN BUTTON DEFAULTS. Used only when the script starts with no arguments,
# for example from the Run button in an editor. The shot log path is taken
# relative to the folder this script sits in.
# ----------------------------------------------------------------------------
DEFAULT_SHOT_LOG = "2026.09.24/experiment_log_20260924_170806/shot_log_20260924_170806.csv"
DEFAULT_SHOT = "43-46"       # one shot "43", a range "43-46", a list "43,45", or "all"
DEFAULT_SHOW = True          # open the figures on screen

# ----------------------------------------------------------------------------
# TIMING MAP. Edit here when a cable or a measurement changes. All in ns.
# ----------------------------------------------------------------------------
# Channel A edge at each scope EXT TRIG. The three trigger cables were replaced
# on 5 Oct 2026 at about noon. Shots before that used the old, longer cables
# (4.599 ns to scope 1, 4.604 ns on to scope 2, 9.188 ns on to scope 3).
TRIG_ARRIVAL_NEW = {1: 4.471, 2: 8.933, 3: 13.392}
TRIG_ARRIVAL_OLD = {1: 4.599, 2: 9.203, 3: 18.391}
TRIG_CABLE_SWAP = "2026-10-05 12:00"
TRIG_ARRIVAL = dict(TRIG_ARRIVAL_NEW)                   # set per shot by use_trigger_cables()
SCOPE_OFFSET = {1: -87.4679, 2: -87.5049, 3: -87.1380}  # record zero vs trigger edge (CH4 cal)

# THE OUTPUT. Timing is judged on the C225 D-dot, integrated to the output
# voltage, at this percent of each pulse's own peak. Same rule as outEdges in
# ltgs_gui3.m: 5 ns moving mean, pulses are runs above 50% of the largest peak
# that last 30 ns or more, crossings interpolated.
OUTPUT_PROBE = (3, 4)
OUTPUT_LEVEL = 50.0

# (scope, channel): (name, kind, cable one way in ns)
CHANNELS = {
    (1, 1): ("RVM 1",              "rvm",   237.847 / 2),
    (1, 2): ("RVM 2",              "rvm",   238.180 / 2),
    (1, 3): ("Trig monitor",       "spike", 238.271 / 2),
    (1, 4): ("Trig Sync (X22)",    "edge",  1.540),
    (2, 1): ("LTGS2-232 D-dot",    "burst", 238.112 / 2),
    (2, 2): ("LTGS2-007 B-dot",    "burst", 238.066 / 2),
    (2, 3): ("LTGS1-232 D-dot",    "burst", 149.961 / 2),
    (2, 4): ("LTGS1-007 B-dot",    "burst", 152.947 / 2),
    (3, 1): ("L1 Q-switch sync",   "edge",  268.558 / 2),
    (3, 2): ("L2 Q-switch sync",   "edge",  268.926 / 2),
    (3, 3): ("C315 B-dot",         "burst", 150.515 / 2),
    (3, 4): ("C225 D-dot",         "burst", 149.672 / 2),
}

# Trigger generator path, from channel A
TAU_A_TO_DG_SR = 1.455      # channel A to screen room DG535 EXT TRIG
DG_SR_INSERTION = 89.989    # EXT TRIG to rear output A, programmed delay zero
TAU_84FT = 129.300          # output A to the TG-100 trigger input
TG_SYNC_DELAY = 33.3        # TG-100 trigger in to sync out (one shot, 1 July 2026)
TG_TO_MARX_SPIKE = 243.5    # TG-100 trigger in to the Trig monitor spike (same shot)
LINK_TG = 162.377           # TF1 + 30 m fiber + X22 on the Trig Sync path

# Laser path, from channel B
SKEW_A_TO_B = -0.783        # channel B fires this much relative to A at equal delays
LINK_LASER = 166.410        # TF1 + fiber + X22 to the laser DG535
TAU_X22_TO_DGL = 1.556      # X22 to laser DG535 EXT TRIG
DG_LASER_INSERTION = {"A": 86.426, "B": 86.409, "C": 86.417, "D": 86.477}
TAU_DGL_TO_LASER = {"A": 4.523, "B": 4.536, "C": 4.596, "D": 4.534}
LASER_OUTPUT_ROLE = {"A": "L1 flashlamp", "B": "L1 Q-switch",
                     "C": "L2 flashlamp", "D": "L2 Q-switch"}

SCOPE_COLOR = {1: "#0d6e7a", 2: "#7a5a2e", 3: "#5b4b9a"}


def use_trigger_cables(when):
    """Pick the trigger cable set for a shot time. `when` is any text that holds
    a date like 2026-09-24 17:22:33, 2026.09.24 or 20260924_170806."""
    import re
    m = re.search(r"(20\d\d)[-./_]?(\d\d)[-./_]?(\d\d)(?:[ T_]?(\d\d):?(\d\d))?", str(when or ""))
    if not m:
        TRIG_ARRIVAL.update(TRIG_ARRIVAL_NEW)
        return "new (no date found)"
    key = f"{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4) or '00'}:{m.group(5) or '00'}"
    old = key < TRIG_CABLE_SWAP
    TRIG_ARRIVAL.update(TRIG_ARRIVAL_OLD if old else TRIG_ARRIVAL_NEW)
    return "old, before 5 Oct 2026" if old else "new, from 5 Oct 2026"


def record_to_sensor(scope, channel):
    """Constant to SUBTRACT from record time (ns) to get time at the sensor."""
    cable = CHANNELS[(scope, channel)][2]
    return cable - TRIG_ARRIVAL[scope] - SCOPE_OFFSET[scope]


# ----------------------------------------------------------------------------
# Loading
# ----------------------------------------------------------------------------
def load_scope_csv(path):
    """Return t (s) and a dict {channel: volts}. Handles the GUI export."""
    try:
        import pandas as pd
        df = pd.read_csv(path)
        cols = list(df.columns)
        arr = df.to_numpy(dtype=float)
    except ImportError:
        with open(path) as f:
            cols = f.readline().strip().split(",")
        arr = np.loadtxt(path, delimiter=",", skiprows=1)
    t = arr[:, 0]
    chans = {}
    for i, c in enumerate(cols[1:], start=1):
        digits = "".join(ch for ch in c.split("CH")[-1][:2] if ch.isdigit())
        if digits:
            chans[int(digits)] = arr[:, i]
    return t, chans


def read_shot_row(path, shot):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        if str(r.get("shot_number", "")).strip() == str(shot) or \
           str(r.get("session_shot_index", "")).strip() == str(shot):
            return r
    have = [r.get("shot_number") for r in rows]
    sys.exit(f"Shot {shot} is not in {path}. Shots in the file: {have}")


def fnum(row, key, default=0.0):
    try:
        return float(row[key])
    except (KeyError, ValueError, TypeError):
        return default


def laser_dg_delays(row):
    """Resolve A/B/C/D delays to ns after the laser DG535's own T0."""
    raw, ref = {}, {}
    for ch in "ABCD":
        raw[ch] = fnum(row, f"dg535_laser_{ch}_delay_us") * 1000.0
        ref[ch] = (row.get(f"dg535_laser_{ch}_ref") or "T0").strip().upper()
    out = {}

    def resolve(ch, depth=0):
        if ch in out:
            return out[ch]
        if depth > 6:
            sys.exit("The laser DG535 channel references form a loop.")
        base = 0.0 if ref[ch] in ("T0", "T", "") else resolve(ref[ch], depth + 1)
        out[ch] = base + raw[ch]
        return out[ch]

    for ch in "ABCD":
        resolve(ch)
    return out, raw, ref


# ----------------------------------------------------------------------------
# Predictions from the timing map (ns after T0, at the named point)
# ----------------------------------------------------------------------------
def predict(bnc_a_us, bnc_b_us, marx_delay_us, dgl):
    p = {}
    marx = marx_delay_us * 1000.0
    tg_in = TAU_A_TO_DG_SR + DG_SR_INSERTION + marx + TAU_84FT
    p["TG-100 trigger in"] = tg_in
    p["TG-100 sync out"] = tg_in + TG_SYNC_DELAY
    p["Trig Sync at X22 out"] = tg_in + TG_SYNC_DELAY + LINK_TG
    p["HV spike at Marx"] = tg_in + TG_TO_MARX_SPIKE

    t_b = (bnc_b_us - bnc_a_us) * 1000.0 + SKEW_A_TO_B
    dgl_trig = t_b + LINK_LASER + TAU_X22_TO_DGL
    p["BNC 575 CH B"] = t_b
    p["Laser DG535 EXT TRIG"] = dgl_trig
    for ch in "ABCD":
        p[f"{LASER_OUTPUT_ROLE[ch]} trigger at laser"] = (
            dgl_trig + DG_LASER_INSERTION[ch] + dgl[ch] + TAU_DGL_TO_LASER[ch])
    return p


# ----------------------------------------------------------------------------
# Event finders. All work on t in ns (sensor time) and return ns.
# ----------------------------------------------------------------------------
def robust_base(v):
    base = float(np.median(v))
    sig = float(np.median(np.abs(v - base))) * 1.4826
    u = np.unique(v)
    lsb = float(np.min(np.diff(u))) if u.size > 1 else 0.0
    return base, max(sig, lsb / np.sqrt(12.0), 1e-12)


def interp_cross(t, y, i, level):
    """y crosses level between i-1 and i. Linear interpolation."""
    if i <= 0 or y[i] == y[i - 1]:
        return float(t[i])
    return float(t[i - 1] + (level - y[i - 1]) / (y[i] - y[i - 1]) * (t[i] - t[i - 1]))


def smooth(v, n):
    n = max(int(n), 1)
    return v if n == 1 else np.convolve(v, np.ones(n) / n, mode="same")


def find_edge(t, v, pre):
    """Logic edge of either polarity. 50% of the step. pre = baseline mask."""
    base, sig = robust_base(v[pre])
    dev = v - base
    big = np.abs(dev)
    peak = float(big.max())
    if peak < 8 * sig:
        return None
    i0 = int(np.argmax(big >= 0.5 * peak))
    dt = float(t[1] - t[0])
    a, b = i0 + int(5 / dt), i0 + int(50 / dt)
    plateau = float(np.median(dev[a:b])) if b < dev.size else float(dev[i0])
    if abs(plateau) < 4 * sig:
        plateau = float(dev[i0])
    y = dev * np.sign(plateau)
    level = 0.5 * abs(plateau)
    lo = max(i0 - int(20 / dt), 1)
    seg = np.nonzero(y[lo:i0 + 2] >= level)[0]
    i = lo + int(seg[0]) if seg.size else i0
    return {"t": interp_cross(t, y, i, level), "amp": plateau,
            "what": "rising" if plateau > 0 else "falling"}


def find_spike(t, v, pre):
    """Short pulse. Time of the first 50% crossing of its peak."""
    base, sig = robust_base(v[pre])
    dev = v - base
    k = int(np.argmax(np.abs(dev)))
    peak = float(dev[k])
    if abs(peak) < 12 * sig:
        return None
    y = dev * np.sign(peak)
    level = 0.5 * abs(peak)
    i = int(np.argmax(y >= level))
    return {"t": interp_cross(t, y, i, level), "amp": peak, "what": "spike"}


def find_bursts(t, v, pre, frac=0.3, gap_ns=300.0, max_n=3):
    """D-dot and B-dot. First crossing of frac*peak in each separated burst."""
    base, sig = robust_base(v[pre])
    dev = v - base
    big = np.abs(dev)
    peak = float(big.max())
    if peak < 12 * sig:
        return []
    idx = np.nonzero(big >= frac * peak)[0]
    if idx.size == 0:
        return []
    starts = [int(idx[0])]
    for a, b in zip(idx[:-1], idx[1:]):
        if t[b] - t[a] > gap_ns:
            starts.append(int(b))
    out = []
    for i in starts[:max_n]:
        j = min(i + int(40 / (t[1] - t[0])), dev.size - 1)
        k = i + int(np.argmax(big[i:j + 1]))
        out.append({"t": interp_cross(t, big, i, frac * peak),
                    "amp": float(dev[k]), "what": f"{int(frac*100)}% of peak"})
    return out


def movmean(y, n):
    """Centred moving mean with a shrinking window at the ends, like MATLAB."""
    n = max(1, int(n))
    if n == 1:
        return np.asarray(y, float)
    c = np.cumsum(np.insert(np.asarray(y, float), 0, 0.0))
    h = n // 2
    i = np.arange(len(y))
    lo, hi = np.maximum(i - h, 0), np.minimum(i + h + 1, len(y))
    return (c[hi] - c[lo]) / (hi - lo)


def output_trace(t, v, t_first, before=2000.0, after=3500.0):
    """Integrate a D-dot or B-dot around the output pulses. t in ns.

    The baseline is the mean of the raw signal from 2000 to 150 ns before the
    first pulse. Returns (t, integral), same sign as the probe gives."""
    m = (t >= t_first - before) & (t <= t_first + after)
    tt, vv = t[m], v[m]
    if tt.size < 200:
        return None
    pre = tt < t_first - 150.0
    if pre.sum() < 50:
        return None
    dt = float(np.median(np.diff(tt[:1000])))
    return tt, np.cumsum(vv - vv[pre].mean()) * dt


def out_edges(t, y, frac):
    """Edges of the first two output pulses at frac of each pulse's own peak.

    Port of outEdges in ltgs_gui3.m. Returns lead[2], trail[2], amp[2], with
    None where a pulse or an edge was not found. Times in the units of t (ns).
    """
    lead, trail, amp = [None, None], [None, None], [None, None]
    if t.size < 10:
        return lead, trail, amp
    dt = float(np.median(np.diff(t[:1000])))
    ys = movmean(y, 2 * round(5.0 / dt / 2) + 1)
    s = np.sign(ys[int(np.argmax(np.abs(ys)))])
    if s == 0:
        return lead, trail, amp
    ys = s * ys
    b = (ys > 0.5 * ys.max()).astype(int)
    d = np.diff(np.concatenate(([0], b, [0])))
    rs, re = np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1
    keep = (re - rs + 1) * dt >= 30.0
    rs, re = rs[keep], re[keep]
    n_all = ys.size

    def xc(a, c, thr):
        if ys[c] == ys[a]:
            return float(t[c])
        return float(t[a] + (thr - ys[a]) * (t[c] - t[a]) / (ys[c] - ys[a]))

    lo = 0
    for p in range(min(2, rs.size)):
        seg = ys[rs[p]:re[p] + 1]
        ap = float(seg.max())
        thr = frac * ap
        amp[p] = float(s * ap)
        above = rs[p] + np.flatnonzero(seg >= 0.5 * ap)
        i50, i50t = int(above[0]), int(above[-1])
        if frac <= 0.5:
            w = np.flatnonzero(ys[lo:i50 + 1] < thr)
            if w.size:
                a = lo + int(w[-1])
                lead[p] = xc(a, a + 1, thr)
        else:
            w = np.flatnonzero(ys[i50:re[p] + 1] >= thr)
            if w.size and i50 + int(w[0]) > 0:
                c = i50 + int(w[0])
                lead[p] = xc(c - 1, c, thr)
        hi = int(rs[p + 1]) if p + 1 < rs.size else n_all - 1
        if frac >= 0.5:
            w = np.flatnonzero(ys[rs[p]:i50t + 1] >= thr)
            if w.size and rs[p] + int(w[-1]) < n_all - 1:
                a = int(rs[p]) + int(w[-1])
                trail[p] = xc(a, a + 1, thr)
        else:
            w = np.flatnonzero(ys[i50t:hi + 1] < thr)
            if w.size and i50t + int(w[0]) > 0:
                c = i50t + int(w[0])
                trail[p] = xc(c - 1, c, thr)
        lo = int(re[p])
    return lead, trail, amp


def find_rvm(t, v, pre):
    """Slow charge then fast collapse. Onset, peak, and half-way collapse."""
    dt = float(t[1] - t[0])
    s = smooth(v, 10 / dt)
    base, _ = robust_base(v[pre])
    sig = float(np.std(s[pre]))
    dev = s - base
    k = int(np.argmax(np.abs(dev)))
    peak = float(dev[k])
    if abs(peak) < 20 * sig:
        return None
    y = dev * np.sign(peak)
    level = max(6 * sig, 0.03 * abs(peak))
    hold = int(20 / dt)
    above = y >= level
    run = np.convolve(above.astype(int), np.ones(hold, dtype=int), mode="valid")
    cand = np.nonzero(run == hold)[0]
    onset = interp_cross(t, y, int(cand[0]), level) if cand.size else None
    after = np.nonzero(y[k:] <= 0.5 * abs(peak))[0]
    collapse = None
    if after.size:
        i = k + int(after[0])
        collapse = interp_cross(t, -y, i, -0.5 * abs(peak))
    return {"onset": onset, "t_peak": float(t[k]), "peak": peak, "collapse": collapse}


# ----------------------------------------------------------------------------
# Plot helpers
# ----------------------------------------------------------------------------
def crop(t, v, lo, hi, max_pts=40000):
    m = (t >= lo) & (t <= hi)
    tt, vv = t[m], v[m]
    if tt.size > max_pts:
        step = int(np.ceil(tt.size / max_pts))
        tt, vv = tt[::step], vv[::step]
    return tt, vv


def draw_rows(fig_title, rows, lo, hi, x0, x_scale, x_label, pred_lines, marks,
              out_path, show):
    """rows: list of (scope, ch, t_ns, v). x shown as (t - x0) / x_scale."""
    import matplotlib.pyplot as plt
    n = len(rows)
    fig, axes = plt.subplots(n, 1, figsize=(13, 1.35 * n + 1.6), sharex=True)
    if n == 1:
        axes = [axes]
    for ax, (scope, ch, t, v) in zip(axes, rows):
        name = CHANNELS[(scope, ch)][0]
        tt, vv = crop(t, v, lo, hi)
        ax.plot((tt - x0) / x_scale, vv, lw=0.9, color=SCOPE_COLOR[scope])
        ax.set_ylabel(f"S{scope} CH{ch}\n{name}", rotation=0, ha="right",
                      va="center", fontsize=8.5)
        ax.grid(True, alpha=0.25)
        ax.tick_params(labelsize=8)
        for label, tp in pred_lines:
            if lo <= tp <= hi:
                ax.axvline((tp - x0) / x_scale, color="0.35", ls="--", lw=0.8)
        shown_marks = [m for m in marks.get((scope, ch), []) if lo <= m["t"] <= hi]
        for j, m in enumerate(shown_marks):
            if lo <= m["t"] <= hi:
                ax.axvline((m["t"] - x0) / x_scale, color="#c0392b", lw=1.0)
                ax.annotate(m["label"], ((m["t"] - x0) / x_scale, 0.97 - 0.2 * (j % 3)),
                            xycoords=("data", "axes fraction"), fontsize=7.5,
                            color="#c0392b", va="top", ha="left",
                            xytext=(3, 0), textcoords="offset points")
    top = axes[0]
    shown = [(lab, tp) for lab, tp in pred_lines if lo <= tp <= hi]
    for k, (label, tp) in enumerate(shown):
        top.annotate(label, ((tp - x0) / x_scale, 1.0),
                     xycoords=("data", "axes fraction"), fontsize=7.5,
                     color="0.25", ha="left", va="bottom",
                     xytext=(2, 3 + 11 * (k % 4)), textcoords="offset points")
    axes[-1].set_xlabel(x_label)
    axes[-1].set_xlim((lo - x0) / x_scale, (hi - x0) / x_scale)
    fig.suptitle(fig_title + "\n dashed grey: timing map prediction    "
                 "red: found in the data", fontsize=10, y=0.995)
    fig.tight_layout()
    fig.subplots_adjust(top=1.0 - 1.25 / fig.get_figheight())
    if out_path:
        fig.savefig(out_path, dpi=120)
        print(f"  wrote {out_path}")
    if not show:
        plt.close(fig)


# ----------------------------------------------------------------------------
# The main figure: one page, three questions
# ----------------------------------------------------------------------------
C_TRIG, C_SYNC, C_BDOT, C_DDOT = "#222222", "#0072B2", "#D55E00", "#009E73"
C_MAP = "#7a7a7a"
C_OUT = "#8E4A9E"


def _norm(t, v, lo, hi, base_hi):
    """Crop to [lo, hi] and scale so the largest swing from baseline is 1."""
    tt, vv = crop(t, v, lo, hi)
    if tt.size < 10:
        return tt, vv
    pre = tt < base_hi
    base = float(np.median(vv[pre])) if pre.sum() > 20 else float(np.median(vv[:max(tt.size // 10, 5)]))
    dev = vv - base
    amp = float(np.max(np.abs(dev))) or 1.0
    return tt, dev / amp


def pick_switch(found, scope_ch, t_sync):
    """The burst on an LTGS channel that follows this laser's sync edge."""
    if t_sync is None:
        return None
    cands = [found[(scope_ch[0], scope_ch[1], k)] for k in ("burst1", "burst2", "burst3")
             if (scope_ch[0], scope_ch[1], k) in found]
    cands = [c for c in cands if -50.0 < c - t_sync < 600.0]
    return min(cands) if cands else None


def _zoom_panel(ax, x0, span, traces, title, xlabel, slots=3, headroom=3.6, lift=0.0):
    """traces: list of (label, color, t_ns, v). Stacked slots, own scale.
    lift raises every slot, to keep a downward pulse clear of the bottom labels."""
    lo, hi = x0 + span[0], x0 + span[1]
    step = 2.6
    for i, (label, color, t, v) in enumerate(traces):
        off = (slots - 1 - i) * step + lift
        tt, yy = _norm(t, v, lo, hi, x0 - 10.0)
        ax.axhline(off, color="0.85", lw=0.8, zorder=0)
        ax.plot(tt - x0, yy + off, color=color, lw=1.6)
        ax.text(span[0] + 0.012 * (span[1] - span[0]), off + 0.5, label, color=color,
                fontsize=10.5, fontweight="bold", va="bottom")
    ax.set_xlim(*span)
    ax.set_ylim(-1.5, (slots - 1) * step + headroom + lift)
    ax.set_yticks([])
    for sp in ("left", "right", "top"):
        ax.spines[sp].set_visible(False)
    ax.set_xlabel(xlabel, fontsize=10.5)
    ax.tick_params(labelsize=9.5)
    ax.set_title(title, fontsize=12.5, fontweight="bold", loc="left", pad=10)
    return (slots - 1) * step + 1.45 + lift      # y where the ribbons start


def _ribbon(ax, a, b, y, text, color, measured=True):
    from matplotlib.patches import Rectangle
    h = 1.05
    ax.add_patch(Rectangle((a, y), b - a, h, facecolor=color, alpha=0.22 if measured else 0.12,
                           edgecolor=color, lw=1.2, ls="-" if measured else "--"))
    xl, xr = ax.get_xlim()
    wide = (b - a) / (xr - xl) > 0.17
    if wide:
        ax.text((a + b) / 2, y + h / 2, text, ha="center", va="center", fontsize=9.5,
                color="black")
    else:
        ax.text(a, y + h + 0.12, text.replace("\n", "  "), ha="left", va="bottom",
                fontsize=9.5, color="black")


def _event(ax, x, y_top, color, text, dashed=False, side="center"):
    ax.plot([x, x], [-1.5, y_top], color=color, lw=1.3, ls="--" if dashed else "-", zorder=1)
    xl, xr = ax.get_xlim()
    pad = 0.008 * (xr - xl)
    xt = {"center": x, "left": x - pad, "right": x + pad}[side]
    ha = {"center": "center", "left": "right", "right": "left"}[side]
    ax.text(xt, -1.42, text, color=color, fontsize=9.5, ha=ha, va="bottom",
            bbox=dict(facecolor="white", edgecolor="none", pad=1.2))


def draw_summary(title, subtitle, data, pred, found, dgl, out_path, show):
    import matplotlib.pyplot as plt

    tg_in = pred["TG-100 trigger in"]
    ts = found.get((1, 4, "edge"))
    q = {1: found.get((3, 1, "edge")), 2: found.get((3, 2, "edge"))}
    trig = {1: pred["L1 Q-switch trigger at laser"], 2: pred["L2 Q-switch trigger at laser"]}
    ltgs_b = {1: (2, 4), 2: (2, 2)}
    ltgs_d = {1: (2, 3), 2: (2, 1)}
    sw = {n: pick_switch(found, ltgs_b[n], q[n]) for n in (1, 2)}

    lead = {n: found.get(("out", n, "lead")) for n in (1, 2)}
    trail = {n: found.get(("out", n, "trail")) for n in (1, 2)}

    fig = plt.figure(figsize=(15, 10.6))
    gs_top = fig.add_gridspec(1, 1, left=0.165, right=0.985, top=0.885, bottom=0.675)
    gs = fig.add_gridspec(1, 3, wspace=0.10, left=0.035, right=0.985, top=0.565,
                          bottom=0.065)
    fig.suptitle(title, fontsize=15, fontweight="bold", x=0.035, ha="left", y=0.98)
    fig.text(0.035, 0.94, subtitle, fontsize=11, color="0.25", ha="left")

    # ---------------- top strip: the whole shot ----------------
    ax = fig.add_subplot(gs_top[0, 0])
    ends = [v for v in (sw[2], sw[1], q[2], q[1], trig[2], trail[2]) if v is not None]
    lo, hi = tg_in - 250.0, max(ends) + 450.0
    rows = [("Trig Sync", C_TRIG, [(1, 4)]),
            ("Q-switch sync, L1 and L2", C_SYNC, [(3, 1), (3, 2)]),
            ("LTGS B-dot, 1 and 2", C_BDOT, [(2, 4), (2, 2)]),
            (f"C225 output", C_OUT, [("out",)])]
    top_y = (len(rows) - 1) * 2.4
    for i, (label, color, chans) in enumerate(rows):
        off = (len(rows) - 1 - i) * 2.4
        ax.axhline(off, color="0.88", lw=0.8, zorder=0)
        for key in chans:
            if key in data:
                tt, yy = _norm(*data[key], lo, hi, tg_in - 50.0)
                ax.plot(tt / 1000.0, yy + off, color=color, lw=1.1)
        ax.text(-0.012, off, label, color=color, fontsize=10.5, fontweight="bold",
                va="center", ha="right", transform=ax.get_yaxis_transform())
    windows = [("A", tg_in), ("B", trig[1]), ("C", trig[2])]
    for name, x0 in windows:
        ax.axvspan((x0 - 50.0) / 1000.0, (x0 + 450.0) / 1000.0, color="0.5", alpha=0.10, lw=0)
        ax.text((x0 - 50.0) / 1000.0, top_y + 2.25, f" {name}", fontsize=13, fontweight="bold",
                va="top", ha="left", color="0.25")

    def span_arrow(a, b, y, text):
        if a is None or b is None:
            return
        ax.annotate("", (b / 1000.0, y), (a / 1000.0, y),
                    arrowprops=dict(arrowstyle="<->", color="0.2", lw=1.1))
        ax.text((a + b) / 2000.0, y + 0.12, text, ha="center", va="bottom", fontsize=9.5,
                bbox=dict(facecolor="white", edgecolor="none", pad=1.0))

    span_arrow(q[1], q[2], top_y - 2.4 - 1.25, f"Q-switch spacing {q[2] - q[1]:.1f} ns  "
               f"(commanded {dgl['D'] - dgl['B']:.0f})" if q[1] and q[2] else "")
    span_arrow(sw[1], sw[2], top_y - 4.8 - 1.25, f"switch spacing {sw[2] - sw[1]:.1f} ns"
               if sw[1] and sw[2] else "")
    span_arrow(ts, q[1], top_y - 1.25, f"Trig Sync to laser 1 sync {(q[1] - ts) / 1000.0:.3f} us"
               if ts and q[1] else "")
    span_arrow(trail[1], lead[2], -1.35,
               f"output gap at {OUTPUT_LEVEL:g}%  {lead[2] - trail[1]:.1f} ns"
               if trail[1] and lead[2] else "")
    for n in (1, 2):
        for x in (lead[n], trail[n]):
            if x is not None:
                ax.plot([x / 1000.0] * 2, [-1.15, 0.25], color=C_OUT, lw=1.0)
    ax.set_xlim(lo / 1000.0, hi / 1000.0)
    ax.set_ylim(-1.9, top_y + 2.4)
    ax.set_yticks([])
    for sp in ("left", "right", "top"):
        ax.spines[sp].set_visible(False)
    ax.set_xlabel("time after T0 (us), cable delays removed", fontsize=10.5)
    ax.tick_params(labelsize=9.5)
    fig.text(0.035, 0.903, "The whole shot", fontsize=12.5, fontweight="bold", ha="left")

    # ---------------- A: trigger generator path ----------------
    span = (-50.0, 450.0)
    ax = fig.add_subplot(gs[0, 0])
    tr = [("Trig Sync", C_TRIG) + data[(1, 4)]] if (1, 4) in data else []
    y_r = _zoom_panel(ax, tg_in, span, tr, "A   Does the trigger path add up?",
                      "ns after the trigger reaches the TG-100")
    _ribbon(ax, 0.0, TG_SYNC_DELAY, y_r, f"TG-100  {TG_SYNC_DELAY:.0f} ns", C_MAP, measured=False)
    _ribbon(ax, TG_SYNC_DELAY, TG_SYNC_DELAY + LINK_TG, y_r,
            f"TF1 + fiber + X22\n{LINK_TG:.1f} ns", C_MAP, measured=False)
    _event(ax, 0.0, y_r, C_MAP, "trigger in\n(map)", dashed=True)
    p_ts = pred["Trig Sync at X22 out"] - tg_in
    if ts is not None:
        _event(ax, ts - tg_in, y_r, C_TRIG, f"edge found\n{ts - tg_in:.1f} ns", side="right")
        diff = ts - pred["Trig Sync at X22 out"]
        ok = abs(diff) < 2.0
        ax.text(0.5, 0.36, f"map predicts   {p_ts:7.2f} ns\nmeasured       {ts - tg_in:7.2f} ns\n"
                           f"difference     {diff:+7.2f} ns",
                transform=ax.transAxes, fontsize=11.5, family="monospace", va="center",
                ha="center", bbox=dict(facecolor="#eef7ee" if ok else "#fdeeee",
                                       edgecolor="#2e7d32" if ok else "#c62828", pad=8))
        ax.text(0.5, 0.17, "The edge lands where the map says." if ok else
                "The edge is NOT where the map says. Check the delays.",
                transform=ax.transAxes, fontsize=10.5, ha="center",
                color="#2e7d32" if ok else "#c62828",
                bbox=dict(facecolor="white", edgecolor="none", pad=2.0))
    else:
        ax.text(0.5, 0.3, "No Trig Sync edge found", transform=ax.transAxes, ha="center",
                fontsize=12, color="#c62828")

    # ---------------- B and C: each laser and its switch ----------------
    for col, n, letter in ((1, 1, "B"), (2, 2, "C")):
        ax = fig.add_subplot(gs[0, col])
        tr = []
        for label, color, key in (("Q-switch sync", C_SYNC, (3, n)),
                                  (f"LTGS{n} B-dot", C_BDOT, ltgs_b[n]),
                                  (f"LTGS{n} D-dot", C_DDOT, ltgs_d[n]),
                                  ("C225 output", C_OUT, ("out",))):
            if key in data:
                tr.append((label, color) + data[key])
        y_r = _zoom_panel(ax, trig[n], span, tr,
                          f"{letter}   Laser {n} to switch {n} to the output",
                          f"ns after the Q-switch trigger reaches laser {n}",
                          slots=4, headroom=5.7, lift=1.25)
        _event(ax, 0.0, y_r, C_MAP, "trigger in\n(map)", dashed=True)
        if q[n] is not None:
            a = q[n] - trig[n]
            _ribbon(ax, 0.0, a, y_r, f"inside laser {n}\n{a:.1f} ns", C_SYNC)
            _event(ax, a, y_r, C_SYNC, f"sync out\n{a:.1f} ns", side="left")
            if lead[n] is not None:
                c = lead[n] - trig[n]
                _ribbon(ax, a, c, y_r + 2.0, f"sync to output\n{c - a:.1f} ns", C_OUT)
                ax.plot([c, c], [-1.5, y_r + 2.0], color=C_OUT, lw=1.3, zorder=1)
                right = c < 250.0
                ax.text(c + (6.0 if right else -6.0), 1.25 + 0.22,
                        f"output {OUTPUT_LEVEL:g}%   {c:.1f} ns",
                        color=C_OUT, fontsize=9.5, ha="left" if right else "right", va="bottom",
                        bbox=dict(facecolor="white", edgecolor="none", pad=1.2))
            if sw[n] is not None:
                b = sw[n] - trig[n]
                _ribbon(ax, a, b, y_r, f"sync to switch\n{b - a:.1f} ns", C_BDOT)
                _event(ax, b, y_r, C_BDOT, f"switch closes\n{b:.1f} ns", side="right")
            else:
                ax.text(0.6, 0.3, "No switch signal found", transform=ax.transAxes,
                        ha="center", fontsize=12, color="#c62828")
        else:
            ax.text(0.5, 0.5, "No Q-switch sync edge found", transform=ax.transAxes,
                    ha="center", fontsize=12, color="#c62828")

    fig.text(0.985, 0.012, "Dashed grey = timing map.  Solid = found in this shot.  "
             "Each trace is scaled to its own peak.  C225 output = integrated D-dot, "
             f"edges at {OUTPUT_LEVEL:g}% of each pulse's own peak.",
             fontsize=9, color="0.4", ha="right")
    if out_path:
        fig.savefig(out_path, dpi=130)
        print(f"  wrote {out_path}")
    if not show:
        plt.close(fig)


# ----------------------------------------------------------------------------
def build_parser():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shot-log", help="shot_log_*.csv written by the GUI")
    ap.add_argument("--shot", help="shot_number or session_shot_index in that log")
    ap.add_argument("--dir", help="folder with the rigol CSVs (default: next to the log)")
    for k in (1, 2, 3):
        ap.add_argument(f"--rigol{k}", help=f"scope {k} CSV, overrides the log")
    ap.add_argument("--marx-delay-us", type=float, default=180.0,
                    help="screen room DG535 channel A delay, us (not in the log)")
    ap.add_argument("--bnc-a-us", type=float, help="override BNC 575 A delay")
    ap.add_argument("--bnc-b-us", type=float, help="override BNC 575 B delay")
    ap.add_argument("--qsw1-us", type=float, help="laser DG535 B after A, us")
    ap.add_argument("--qsw2-us", type=float, help="laser DG535 D after C, us")
    ap.add_argument("--out", help="output folder for the PNG files")
    ap.add_argument("--show", action="store_true", help="open the figures")
    ap.add_argument("--raw", action="store_true",
                    help="plot scope record time, no corrections")
    ap.add_argument("--no-detect", action="store_true")
    ap.add_argument("--detail", action="store_true",
                    help="also save the older figures with all 12 channels")
    ap.add_argument("--zoom", nargs=2, type=float, metavar=("LO_US", "HI_US"),
                    help="extra figure of every channel between these times, "
                         "us after T0")
    ap.add_argument("--all", action="store_true",
                    help="run every shot in the shot log and print one table. "
                         "No figures unless --figures is given")
    ap.add_argument("--figures", action="store_true",
                    help="with --all, also save the figures for every shot")
    return ap


def run_shot(a, row, make_figures=True):
    """Analyse one shot. Returns {description: value in ns} for the summary."""
    summ = {}
    # ---- settings ---------------------------------------------------------
    bnc_a = a.bnc_a_us if a.bnc_a_us is not None else fnum(row, "bnc575_A_delay_us")
    bnc_b = a.bnc_b_us if a.bnc_b_us is not None else fnum(row, "bnc575_B_delay_us")
    if row:
        dgl, dgl_raw, dgl_ref = laser_dg_delays(row)
    else:
        dgl = {"A": 0.0, "B": 0.0, "C": 0.0, "D": 0.0}
        dgl_raw, dgl_ref = dict(dgl), {c: "T0" for c in "ABCD"}
    if a.qsw1_us is not None:
        dgl["B"] = dgl["A"] + a.qsw1_us * 1000.0
    if a.qsw2_us is not None:
        dgl["D"] = dgl["C"] + a.qsw2_us * 1000.0

    log_dir = os.path.dirname(os.path.abspath(a.shot_log)) if a.shot_log else "."
    # Where the rigol files may be: next to the log, or in the session folder
    # the row names. That second case covers shot_log_master.csv.
    sess = (row.get("session_dir") or "").replace("\\", "/").strip("/")
    places = [a.dir] if a.dir else [log_dir]
    if sess and not a.dir:
        parts = sess.split("/")
        places += [os.path.join(log_dir, *parts), os.path.join(log_dir, "..", *parts),
                   os.path.join(log_dir, *parts[1:]), os.path.join(os.getcwd(), *parts)]
    files = {}
    for k in (1, 2, 3):
        name = row.get(f"rigol{k}_file")
        cands = [getattr(a, f"rigol{k}")] if getattr(a, f"rigol{k}") else \
                [os.path.join(d, name) for d in places] if name else []
        hit = next((os.path.normpath(c) for c in cands if c and os.path.exists(c)), None)
        if hit:
            files[k] = hit
        else:
            print(f"  scope {k}: file not found ({name}). Skipping that scope.")
    base_dir = os.path.dirname(next(iter(files.values()))) if files else log_dir
    if not files:
        raise FileNotFoundError("No scope files found. Use --dir or --rigol1/2/3.")

    when = (row.get("datetime") if row else None) or \
        " ".join(os.path.basename(f) for f in files.values())
    cable_set = use_trigger_cables(when)

    tag = f"shot_{int(float(row['shot_number'])):04d}" if row.get("shot_number") else "shot"
    out_dir = a.out or base_dir
    os.makedirs(out_dir, exist_ok=True)

    print("SETTINGS FOR THIS SHOT")
    print("=" * 74)
    if row:
        print(f"  shot {row.get('shot_number')}  ({row.get('datetime')})   "
              f"pressure {row.get('pressure_psi')} psi   charge "
              f"{row.get('wj1_charge_kv')} / {row.get('wj2_charge_kv')} kV")
    print(f"  trigger cables {cable_set}:  scope 1 {TRIG_ARRIVAL[1]:.3f}  "
          f"scope 2 {TRIG_ARRIVAL[2]:.3f}  scope 3 {TRIG_ARRIVAL[3]:.3f} ns")
    print(f"  BNC 575        A delay {bnc_a:.6f} us    B delay {bnc_b:.6f} us")
    print(f"  screen room DG535 channel A delay   {a.marx_delay_us:.3f} us   "
          f"(option, not from the log)")
    for ch in "ABCD":
        print(f"  laser DG535 {ch}  {LASER_OUTPUT_ROLE[ch]:<13} = {dgl_ref[ch]:>2} + "
              f"{dgl_raw[ch]/1000:.6f} us   -> {dgl[ch]/1000:.6f} us after its T0")

    pred = predict(bnc_a, bnc_b, a.marx_delay_us, dgl)

    # ---- load and shift ---------------------------------------------------
    data = {}      # (scope, ch) -> (t_ns sensor time, v)
    for k, p in files.items():
        print(f"\n  loading scope {k}: {os.path.basename(p)}")
        t, chans = load_scope_csv(p)
        print(f"    record {t[0]*1e6:.3f} to {t[-1]*1e6:.3f} us, "
              f"{(t[1]-t[0])*1e12:.0f} ps per sample, channels {sorted(chans)}")
        for ch, v in chans.items():
            if (k, ch) not in CHANNELS:
                continue
            shift = 0.0 if a.raw else record_to_sensor(k, ch)
            data[(k, ch)] = (t * 1e9 - shift, v)

    # ---- find events ------------------------------------------------------
    tg_in = pred["TG-100 trigger in"]
    win_lo, win_hi = tg_in - 2000.0, tg_in + 12000.0
    marks, found = {}, {}
    if not a.no_detect and not a.raw:
        for (k, ch), (t, v) in sorted(data.items()):
            name, kind, _ = CHANNELS[(k, ch)]
            m = (t >= win_lo) & (t <= win_hi)
            tt, vv = t[m], v[m]
            if tt.size < 100:
                continue
            pre = tt < (tg_in - 200.0)
            if pre.sum() < 50:
                pre = np.arange(tt.size) < tt.size // 10
            res = []
            if kind == "edge":
                e = find_edge(tt, vv, pre)
                if e:
                    res = [{"t": e["t"], "label": f"{e['what']} edge", "key": "edge"}]
            elif kind == "spike":
                e = find_spike(tt, vv, pre)
                if e:
                    res = [{"t": e["t"], "label": "spike", "key": "spike"}]
            elif kind == "burst":
                for n, e in enumerate(find_bursts(tt, vv, pre), start=1):
                    res.append({"t": e["t"], "label": f"burst {n}", "key": f"burst{n}"})
            elif kind == "rvm":
                e = find_rvm(tt, vv, pre)
                if e:
                    if e["onset"] is not None:
                        res.append({"t": e["onset"], "label": "starts", "key": "onset"})
                    res.append({"t": e["t_peak"], "key": "peak",
                                "label": f"peak {e['peak']/1e3:.0f} kV"})
                    if e["collapse"] is not None:
                        res.append({"t": e["collapse"], "label": "collapse 50%",
                                    "key": "collapse"})
            marks[(k, ch)] = res
            for r in res:
                found[(k, ch, r["key"])] = r["t"]

    # ---- the output pulses at C225 ------------------------------------------
    outp = None
    first = found.get(OUTPUT_PROBE + ("burst1",))
    if first is not None and OUTPUT_PROBE in data:
        tr = output_trace(data[OUTPUT_PROBE][0], data[OUTPUT_PROBE][1], first)
        if tr is not None:
            lead, trail, amp = out_edges(tr[0], tr[1], OUTPUT_LEVEL / 100.0)
            outp = {"t": tr[0], "y": tr[1], "lead": lead, "trail": trail, "amp": amp}
            data[("out",)] = tr
            for p in (0, 1):
                if lead[p] is not None:
                    found[("out", p + 1, "lead")] = lead[p]
                if trail[p] is not None:
                    found[("out", p + 1, "trail")] = trail[p]

    # ---- report -----------------------------------------------------------
    us = lambda x: f"{x/1000:12.4f} us"
    print("\n\nTIMING MAP PREDICTIONS, after T0")
    print("=" * 74)
    for name, tp in sorted(pred.items(), key=lambda kv: kv[1]):
        print(f"  {name:<34}{us(tp)}")

    if found:
        print("\n\nEVENTS FOUND IN THE DATA, at the sensor, after T0")
        print("=" * 74)
        for (k, ch), res in sorted(marks.items()):
            for r in res:
                print(f"  S{k} CH{ch} {CHANNELS[(k, ch)][0]:<18} {r['label']:<16}{us(r['t'])}")

        if outp is not None:
            for p in (0, 1):
                for key, word in (("lead", "starts"), ("trail", "ends")):
                    if outp[key][p] is not None:
                        print(f"  C225 output, {OUTPUT_LEVEL:g}%      "
                              f"{'pulse ' + str(p + 1) + ' ' + word:<16}{us(outp[key][p])}")

        print("\n\nDOES IT ADD UP")
        print("=" * 74)

        def line(text, value, unit="ns"):
            summ[text.strip()] = value
            print(f"  {text:<52}{value:10.2f} {unit}")

        ts = found.get((1, 4, "edge"))
        if ts is not None:
            line("Trig Sync: measured - predicted", ts - pred["Trig Sync at X22 out"])
            line("  implied TG-100 sync delay",
                 ts - (pred["Trig Sync at X22 out"] - TG_SYNC_DELAY))
        sp = found.get((1, 3, "spike"))
        if sp is not None:
            line("Trig monitor spike after TG-100 trigger in", sp - tg_in)
            if ts is not None:
                line("Trig monitor spike after sync output",
                     sp - (ts - LINK_TG))
        else:
            print("  Trig monitor: no spike found on scope 1 CH3")
        for rv in (1, 2):
            on = found.get((1, rv, "onset"))
            if on is not None:
                line(f"RVM {rv} starts, after TG-100 trigger in", on - tg_in)
        for n, sync_ch, out, ltgs in ((1, 1, "B", (2, 4)), (2, 2, "D", (2, 2))):
            q = found.get((3, sync_ch, "edge"))
            trig = pred[f"L{n} Q-switch trigger at laser"]
            if q is None:
                print(f"  Laser {n}: no Q-switch sync edge found")
                continue
            line(f"Laser {n}: Q-switch sync after its trigger arrives", q - trig)
            cands = [found[(ltgs[0], ltgs[1], key)] for key in ("burst1", "burst2", "burst3")
                     if (ltgs[0], ltgs[1], key) in found]
            sw = min((c for c in cands if c > q - 50), default=None, key=lambda c: abs(c - q))
            if sw is not None:
                line(f"Laser {n}: LTGS{n} B-dot after the Q-switch sync", sw - q)
            col = found.get((1, n, "collapse"))
            if col is not None:
                line(f"Laser {n}: RVM {n} half collapse after the Q-switch sync", col - q)
        q1, q2 = found.get((3, 1, "edge")), found.get((3, 2, "edge"))
        if q1 is not None and q2 is not None:
            line("Q-switch sync spacing, laser 2 - laser 1", q2 - q1)
            line("  commanded spacing", dgl["D"] - dgl["B"])
        c1, c2 = found.get((1, 1, "collapse")), found.get((1, 2, "collapse"))
        if c1 is not None and c2 is not None:
            line("RVM collapse spacing, 2 - 1", c2 - c1)

        if outp is not None:
            L = f"{OUTPUT_LEVEL:g}%"
            print(f"\n  OUTPUT AT C225, {L} of each pulse's own peak")
            l1, l2 = outp["lead"]
            f1, f2 = outp["trail"]
            if l1 is not None and q1 is not None:
                line("Output: pulse 1 start after the laser 1 sync", l1 - q1)
            if l2 is not None and q2 is not None:
                line("Output: pulse 2 start after the laser 2 sync", l2 - q2)
            if l1 is not None and f1 is not None:
                line("Output: pulse 1 width", f1 - l1)
            if l2 is not None and f2 is not None:
                line("Output: pulse 2 width", f2 - l2)
            if l1 is not None and l2 is not None:
                line("Output: start to start", l2 - l1)
            if f1 is not None and l2 is not None:
                line("Output: gap, pulse 1 end to pulse 2 start", l2 - f1)
                line("Output: commanded spacing minus gap", (dgl["D"] - dgl["B"]) - (l2 - f1))

    for (k, ch, key), tv in found.items():
        if (k, ch) in ((1, 1), (1, 2)) and key == "peak":
            m = [r for r in marks[(k, ch)] if r["key"] == "peak"]
            if m:
                summ[f"RVM {ch} peak (kV)"] = float(m[0]["label"].split()[1])
    if not make_figures:
        return summ

    # ---- figures ----------------------------------------------------------
    order = [(1, 4), (1, 3), (1, 1), (1, 2), (3, 1), (2, 4), (2, 3), (3, 2),
             (2, 2), (2, 1), (3, 4), (3, 3)]
    rows = [(k, ch) + data[(k, ch)] for (k, ch) in order if (k, ch) in data]
    pl = sorted(pred.items(), key=lambda kv: kv[1])
    title = f"{tag}" + (f"  {row.get('datetime')}" if row else "")
    print()

    if not a.raw:
        head = (f"Shot {row.get('shot_number')}   {str(row.get('datetime', ''))[:19]}"
                if row else "Shot timing")
        bits = []
        if row:
            bits.append(f"{row.get('pressure_psi')} psi, charge {row.get('wj1_charge_kv')} kV")
        bits.append(f"BNC 575 A {bnc_a:g} us, B {bnc_b:g} us")
        bits.append(f"Q-switch 1 at {dgl['B'] / 1000:g} us, Q-switch 2 at {dgl['D'] / 1000:g} us "
                    f"after the flashlamps")
        bits.append(f"TG-100 delay {a.marx_delay_us:g} us")
        draw_summary(head, "     ".join(bits), data, pred, found, dgl,
                     os.path.join(out_dir, f"{tag}_timing.png"), a.show)
    if not (a.detail or a.raw or a.zoom):
        return summ

    if a.raw:
        t_all = np.concatenate([r[2][[0, -1]] for r in rows])
        draw_rows(title + "  RAW record time", rows, t_all.min(), t_all.max(), 0.0, 1000.0,
                  "scope record time (us)", [], {}, os.path.join(out_dir, f"{tag}_raw.png"),
                  a.show)
    elif a.detail:
        last = max(found.values()) if found else tg_in + 6000.0
        draw_rows(title + "  overview", rows, tg_in - 500.0, last + 800.0, 0.0, 1000.0,
                  "time at the sensor, after T0 (us)", pl, marks,
                  os.path.join(out_dir, f"{tag}_timing_overview.png"), a.show)

        trig_rows = [r for r in rows if (r[0], r[1]) in ((1, 4), (1, 3), (1, 1), (1, 2))]
        draw_rows(title + "  trigger generator region", trig_rows, tg_in - 100.0,
                  tg_in + 900.0, tg_in, 1.0, "ns after the TG-100 trigger input (map)",
                  pl, marks, os.path.join(out_dir, f"{tag}_timing_trigger.png"), a.show)

        for n, sync_ch, keep in ((1, 1, ((3, 1), (2, 4), (2, 3), (1, 1), (3, 4), (3, 3))),
                                 (2, 2, ((3, 2), (2, 2), (2, 1), (1, 2), (3, 4), (3, 3)))):
            trig = pred[f"L{n} Q-switch trigger at laser"]
            sw_rows = [r for r in rows if (r[0], r[1]) in keep]
            sw_rows.sort(key=lambda r: keep.index((r[0], r[1])))
            draw_rows(title + f"  switch {n} region", sw_rows, trig - 100.0, trig + 700.0,
                      trig, 1.0, f"ns after the laser {n} Q-switch trigger arrives (map)",
                      pl, marks, os.path.join(out_dir, f"{tag}_timing_switch{n}.png"),
                      a.show)

    if a.zoom and not a.raw:
        zlo, zhi = a.zoom[0] * 1000.0, a.zoom[1] * 1000.0
        draw_rows(title + f"  zoom {a.zoom[0]:g} to {a.zoom[1]:g} us", rows, zlo, zhi,
                  zlo, 1.0, f"ns after {a.zoom[0]:g} us on the T0 axis", pl, marks,
                  os.path.join(out_dir, f"{tag}_timing_zoom.png"), a.show)

    return summ


def apply_run_button_defaults(a):
    here = os.path.dirname(os.path.abspath(__file__))
    tried = []
    for base in (here, os.getcwd(), os.path.join(os.getcwd(), "logs")):
        p = os.path.normpath(os.path.join(base, DEFAULT_SHOT_LOG))
        tried.append(p)
        if os.path.exists(p):
            a.shot_log = p
            break
    else:
        sys.exit("No arguments given, and the default shot log was not found.\n"
                 "Looked for:\n  " + "\n  ".join(tried) + "\n"
                 "Edit DEFAULT_SHOT_LOG at the top of this file, or pass "
                 "--shot-log and --shot.")
    if str(DEFAULT_SHOT).lower() == "all":
        a.all = True
    else:
        a.shot = str(DEFAULT_SHOT)
        a.show = bool(DEFAULT_SHOW)
    print("No arguments given. Using the defaults at the top of this file:")
    print(f"  shot log  {a.shot_log}")
    print(f"  shot      {DEFAULT_SHOT}\n")


def parse_shots(spec):
    """'43-46' or '43,45,46' -> set of shot numbers. A single number or
    anything else returns None, which means the one-shot path."""
    spec = str(spec or "").replace(" ", "")
    if not spec or not ("-" in spec or "," in spec):
        return None
    want = set()
    try:
        for part in spec.split(","):
            if "-" in part:
                lo, hi = part.split("-", 1)
                want.update(range(int(lo), int(hi) + 1))
            elif part:
                want.add(int(part))
    except ValueError:
        return None
    return want or None


def resolve_log(path):
    """Find the shot log. Tries the path as given, then next to this script,
    then any folder below this script that holds a file of that name."""
    import glob
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (path, os.path.join(here, path)):
        if os.path.isfile(cand):
            return cand
    hits = sorted(glob.glob(os.path.join(here, "**", os.path.basename(path)),
                            recursive=True))
    if hits:
        print(f"  shot log found at {hits[0]}")
        return hits[0]
    sys.exit(f"Shot log not found: {path}\n  Looked in the current folder and "
             f"under {here}")


def main():
    a = build_parser().parse_args()
    if len(sys.argv) == 1:
        apply_run_button_defaults(a)
    wanted = parse_shots(a.shot)
    if wanted:
        a.all = True
        a.figures = True          # a short list: save one figure per shot
        a.show = False
    if a.all and not a.shot_log:
        a.shot_log = DEFAULT_SHOT_LOG
    if a.shot_log:
        a.shot_log = resolve_log(a.shot_log)
    if not a.show:
        import matplotlib
        matplotlib.use("Agg")

    if a.all:
        if not a.shot_log:
            sys.exit("--all needs --shot-log")
        import contextlib
        import io
        with open(a.shot_log, newline="") as f:
            rows = list(csv.DictReader(f))
        if wanted:
            def _num(r):
                try:
                    return int(float(r.get("shot_number", "")))
                except ValueError:
                    return None
            rows = [r for r in rows if _num(r) in wanted]
            have = {_num(r) for r in rows}
            miss = sorted(wanted - have)
            if miss:
                print(f"  not in this log: shot {', '.join(map(str, miss))}")
        results, cols = [], []
        for row in rows:
            n = row.get("shot_number", "?")
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    summ = run_shot(a, row, make_figures=a.figures)
            except FileNotFoundError as e:
                print(f"  shot {n}: skipped, {e}")
                continue
            except Exception as e:                       # keep going on a bad shot
                print(f"  shot {n}: failed, {type(e).__name__}: {e}")
                continue
            print(f"  shot {n}: done, {len(summ)} values")
            results.append((row, summ))
            for c in summ:
                if c not in cols:
                    cols.append(c)
        if not results:
            sys.exit("No shot could be analysed.")

        def table(title, short):
            show = [c for c in short if c in cols]
            if not show:
                return
            print(f"\n\n{title}, ns")
            print("=" * (8 + 13 * len(show)))
            print(f"  {'shot':<6}" + "".join(f"{short[c]:>13}" for c in show))
            for row, summ in results:
                print(f"  {row.get('shot_number', '?'):<6}" + "".join(
                    f"{summ[c]:13.2f}" if c in summ else f"{'-':>13}" for c in show))
            print(f"  {'mean':<6}" + "".join(
                f"{np.mean([s_[c] for _, s_ in results if c in s_]):13.2f}" for c in show))
            print(f"  {'std':<6}" + "".join(
                f"{np.std([s_[c] for _, s_ in results if c in s_], ddof=1):13.2f}"
                if sum(c in s_ for _, s_ in results) > 1 else f"{'-':>13}" for c in show))

        tag = ("SHOTS " + a.shot) if wanted else "ALL SHOTS"
        table(f"{tag}: TRIGGER, LASERS AND SWITCHES", {
            "Trig Sync: measured - predicted": "sync-pred",
            "implied TG-100 sync delay": "sync dly",
            "Laser 1: Q-switch sync after its trigger arrives": "L1 dly",
            "Laser 2: Q-switch sync after its trigger arrives": "L2 dly",
            "Laser 1: LTGS1 B-dot after the Q-switch sync": "L1->SW1",
            "Laser 2: LTGS2 B-dot after the Q-switch sync": "L2->SW2",
            "Q-switch sync spacing, laser 2 - laser 1": "Q spacing",
            "RVM collapse spacing, 2 - 1": "RVM spacing"})
        table(f"{tag}: OUTPUT AT C225, {OUTPUT_LEVEL:g}%", {
            "commanded spacing": "commanded",
            "Output: pulse 1 start after the laser 1 sync": "L1->out",
            "Output: pulse 2 start after the laser 2 sync": "L2->out",
            "Output: pulse 1 width": "P1 width",
            "Output: pulse 2 width": "P2 width",
            "Output: start to start": "start-start",
            "Output: gap, pulse 1 end to pulse 2 start": "gap",
            "Output: commanded spacing minus gap": "cmd - gap"})

        key = "Output: commanded spacing minus gap"
        offs = [s_[key] for _, s_ in results if key in s_]
        if offs:
            off = float(np.mean(offs))
            sd = float(np.std(offs, ddof=1)) if len(offs) > 1 else float("nan")
            print(f"\n\nSETTING THE GAP AT C225, {OUTPUT_LEVEL:g}%")
            print("=" * 74)
            print(f"  gap = (D - B) - {off:.1f} ns      from {len(offs)} shot"
                  + ("s" if len(offs) > 1 else "")
                  + (f", spread {sd:.1f} ns" if len(offs) > 1 else ""))
            print(f"  So for a target gap, set  D - B = gap + {off:.1f} ns  on the laser DG535.")
            try:
                dgl_last = laser_dg_delays(results[-1][0])[0]
                b0, d0 = dgl_last["B"] / 1000.0, dgl_last["D"] / 1000.0
            except Exception:
                b0 = d0 = None
            head = f"\n  {'target gap':>12}{'D - B':>14}"
            if b0 is not None:
                head += f"{'B, D held at ' + format(d0, '.4f'):>26}{'D, B held at ' + format(b0, '.4f'):>26}"
            print(head)
            for g in (1000, 500, 300, 200, 100, 50):
                sep = (g + off) / 1000.0
                row_txt = f"  {g:9d} ns{sep:11.4f} us"
                if b0 is not None:
                    row_txt += f"{d0 - sep:23.4f} us{b0 + sep:23.4f} us"
                print(row_txt)
            if b0 is not None:
                print("  B and D are the laser DG535 Q-switch delays, in us after their "
                      "flashlamp channel.")
                print("  Move one and hold the other. The one you move fires its switch at "
                      "a different")
                print("  point on the charge ramp, so check the gap on the first shot and "
                      "correct.")
            print("  Holds at the pressure and charge of these shots. Redo it if they change.")

        out_dir = a.out or a.dir or os.path.dirname(os.path.abspath(a.shot_log))
        stem = os.path.splitext(os.path.basename(a.shot_log))[0].replace("shot_log", "timing_summary")
        if wanted:
            stem += f"_shots_{min(wanted)}_to_{max(wanted)}"
        path = os.path.join(out_dir, stem + ".csv")
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["shot_number", "datetime", "pressure_psi", "bnc575_A_delay_us",
                        "bnc575_B_delay_us"] + cols)
            for row, summ in results:
                w.writerow([row.get("shot_number"), row.get("datetime"),
                            row.get("pressure_psi"), row.get("bnc575_A_delay_us"),
                            row.get("bnc575_B_delay_us")]
                           + [f"{summ[c]:.3f}" if c in summ else "" for c in cols])
        print(f"\n  wrote {path}")
        return 0

    row = read_shot_row(a.shot_log, a.shot) if a.shot_log and a.shot else {}
    try:
        run_shot(a, row)
    except FileNotFoundError as e:
        sys.exit(str(e))
    if a.show:
        import matplotlib.pyplot as plt
        plt.show()
    return 0


if __name__ == "__main__":
    sys.exit(main())