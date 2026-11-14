"""
pulse_spacing.py

Spacing of the two output pulses on C225, two ways, at any edge level:

    rise to rise   pulse 1 start to pulse 2 start (the older way)
    fall to rise   pulse 1 end to pulse 2 start (the gap, the newer way)

The edge rule is outEdges from ltgs_gui3_5.m, line for line: a 5 ns moving
mean, pulses are runs above 50% of the largest peak that last 30 ns or more,
the level is that percent of each pulse's own peak, and every crossing is
interpolated between samples. At 50% this is the GUI Edge table.

Two sources for the C225 trace (SOURCE below):

  "raw"  Reads the rigol3 scope file and builds C225 itself with the local
         baseline (pipeline py-3): baseline from the raw signal 2.0 to 0.15 us
         before the pulse, integrated, zeroed 60 to 20 ns before the pulse.
         It does not depend on which pipeline version made the .mat files.
  "mat"  Reads C225 from processed_shots/shot_NNNN.mat, the trace the MATLAB
         GUI uses. Its baseline is whatever that pipeline version used.

Run it with the Run button. Edit the settings below. It prints a table and
writes pulse_spacing.csv, plus one figure per shot, into OUT_DIR.
"""
import csv
import glob
import os
import sys

import numpy as np

# ----------------------------------------------------------------------------
# SETTINGS
# ----------------------------------------------------------------------------
# LOGS_DIR = r"C:\Users\ESpurbeck.P3E-HIGHBAY-01\Desktop\LANL Project\GUI\Python Testing\logs"
LOGS_DIR = r"C:\Users\ESpurbeck\Desktop\LANL Project\Double Pulse"
SHOT_LOG = "2026.09.24/experiment_log_20260924_170806/shot_log_20260924_170806.csv"
SHOTS = "43-46"                    # "43", "43-46" or "43,45,46"
SOURCE = "raw"                     # "raw" or "mat", see above
LEVELS = [10, 25, 50, 90]          # edge levels in percent of each pulse's peak
PLOT_LEVEL = 50                    # level marked on the figures. None for no figures
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pulse_spacing_out")

CF_C225 = 1.56e11                  # C225 D-dot, FC032, V/(V s). Scope 3 CH4.
C225_COLUMN = 4                    # column of C225 in the rigol3 file (0 is time)
BASE_PRE_S = (2.0e-6, 0.15e-6)     # raw baseline window, before the onset
ZERO_S = (60e-9, 20e-9)            # the integral is zeroed here, before the onset
ONSET_FRAC = 0.3                   # onset: first sample at this fraction of the peak


# ----------------------------------------------------------------------------
# Small MATLAB equivalents
# ----------------------------------------------------------------------------
def mround(x):
    """MATLAB round(): halves go away from zero."""
    return int(np.sign(x) * np.floor(abs(x) + 0.5))


def movmean(x, k):
    """MATLAB movmean(x, k) for odd k, shrinking at the ends."""
    x = np.asarray(x, dtype=float)
    h = (int(k) - 1) // 2
    c = np.concatenate(([0.0], np.cumsum(x)))
    i = np.arange(x.size)
    lo, hi = np.maximum(i - h, 0), np.minimum(i + h + 1, x.size)
    return (c[hi] - c[lo]) / (hi - lo)


def movmax(x, k):
    from scipy.ndimage import maximum_filter1d
    return maximum_filter1d(np.asarray(x, dtype=float), size=int(k), mode="nearest")


# ----------------------------------------------------------------------------
# outEdges from ltgs_gui3_5.m
# ----------------------------------------------------------------------------
def out_edges(t, y, frac, win):
    """Edges of the first two output pulses at frac (0..1) of each pulse's own
    peak, on either polarity. t and win in us. Returns lead[2], trail[2], A[2]
    with NaN where an edge is not found.
      lead[p]:  where pulse p starts, |V| rising through frac * peak
      trail[p]: where pulse p ends,   |V| falling through frac * peak"""
    lead, trail, A = [np.nan, np.nan], [np.nan, np.nan], [np.nan, np.nan]
    t, y = np.asarray(t, float).ravel(), np.asarray(y, float).ravel()
    if t.size < 10:
        return lead, trail, A
    dt = float(np.median(np.diff(t[:1000])))
    ys = movmean(y, max(1, 2 * mround(0.005 / dt / 2) + 1))
    w = (t > win[0]) & (t < win[1])
    if not w.any():
        return lead, trail, A
    yw = ys[w]
    s = np.sign(yw[int(np.argmax(np.abs(yw)))])
    if s == 0:
        return lead, trail, A
    ys = s * ys
    ys[~w] = 0.0
    g = ys.max()
    b = (ys > 0.5 * g).astype(int)
    d = np.diff(np.concatenate(([0], b, [0])))
    rs, re_ = np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1
    keep = (re_ - rs + 1) * dt >= 0.03
    rs, re_ = rs[keep], re_[keep]
    N = ys.size

    def xc(a, c, thr):
        if ys[c] == ys[a]:
            return float(t[c])
        return float(t[a] + (thr - ys[a]) * (t[c] - t[a]) / (ys[c] - ys[a]))

    lo = 0
    for p in range(min(2, rs.size)):
        seg = np.arange(rs[p], re_[p] + 1)
        Ap = float(ys[seg].max())
        thr = frac * Ap
        A[p] = float(s * Ap)
        above = seg[ys[seg] >= 0.5 * Ap]
        i50, i50t = int(above[0]), int(above[-1])
        if frac <= 0.5:                                   # leading edge
            k = np.flatnonzero(ys[lo:i50 + 1] < thr)
            if k.size:
                a = lo + int(k[-1])
                lead[p] = xc(a, a + 1, thr)
        else:
            k = np.flatnonzero(ys[i50:re_[p] + 1] >= thr)
            if k.size and i50 + int(k[0]) > 0:
                bb = i50 + int(k[0])
                lead[p] = xc(bb - 1, bb, thr)
        hi = int(rs[p + 1]) if p + 1 < rs.size else N - 1
        if frac >= 0.5:                                   # trailing edge
            k = np.flatnonzero(ys[rs[p]:i50t + 1] >= thr)
            if k.size and int(rs[p]) + int(k[-1]) < N - 1:
                a = int(rs[p]) + int(k[-1])
                trail[p] = xc(a, a + 1, thr)
        else:
            k = np.flatnonzero(ys[i50t:hi + 1] < thr)
            if k.size and i50t + int(k[0]) > 0:
                bb = i50t + int(k[0])
                trail[p] = xc(bb - 1, bb, thr)
        lo = int(re_[p])
    return lead, trail, A


# ----------------------------------------------------------------------------
# C225 from the raw scope file, local baseline (pipeline py-3)
# ----------------------------------------------------------------------------
def read_rigol(path):
    try:
        import pandas as pd
        M = pd.read_csv(path, header=0, dtype=float, engine="c").to_numpy()
    except ImportError:
        M = np.loadtxt(path, delimiter=",", skiprows=1)
    return M[np.isfinite(M[:, 0])]


def activity(t, v, k=10, env_s=200e-9, noise_s=500e-9):
    """detect_activity from the pipeline: (start, end, mask), start None if quiet."""
    v0 = v - np.median(v)
    dt = (t[-1] - t[0]) / (t.size - 1)
    wn = max(8, mround(noise_s / dt))
    nb = v0.size // wn
    s = np.sort(v0[:nb * wn].reshape(nb, wn).std(axis=1, ddof=1))
    sig = s[max(1, mround(0.25 * s.size)) - 1]
    above = movmax(np.abs(v0), max(3, mround(env_s / dt))) > k * sig
    if not above.any():
        return None, None, above
    idx = np.flatnonzero(above)
    return t[idx[0]], t[idx[-1]], above


def c225_local(t, raw):
    """Returns (t_us from the onset, C225 in kV, window in us) or raises."""
    from scipy.integrate import cumulative_trapezoid
    t0, t1, act = activity(t, raw)
    if t0 is None:
        raise ValueError("no pulse on C225")
    dev = np.abs(raw - np.median(raw))
    dev[~act] = 0.0
    t_on = float(t[np.flatnonzero(dev >= ONSET_FRAC * dev.max())[0]])
    pre = (t >= t_on - BASE_PRE_S[0]) & (t < t_on - BASE_PRE_S[1])
    if pre.sum() < 100:
        raise ValueError("the scope 3 record starts too close to the pulse for the baseline")
    integ = cumulative_trapezoid(raw - raw[pre].mean(), t, initial=0.0)
    z = (t > t_on - ZERO_S[0]) & (t < t_on - ZERO_S[1])
    V = CF_C225 * (integ - integ[z].mean()) / 1e3
    tu = (t - t_on) * 1e6
    return tu, V, (-1.0, (t1 - t_on) * 1e6 + 1.0)


# ----------------------------------------------------------------------------
# Finding the shots
# ----------------------------------------------------------------------------
def parse_shots(spec):
    want = []
    for part in str(spec).replace(" ", "").split(","):
        if "-" in part:
            a, b = part.split("-", 1)
            want += list(range(int(a), int(b) + 1))
        elif part:
            want.append(int(part))
    return want


def find_log():
    for cand in (SHOT_LOG, os.path.join(LOGS_DIR, SHOT_LOG)):
        if os.path.isfile(cand):
            return os.path.abspath(cand)
    hits = glob.glob(os.path.join(LOGS_DIR, "**", os.path.basename(SHOT_LOG)), recursive=True)
    if hits:
        return hits[0]
    sys.exit(f"Shot log not found: {SHOT_LOG}\n  Looked under {LOGS_DIR}")


def find_file(log_path, name):
    for d in (os.path.dirname(log_path), LOGS_DIR):
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    hits = glob.glob(os.path.join(LOGS_DIR, "**", name), recursive=True)
    return hits[0] if hits else None


def load_raw(row, log_path):
    name = (row.get("rigol3_file") or "").strip()
    path = find_file(log_path, name) if name else None
    if not path:
        raise FileNotFoundError(f"scope 3 file {name or '(none in the log)'} not found")
    M = read_rigol(path)
    t, v = M[:, 0], M[:, C225_COLUMN]
    tu, V, win = c225_local(t, v)
    return tu, V, win, "local baseline, from " + os.path.basename(path)


def load_mat(n):
    from scipy.io import loadmat
    path = os.path.join(LOGS_DIR, "processed_shots", f"shot_{n:04d}.mat")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"{path} not found")
    S = loadmat(path, squeeze_me=True, simplify_cells=True)
    tu = np.asarray(S["C225_t"], float).ravel()
    V = np.asarray(S["C225"], float).ravel()
    win = (-1.0, (float(S["tEnd"]) - float(S["tPulse"])) * 1e6 + 1.0)
    ver = str(S.get("pipeline_version", "unknown"))
    note = f"from shot_{n:04d}.mat, pipeline {ver}"
    if ver != "py-3":
        note += ". This C225 does not use the local baseline. SOURCE = 'raw' does."
    return tu, V, win, note


# ----------------------------------------------------------------------------
def edges_for(tu, V, win, levels):
    keep = (tu > win[0] - 0.2) & (tu < win[1] + 0.2)          # outputCrop
    t, y = tu[keep], V[keep]
    res = {}
    for lv in levels:
        lead, trail, A = out_edges(t, y, lv / 100.0, win)
        res[lv] = dict(p1_rise=lead[0] * 1e3, p1_fall=trail[0] * 1e3,
                       p2_rise=lead[1] * 1e3, p2_fall=trail[1] * 1e3,
                       p1_peak=A[0], p2_peak=A[1])
        r = res[lv]
        r["w1"] = r["p1_fall"] - r["p1_rise"]
        r["w2"] = r["p2_fall"] - r["p2_rise"]
        r["rise_to_rise"] = r["p2_rise"] - r["p1_rise"]
        r["fall_to_rise"] = r["p2_rise"] - r["p1_fall"]
    return t, y, res


def figure(n, cmd, t, y, r, note, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    style = {"font.family": "serif", "font.serif": ["Times New Roman", "Times", "Liberation Serif"],
             "font.weight": "bold", "axes.labelweight": "bold", "axes.titleweight": "bold",
             "font.size": 11, "axes.linewidth": 1.2, "xtick.direction": "in", "ytick.direction": "in",
             "xtick.top": True, "ytick.right": True, "axes.grid": True, "grid.alpha": 0.25}
    with plt.rc_context(style):
        fig, ax = plt.subplots(figsize=(11, 5.5), constrained_layout=True)
        tn = t * 1e3
        ax.plot(tn, y, "-", color="#ff00ff", lw=1.5, label="C225")
        lvl = [PLOT_LEVEL / 100 * r["p1_peak"], PLOT_LEVEL / 100 * r["p2_peak"]]
        for x, yy, lab, col in ((r["p1_rise"], lvl[0], "P1 rise", "#0000ff"), (r["p1_fall"], lvl[0], "P1 fall", "#d9541a"),
                                (r["p2_rise"], lvl[1], "P2 rise", "#009900"), (r["p2_fall"], lvl[1], "P2 fall", "#666666")):
            if np.isfinite(x):
                ax.axvline(x, color=col, lw=1.0, ls="--")
                ax.plot([x], [yy], "o", color=col, ms=6, label=f"{lab} {x:.1f} ns")
        ytop = max(np.nanmax(y), 0) + 15
        if np.isfinite(r["fall_to_rise"]):
            ax.annotate("", xy=(r["p2_rise"], ytop * 0.5), xytext=(r["p1_fall"], ytop * 0.5),
                        arrowprops=dict(arrowstyle="<->", color="k"))
            ax.text(0.5 * (r["p1_fall"] + r["p2_rise"]), ytop * 0.5 + 4,
                    f"fall to rise {r['fall_to_rise']:.2f} ns", ha="center", va="bottom")
        x0 = r["p1_rise"] - 300 if np.isfinite(r["p1_rise"]) else tn[0]
        x1 = r["p2_fall"] + 300 if np.isfinite(r["p2_fall"]) else tn[-1]
        ax.set_xlim(x0, x1)
        ax.set_xlabel("Time (ns)")
        ax.set_ylabel("C225 (kV)")
        ax.set_title(f"Shot {n}, commanded {cmd:g} ns, edges at {PLOT_LEVEL}%:  "
                     f"rise to rise {r['rise_to_rise']:.2f} ns,  fall to rise {r['fall_to_rise']:.2f} ns")
        ax.legend(loc="lower right", fontsize=9)
        fig.text(0.01, 0.01, note, fontsize=8, fontweight="normal")
        fig.savefig(path, dpi=120)
        plt.close(fig)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    levels = sorted(set(int(x) for x in LEVELS) | ({int(PLOT_LEVEL)} if PLOT_LEVEL else set()))
    log_path = find_log()
    with open(log_path, newline="", encoding="utf-8-sig") as f:
        rows = {int(float(r["shot_number"])): r for r in csv.DictReader(f) if (r.get("shot_number") or "").strip()}
    print(f"shot log  {log_path}\nsource    {SOURCE}\n")
    table = []
    for n in parse_shots(SHOTS):
        row = rows.get(n)
        if row is None:
            print(f"shot {n}: not in the shot log. Skipped.")
            continue
        try:
            cmd = float(row.get("pulse_spacing_ns") or "nan")
        except ValueError:
            cmd = float("nan")
        try:
            tu, V, win, note = load_raw(row, log_path) if SOURCE == "raw" else load_mat(n)
        except Exception as e:
            print(f"shot {n}: skipped ({e})")
            continue
        t, y, res = edges_for(tu, V, win, levels)
        print(f"shot {n}: {note}")
        for lv in levels:
            r = res[lv]
            table.append(dict(shot=n, cmd_ns=cmd, level_pct=lv, **{k: r[k] for k in (
                "p1_rise", "p1_fall", "p2_rise", "p2_fall", "w1", "w2", "rise_to_rise", "fall_to_rise",
                "p1_peak", "p2_peak")}, cmd_minus_fall_to_rise=cmd - r["fall_to_rise"],
                rise_to_rise_minus_cmd=r["rise_to_rise"] - cmd))
        if PLOT_LEVEL:
            figure(n, cmd, t, y, res[int(PLOT_LEVEL)], note, os.path.join(OUT_DIR, f"shot_{n:04d}_spacing.png"))
    if not table:
        sys.exit("Nothing measured.")

    # ---- table ----
    print("\nC225 PULSE SPACING. Edge times in ns, from the C225 onset (raw) or from pulse 1 as the GUI places it (mat).")
    print(f"{'shot':>4} {'cmd':>6} {'level':>5} | {'P1 rise':>8} {'P1 fall':>8} {'P2 rise':>8} {'P2 fall':>8} |"
          f" {'P1 w':>7} {'P2 w':>7} | {'rise-rise':>9} {'fall-rise':>9} | {'cmd-gap':>7}")
    for r in table:
        print(f"{r['shot']:>4} {r['cmd_ns']:6.0f} {r['level_pct']:4d}% | {r['p1_rise']:8.2f} {r['p1_fall']:8.2f} "
              f"{r['p2_rise']:8.2f} {r['p2_fall']:8.2f} | {r['w1']:7.2f} {r['w2']:7.2f} | "
              f"{r['rise_to_rise']:9.2f} {r['fall_to_rise']:9.2f} | {r['cmd_minus_fall_to_rise']:7.2f}")
    print("\nOFFSETS FOR THE DG535, mean over the shots (spread = largest minus smallest)")
    print(f"{'level':>5} | {'fall to rise: D-B = gap + offset':>34} | {'rise to rise: D-B = spacing - offset':>37}")
    for lv in levels:
        a = np.array([r["cmd_minus_fall_to_rise"] for r in table if r["level_pct"] == lv])
        b = np.array([r["rise_to_rise_minus_cmd"] for r in table if r["level_pct"] == lv])
        a, b = a[np.isfinite(a)], b[np.isfinite(b)]
        if a.size:
            print(f"{lv:4d}% | offset {a.mean():8.2f} ns, spread {a.max() - a.min():5.2f} ns     | "
                  f"offset {b.mean():8.2f} ns, spread {b.max() - b.min():5.2f} ns")

    path = os.path.join(OUT_DIR, "pulse_spacing.csv")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(table[0].keys()))
        w.writeheader()
        for r in table:
            w.writerow({k: (f"{v:.4f}" if isinstance(v, float) else v) for k, v in r.items()})
    print(f"\nwrote {path}")
    if PLOT_LEVEL:
        print(f"figures in {OUT_DIR}")


if __name__ == "__main__":
    main()
