"""Raw signals and independent LTGS D-dot integration for double-pulse shots.

Usage:
    python ddot_analysis.py shot0043_raw.npz
    python ddot_analysis.py shot0040_raw.npz shot0043_raw.npz shot0044_raw.npz
    python ddot_analysis.py *.npz --show
    python ddot_analysis.py shot0043_raw.npz --smooth 50 --ylim-raw -3 3
    python ddot_analysis.py --files rigol1.csv rigol2.csv rigol3.csv --name shot0043

Input: .npz files from export_shot.py (or the three rigol CSVs with --files).

For each shot it saves, in --out (default ./ddot_plots):
    <shot>_raw_rigol1.png   RVM 1, RVM 2, CH3, CH4, raw volts
    <shot>_raw_rigol2.png   LTGS D-dots and B-dots, raw volts
    <shot>_raw_rigol3.png   Q-switches, C315, C225, raw volts
    <shot>_ddot.png         D-dots integrated two ways, with both RVMs
    <shot>_baseline.png     raw D-dot baseline, running mean, with the windows
and prints one summary row per probe. With several shots it also writes
ddot_summary.csv.

Two independent D-dot methods, neither uses the RVMs:

  July (same as process_shots.m before the RVM correction)
    before window  tPulse-8 .. tPulse-4 us
    after window   tEnd+3 .. tEnd+8 us
    offset step vp -> vq ramped from tPulse to tEnd, integrate from
    tPulse-6 us, subtract one line fitted over both windows, zero on the
    before window, scale by CF.

  Short windows + bridge
    t0 = start of the charge ramp (integral leaves the baseline by 2% of
    its peak). before window t0-2 .. t0-0.2 us, after window tEnd+0.5 ..
    tEnd+2.5 us. Subtract the before-window mean, integrate, zero on the
    before window. Whatever level is left in the after window is removed
    with a ramp from t0 to tEnd, so the trace reads 0 before and after.

The RVMs are only used for comparison: the gain column is the
least-squares D-dot / RVM ratio over the charge ramp (tPulse-3 .. -0.2 us).
"""
import argparse
import csv
import json
import os
import sys

import numpy as np
import matplotlib

if "--show" not in sys.argv:
    matplotlib.use("Agg")
import matplotlib.pyplot as plt


# ------------------------------------------------------------------ setup
DEFAULT_CONST = {
    "CF_rigol2_CH1": 1.85e11, "CF_rigol2_CH3": 1.83e11,
    "DIV_rigol1_CH1": 19588.6 / 20000, "DIV_rigol1_CH2": 19970.7 / 20000,
}
DEFAULT_MAP = {
    "rigol1": {"CH1": "RVM 1", "CH2": "RVM 2", "CH3": "CH3", "CH4": "CH4"},
    "rigol2": {"CH1": "LTGS2-232 D-dot (FC011)", "CH2": "LTGS2-007 B-dot (FC013)",
               "CH3": "LTGS1-232 D-dot (FC017)", "CH4": "LTGS1-007 B-dot (FC016)"},
    "rigol3": {"CH1": "Laser1 Q-switch", "CH2": "Laser2 Q-switch",
               "CH3": "C315 B-dot (FC027)", "CH4": "C225 D-dot (FC032)"},
}
CH_COLORS = ["#1f3fbf", "#c0392b", "#138d3b", "#8e44ad"]

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 13, "font.weight": "bold", "axes.labelweight": "bold",
    "axes.titleweight": "bold", "axes.linewidth": 1.2, "axes.grid": True,
    "grid.alpha": 0.3, "legend.fontsize": 10, "figure.figsize": (14, 7),
})


# ------------------------------------------------------------------ io
def read_rigol_csv(path):
    try:
        import pandas as pd
        df = pd.read_csv(path, header=0, usecols=range(5))
        M = df.apply(pd.to_numeric, errors="coerce").to_numpy(dtype=np.float64)
    except ImportError:
        M = np.genfromtxt(path, delimiter=",", skip_header=1, usecols=range(5))
    return M[np.isfinite(M[:, 0])]


class Shot:
    """Raw data for one shot. t in seconds, v in volts (n x 4) per scope."""

    def __init__(self, name, t, v, meta):
        self.name, self.t, self.v, self.meta = name, t, v, meta
        self.C = {**DEFAULT_CONST, **meta.get("constants", {})}
        self.map = meta.get("channel_map", DEFAULT_MAP)
        self.tP = meta.get("tPulse_s")
        self.tE = meta.get("tEnd_s")
        if self.tP is None or self.tE is None:
            self.tP, self.tE = find_pulse(self)

    @classmethod
    def from_npz(cls, path):
        d = np.load(path, allow_pickle=False)
        meta = json.loads(str(d["meta"])) if "meta" in d else {}
        t = {k: d[f"r{k}_t"] for k in (1, 2, 3)}
        v = {k: d[f"r{k}_v"].astype(np.float64) for k in (1, 2, 3)}
        name = os.path.basename(path).replace("_raw.npz", "").replace(".npz", "")
        return cls(name, t, v, meta)

    @classmethod
    def from_csv(cls, files, name):
        t, v = {}, {}
        for k, f in enumerate(files, start=1):
            print("reading", f)
            M = read_rigol_csv(f)
            t[k], v[k] = M[:, 0], M[:, 1:5]
        return cls(name, t, v, {"files": list(files)})


# ------------------------------------------------------------------ helpers
def detect_activity(t, v, k=10, env_s=200e-9, noise_s=500e-9):
    v0 = v - np.median(v)
    dt = t[1] - t[0]
    wn = max(8, int(round(noise_s / dt)))
    nb = len(v0) // wn
    s = np.sort(v0[: nb * wn].reshape(nb, wn).std(axis=1, ddof=1))
    sig = s[max(0, int(round(0.25 * nb)) - 1)]
    idx = np.flatnonzero(np.abs(v0) > k * sig)
    if idx.size == 0:
        return None, None
    half = max(3, int(round(env_s / dt))) // 2
    return t[max(0, idx[0] - half)], t[min(len(t) - 1, idx[-1] + half)]


def find_pulse(s):
    st, en = [], []
    for scope, col in ((2, 2), (2, 3), (3, 3)):   # rigol2 CH3, CH4, rigol3 CH4
        a, b = detect_activity(s.t[scope], s.v[scope][:, col])
        if a is not None:
            st.append(a)
            en.append(b)
    if not st:
        raise RuntimeError(f"{s.name}: no pulse detected")
    return float(np.median(st)), float(max(en))


def mean_in(t, v, w):
    m = (t > w[0]) & (t < w[1])
    if not m.any():
        raise RuntimeError(f"no samples in window {w[0]*1e6:.2f}..{w[1]*1e6:.2f} us "
                           "(export with a larger --pre / --post)")
    return v[m].mean()


def cumtrapz(t, v):
    out = np.zeros_like(v)
    out[1:] = np.cumsum(0.5 * (v[1:] + v[:-1]) * np.diff(t))
    return out


def running_mean(x, n):
    n = max(1, int(n))
    c = np.cumsum(np.insert(x, 0, 0.0))
    out = np.full_like(x, np.nan)
    h = n // 2
    out[h: h + len(x) - n + 1] = (c[n:] - c[:-n]) / n
    return out


# ------------------------------------------------------------------ methods
def ddot_july(s, v, CF, int_start_us=-6.0):
    t, tP, tE = s.t[2], s.tP, s.tE
    pre = (tP - 8e-6, tP - 4e-6)
    post = (tE + 3e-6, min(tE + 8e-6, t[-1]))
    vp, vq = mean_in(t, v, pre), mean_in(t, v, post)
    off = np.full_like(v, vp)
    r = (t >= tP) & (t <= tE)
    off[r] = vp + (vq - vp) * (t[r] - tP) / (tE - tP)
    off[t > tE] = vq
    im = (t >= tP + int_start_us * 1e-6) & (t <= post[1])
    ti = t[im]
    I = cumtrapz(ti, (v - off)[im])
    ip = (ti > pre[0]) & (ti < pre[1])
    iq = (ti > post[0]) & (ti < post[1])
    p = np.polyfit(ti[ip | iq] - tP, I[ip | iq], 1)
    I = I - np.polyval(p, ti - tP)
    I = I - I[ip].mean()
    info = {"pre": pre, "post": post, "vp_V": vp, "vq_V": vq,
            "drift_kV_per_us": CF * p[0] / 1e3 / 1e6}
    return ti, CF * I / 1e3, info


def ddot_short(s, v, CF, pre_len_us=2.0, pre_gap_us=0.2, post_us=(0.5, 2.5), thr=0.02):
    t, tP, tE = s.t[2], s.tP, s.tE
    # rough integral to find the start of the charge ramp
    bw = (max(t[0], tP - 10e-6), tP - 6e-6)
    I0 = CF * cumtrapz(t, v - mean_in(t, v, bw)) / 1e3
    I0s = running_mean(I0, int(1e-6 / (t[1] - t[0])))
    act = (t > tP - 6e-6) & (t < tE)
    ipk = np.nanargmax(np.where(act, np.abs(I0s), -np.inf))
    base = np.nanmean(I0s[(t > bw[0]) & (t < bw[1])])
    lvl = thr * abs(I0s[ipk] - base)
    j = ipk
    while j > 0 and abs(I0s[j] - base) > lvl:
        j -= 1
    t0 = t[j]
    pre = (t0 - pre_len_us * 1e-6, t0 - pre_gap_us * 1e-6)
    post = (tE + post_us[0] * 1e-6, tE + post_us[1] * 1e-6)
    vp = mean_in(t, v, pre)
    im = (t >= pre[0]) & (t <= post[1])
    ti = t[im]
    I = CF * cumtrapz(ti, v[im] - vp) / 1e3
    ip = (ti > pre[0]) & (ti < pre[1])
    iq = (ti > post[0]) & (ti < post[1])
    I -= I[ip].mean()
    L = I[iq].mean()
    I -= np.clip((ti - t0) / (tE - t0), 0, 1) * L
    info = {"pre": pre, "post": post, "t0_us": t0 * 1e6, "vp_V": vp,
            "post_level_kV": L, "equiv_offset_mV": L * 1e3 / CF / (tE - t0) * 1e3}
    return ti, I, info


def rvm(s, k):
    t, v = s.t[1], s.v[1][:, k]
    pre = (s.tP - 8e-6, s.tP - 4e-6)
    return t, s.C[f"DIV_rigol1_CH{k+1}"] * (v - mean_in(t, v, pre)) / 1e3


def ramp_gain(s, t, V, tr, R):
    m = (t > s.tP - 3e-6) & (t < s.tP - 0.2e-6)
    Ri = np.interp(t[m], tr, R)
    g = (Ri @ V[m]) / (Ri @ Ri)
    return g, float(np.sqrt(np.mean((V[m] - g * Ri) ** 2)))


def peak(s, t, V):
    m = (t > s.tP - 1e-6) & (t < s.tE + 1e-6)
    i = np.argmax(np.abs(V[m]))
    return float(abs(V[m][i])), float(t[m][i] * 1e6)


# ------------------------------------------------------------------ plots
def finish(fig, path, show):
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    if not show:
        plt.close(fig)
    print("  saved", path)


def plot_raw(s, out, show, smooth_ns, xl, yl=None):
    for k in (1, 2, 3):
        t, v = s.t[k], s.v[k]
        names = s.map.get(f"rigol{k}", DEFAULT_MAP[f"rigol{k}"])
        fig, ax = plt.subplots()
        n = int(round(smooth_ns * 1e-9 / (t[1] - t[0]))) if smooth_ns else 0
        for c in range(4):
            lab = f"CH{c+1}: {names.get(f'CH{c+1}', '')}"
            if n > 1:
                ax.plot(t * 1e6, v[:, c], color=CH_COLORS[c], lw=0.5, alpha=0.25)
                ax.plot(t * 1e6, running_mean(v[:, c], n), color=CH_COLORS[c], lw=1.4,
                        label=f"{lab}, {smooth_ns:g} ns mean")
            else:
                ax.plot(t * 1e6, v[:, c], color=CH_COLORS[c], lw=0.8, label=lab)
        ax.axvline(s.tP * 1e6, color="k", ls=":", lw=1)
        ax.axvline(s.tE * 1e6, color="k", ls=":", lw=1)
        if xl:
            ax.set_xlim(xl)
        if yl:
            ax.set_ylim(yl)
        ax.set_xlabel("Scope time (us)")
        ax.set_ylabel("Raw signal (V)")
        ax.set_title(f"{s.name}, rigol{k} raw (dotted: tPulse, tEnd)")
        ax.legend(loc="best")
        finish(fig, os.path.join(out, f"{s.name}_raw_rigol{k}.png"), show)


def plot_ddot(s, res, out, show, xl):
    fig, ax = plt.subplots()
    for k, ls in ((0, "-"), (1, "--")):
        tr, R = rvm(s, k)
        ax.plot(tr * 1e6, R, ls, color="0.6", lw=1, label=f"RVM {k+1}")
    for r in res:
        ax.plot(r["tj"] * 1e6, r["Vj"], color=r["color"], lw=1, alpha=0.4,
                label=f"{r['name']}, July windows")
        ax.plot(r["ts"] * 1e6, r["Vs"], color=r["color"], lw=2,
                label=f"{r['name']}, short windows + bridge")
    ax.set_xlim(xl or ((s.tP - 7e-6) * 1e6, (s.tE + 5e-6) * 1e6))
    ax.set_xlabel("Scope time (us)")
    ax.set_ylabel("Voltage (kV)")
    ax.set_title(f"{s.name}, LTGS D-dots integrated without RVM correction")
    ax.legend(loc="lower left")
    finish(fig, os.path.join(out, f"{s.name}_ddot.png"), show)


def plot_baseline(s, res, out, show):
    fig, ax = plt.subplots()
    t = s.t[2]
    n = int(round(1e-6 / (t[1] - t[0])))
    for r in res:
        v = s.v[2][:, r["col"]]
        vp = r["info_j"]["vp_V"]
        ax.plot(t * 1e6, 1e3 * (running_mean(v, n) - vp), color=r["color"], lw=1.5,
                label=f"{r['name']} raw, 1 us mean, minus July vp")
    ij = res[0]["info_j"]
    ax.axvspan(ij["pre"][0] * 1e6, ij["pre"][1] * 1e6, color="0.80", label="July before window")
    ax.axvspan(ij["post"][0] * 1e6, ij["post"][1] * 1e6, color="0.90", label="July after window")
    for r in res:
        for w in (r["info_s"]["pre"], r["info_s"]["post"]):
            ax.axvspan(w[0] * 1e6, w[1] * 1e6, color=r["color"], alpha=0.08)
    ax.set_ylim(-100, 80)
    ax.set_xlabel("Scope time (us)")
    ax.set_ylabel("Offset (mV)")
    ax.set_title(f"{s.name}, raw D-dot baseline (tinted: short windows, pulse clipped)")
    ax.legend(loc="lower left")
    finish(fig, os.path.join(out, f"{s.name}_baseline.png"), show)


# ------------------------------------------------------------------ main
def analyze(s, out, show, smooth_ns, xl_raw, xl_ddot, yl_raw=None):
    print(f"\n{s.name}: tPulse {s.tP*1e6:.3f} us, tEnd {s.tE*1e6:.3f} us (scope time)")
    probes = [("LTGS1-232", 2, s.C["CF_rigol2_CH3"], "#0000ff"),
              ("LTGS2-232", 0, s.C["CF_rigol2_CH1"], "#ff0000")]
    rv = [rvm(s, 0), rvm(s, 1)]
    res, rows = [], []
    for name, col, CF, color in probes:
        v = s.v[2][:, col]
        tj, Vj, ij = ddot_july(s, v, CF)
        ts, Vs, isv = ddot_short(s, v, CF)
        r = {"name": name, "col": col, "color": color, "tj": tj, "Vj": Vj,
             "ts": ts, "Vs": Vs, "info_j": ij, "info_s": isv}
        res.append(r)
        for method, (t, V) in (("july", (tj, Vj)), ("short", (ts, Vs))):
            pk, tpk = peak(s, t, V)
            g1, e1 = ramp_gain(s, t, V, *rv[0])
            g2, e2 = ramp_gain(s, t, V, *rv[1])
            rows.append({"shot": s.name, "probe": name, "method": method,
                         "peak_kV": pk, "t_peak_us": tpk,
                         "gain_RVM1": g1, "rms_RVM1_kV": e1,
                         "gain_RVM2": g2, "rms_RVM2_kV": e2,
                         "drift_kV_per_us": ij["drift_kV_per_us"] if method == "july" else np.nan,
                         "post_level_kV": isv["post_level_kV"] if method == "short" else np.nan,
                         "equiv_offset_mV": isv["equiv_offset_mV"] if method == "short" else np.nan,
                         "t0_us": isv["t0_us"] if method == "short" else np.nan})

    print(f"{'probe':10s} {'method':6s} {'peak kV':>8s} {'t pk us':>9s} {'g RVM1':>7s} "
          f"{'g RVM2':>7s} {'rms kV':>7s} {'drift':>7s} {'post kV':>8s}")
    for w in rows:
        print(f"{w['probe']:10s} {w['method']:6s} {w['peak_kV']:8.1f} {w['t_peak_us']:9.3f} "
              f"{w['gain_RVM1']:7.3f} {w['gain_RVM2']:7.3f} "
              f"{min(w['rms_RVM1_kV'], w['rms_RVM2_kV']):7.1f} "
              f"{w['drift_kV_per_us']:7.2f} {w['post_level_kV']:8.1f}")
    g = {(w["probe"], w["method"]): w["gain_RVM1"] for w in rows}
    for m in ("july", "short"):
        print(f"LTGS1/LTGS2 ramp ratio, {m}: {g[('LTGS1-232', m)] / g[('LTGS2-232', m)]:.3f}")
    print("drift = line removed by the July fit (kV/us). post kV = level removed by the bridge.")

    plot_raw(s, out, show, smooth_ns, xl_raw, yl_raw)
    plot_ddot(s, res, out, show, xl_ddot)
    plot_baseline(s, res, out, show)
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("npz", nargs="*", help=".npz files from export_shot.py")
    ap.add_argument("--files", nargs=3, metavar=("RIGOL1", "RIGOL2", "RIGOL3"),
                    help="read the three rigol CSVs directly instead")
    ap.add_argument("--name", default="shot", help="name for --files input")
    ap.add_argument("--out", default="ddot_plots", help="output folder")
    ap.add_argument("--smooth", type=float, default=0,
                    help="raw plots: overlay an N ns running mean (e.g. 20)")
    ap.add_argument("--xlim-raw", type=float, nargs=2, metavar=("MIN", "MAX"),
                    help="raw plots x range, us scope time")
    ap.add_argument("--ylim-raw", type=float, nargs=2, metavar=("MIN", "MAX"),
                    help="raw plots y range, V (e.g. -3 3 to see the ramp under the spikes)")
    ap.add_argument("--xlim", type=float, nargs=2, metavar=("MIN", "MAX"),
                    help="D-dot plot x range, us scope time")
    ap.add_argument("--show", action="store_true", help="open the figures")
    a = ap.parse_args()

    shots = []
    if a.files:
        shots.append(Shot.from_csv(a.files, a.name))
    for p in a.npz:
        shots.append(Shot.from_npz(p))
    if not shots:
        ap.error("give one or more .npz files, or --files")

    os.makedirs(a.out, exist_ok=True)
    rows = []
    for s in shots:
        try:
            rows += analyze(s, a.out, a.show, a.smooth, a.xlim_raw, a.xlim, a.ylim_raw)
        except RuntimeError as e:
            print(f"\n{s.name}: skipped ({e})")

    if len(shots) > 1 and rows:
        path = os.path.join(a.out, "ddot_summary.csv")
        with open(path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print("\nsummary:", path)
    if a.show:
        plt.show()


if __name__ == "__main__":
    main()
