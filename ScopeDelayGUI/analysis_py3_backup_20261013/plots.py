"""Standard figures for one shot and for the whole log.

Styling follows ltgs_gui3: Times New Roman bold, boxed axes, ticks in,
minor ticks, light grid, same trace colors and line styles, same default
limits (X -4.7..4.7 us, Y -660..100 kV, Q -1..6 V).
"""

from __future__ import annotations

import logging
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .pipeline import CHANNEL_NAMES  # noqa: E402

logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)

XLIM_US = (-4.7, 4.7)
YLIM_KV = (-660, 100)
QLIM_V = (-1, 6)

COL = {
    "D1": "#0000ff", "D2": "#ff0000", "B1": "#009900", "B2": "#00b3b3",
    "C225": "#ff00ff", "C315": "#8c4512", "R1": "#666666", "R2": "#b3b3b3",
    "Q1": "#d9541a", "Q2": "#7d2e8f",
}

STYLE = {
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "Liberation Serif", "DejaVu Serif"],
    "font.weight": "bold",
    "axes.labelweight": "bold",
    "axes.titleweight": "bold",
    "font.size": 11,
    "axes.linewidth": 1.2,
    "xtick.direction": "in",
    "ytick.direction": "in",
    "xtick.minor.visible": True,
    "ytick.minor.visible": True,
    "xtick.top": True,
    "ytick.right": True,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "legend.fontsize": 9,
    "legend.framealpha": 0.9,
}

LW = 1.5


def _num(x, fmt):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "--"
    return "--" if not np.isfinite(x) else fmt % x


def _minmax(t, v, n=3000):
    """Min/max envelope for plotting long records without losing spikes."""
    if v.size <= 2 * n:
        return t, v
    k = v.size // n
    m = k * n
    tb = t[:m].reshape(n, k)
    vb = v[:m].reshape(n, k)
    tt = np.repeat(tb[:, 0], 2)
    vv = np.column_stack([vb.min(axis=1), vb.max(axis=1)]).ravel()
    return tt, vv


def _clip(t, y, xlim, margin=0.5):
    m = (t >= xlim[0] - margin) & (t <= xlim[1] + margin)
    return t[m], y[m]


def shot_title(S):
    st = S["settings"]
    parts = [S["name"]]
    if st.get("datetime"):
        parts.append(st["datetime"][:19])
    p = st.get("pressure_psi", np.nan)
    if np.isfinite(p):
        parts.append(f"{p:.1f} psi")
    kv = np.nanmean([st.get("wj1_charge_kv", np.nan), st.get("wj2_charge_kv", np.nan)]) \
        if np.isfinite([st.get("wj1_charge_kv", np.nan), st.get("wj2_charge_kv", np.nan)]).any() else np.nan
    if np.isfinite(kv):
        parts.append(f"{kv:.1f} kV")
    c = st.get("pulse_spacing_cmd_ns", np.nan)
    if np.isfinite(c):
        parts.append(f"{c:.0f} ns commanded")
    return "   |   ".join(parts)


def analysis_figure(S, path):
    """Four panels for a fired shot: LTGS voltage with RVMs, B-dots,
    C225/C315, and the Q-switch monitors with the spacing check."""
    pk = S["peaks"]
    with plt.rc_context(STYLE):
        fig, axs = plt.subplots(2, 2, figsize=(15, 9.5), constrained_layout=True)

        ax = axs[0, 0]
        for key, lab, t, y, ls in (
            ("D1", "LTGS1-232 D-dot", S["Dt"][0], S["Dv"][0], "-"),
            ("D2", "LTGS2-232 D-dot", S["Dt"][1], S["Dv"][1], "-"),
            ("R1", "RVM 1", S["Rt"][0], S["Rv"][0], "-"),
            ("R2", "RVM 2", S["Rt"][1], S["Rv"][1], "--"),
        ):
            tt, yy = _clip(t, y, XLIM_US)
            ax.plot(tt, yy, ls, color=COL[key], lw=LW, label=lab)
        ax.set_xlim(XLIM_US)
        lo = min(YLIM_KV[0], np.nanmin([np.nanmin(_clip(S["Dt"][i], S["Dv"][i], XLIM_US)[1])
                                        for i in range(2)]) * 1.05)
        ax.set_ylim(lo, YLIM_KV[1])
        ax.set_ylabel("Voltage (kV)")
        ax.set_title("LTGS D-dots and RVMs")
        ax.legend(loc="lower right")

        ax = axs[0, 1]
        for key, lab, t, y, ls in (
            ("B1", "LTGS1-007 B-dot Z*I", S["Bt"][0], S["Bv"][0], "--"),
            ("B2", "LTGS2-007 B-dot Z*I", S["Bt"][1], S["Bv"][1], "--"),
        ):
            tt, yy = _clip(t, y, XLIM_US)
            ax.plot(tt, yy, ls, color=COL[key], lw=LW, label=lab)
        ax.set_xlim(XLIM_US)
        ax.set_ylabel("Z*I (kV)")
        ax.set_title("LTGS B-dots")
        ax.legend(loc="best")

        ax = axs[1, 0]
        tt, yy = _clip(S["C225_t"], S["C225"], XLIM_US)
        ax.plot(tt, yy, "-.", color=COL["C225"], lw=LW, label="C225 D-dot")
        tt, yy = _clip(S["C315_t"], S["C315"], XLIM_US)
        ax.plot(tt, yy, ":", color=COL["C315"], lw=LW + 0.3, label="C315 B-dot Z*I")
        ax.set_xlim(XLIM_US)
        ax.set_ylabel("Voltage (kV)")
        ax.set_xlabel("Time from pulse 1 (us)")
        ax.set_title("C225 / C315 monitors")
        ax.legend(loc="best")

        ax = axs[1, 1]
        for i, key, lab in ((0, "Q1", "Laser1 Q-switch"), (1, "Q2", "Laser2 Q-switch")):
            tt, yy = _clip(S["Qt"][i], S["Qv"][i], XLIM_US)
            ax.plot(tt, yy, "-", color=COL[key], lw=LW, label=lab)
        ax.set_xlim(XLIM_US)
        ax.set_ylim(QLIM_V)
        ax.set_ylabel("Q-switch (V)")
        ax.set_xlabel("Time from pulse 1 (us)")
        ax.set_title("Q-switch monitors")
        ax.legend(loc="upper right")
        ax.text(0.02, 0.97, spacing_text(S), transform=ax.transAxes, va="top",
                family="monospace", fontsize=10,
                bbox=dict(boxstyle="round", fc="white", ec="0.6"))

        fig.suptitle(shot_title(S), fontsize=14, fontweight="bold")
        g = S.get("rvm_gain", [np.nan, np.nan])
        fig.text(0.5, -0.01,
                 "Peaks (kV):  D1 {}  D2 {}  B1 {}  B2 {}  C225 {}  C315 {}  RVM1 {}  RVM2 {}"
                 "     RVM gain {}/{}".format(
                     _num(pk.get("LTGS1_Ddot"), "%.0f"), _num(pk.get("LTGS2_Ddot"), "%.0f"),
                     _num(pk.get("LTGS1_Bdot"), "%.1f"), _num(pk.get("LTGS2_Bdot"), "%.1f"),
                     _num(pk.get("C225_Ddot"), "%.0f"), _num(pk.get("C315_Bdot"), "%.1f"),
                     _num(pk.get("RVM1"), "%.0f"), _num(pk.get("RVM2"), "%.0f"),
                     _num(g[0], "%.3f"), _num(g[1], "%.3f")),
                 ha="center", va="top", fontsize=11)
        fig.savefig(path, dpi=110, bbox_inches="tight")
        plt.close(fig)


def spacing_text(S):
    st = S["settings"]
    return ("Spacing (ns)\n"
            f"commanded {_num(st.get('pulse_spacing_cmd_ns'), '%7.1f')}\n"
            f"Q-switch  {_num(S.get('spacing_qsw_ns'), '%7.1f')}\n"
            f"RVM       {_num(S.get('spacing_rvm_ns'), '%7.1f')}")


def raw_figure(S, scopes, path):
    """All 12 scope channels in volts as recorded, over the window each
    scope showed on screen (timebase delay +/- 5 divisions). Made for
    every shot, including dry runs."""
    st = S["meta"]
    with plt.rc_context(STYLE):
        fig, axs = plt.subplots(3, 4, figsize=(17, 9.5), constrained_layout=True)
        for r, k in enumerate((1, 2, 3)):
            M = scopes.get(k)
            try:
                off = float(st.get(f"rigol{k}_timebase_offset_s", "nan"))
                scl = float(st.get(f"rigol{k}_timebase_scale_s_div", "nan"))
            except ValueError:
                off = scl = np.nan
            for c in range(4):
                ax = axs[r, c]
                ax.set_title(f"Scope {k} CH{c + 1}: {CHANNEL_NAMES[k][c]}", fontsize=10)
                if M is None:
                    ax.text(0.5, 0.5, "file missing", ha="center", va="center",
                            transform=ax.transAxes)
                    continue
                t = M[:, 0]
                if np.isfinite(off) and np.isfinite(scl):
                    m = (t >= off - 5 * scl) & (t <= off + 5 * scl)
                    if m.sum() < 10:
                        m = np.ones_like(t, dtype=bool)
                else:
                    m = np.ones_like(t, dtype=bool)
                tt, vv = _minmax(t[m] * 1e6, M[m, c + 1])
                ax.plot(tt, vv, "-", color="k", lw=0.8)
                if r == 2:
                    ax.set_xlabel("Time from trigger (us)")
                if c == 0:
                    ax.set_ylabel("Volts")
        fig.suptitle(shot_title(S) + f"   |   status: {S['status']}",
                     fontsize=14, fontweight="bold")
        if S["status"] != "ok":
            q = S.get("qsw_rise_trig_us", [np.nan, np.nan])
            fig.text(0.5, -0.01,
                     f"Q-switch rise from trigger: L1 {_num(q[0], '%.3f')} us, "
                     f"L2 {_num(q[1], '%.3f')} us, spacing {_num(S.get('spacing_qsw_ns'), '%.1f')} ns"
                     f" (commanded {_num(S['settings'].get('pulse_spacing_cmd_ns'), '%.0f')} ns)"
                     + (f"      {S['error']}" if S.get("error") else ""),
                     ha="center", va="top", fontsize=11)
        fig.savefig(path, dpi=100, bbox_inches="tight")
        plt.close(fig)


def summary_figure(rows, path):
    """Peaks and spacing across every processed shot."""
    ok = [r for r in rows if r["status"] == "ok"]
    timed = [r for r in rows if np.isfinite(_f(r["spacing_qsw_ns"]))
             or np.isfinite(_f(r["spacing_rvm_ns"]))]
    with plt.rc_context(STYLE):
        fig, axs = plt.subplots(2, 1, figsize=(14, 9), constrained_layout=True)
        ax = axs[0]
        if ok:
            x = np.arange(len(ok))
            for key, col, lab in (("LTGS1_Ddot_kV", COL["D1"], "LTGS1-232 D-dot"),
                                  ("LTGS2_Ddot_kV", COL["D2"], "LTGS2-232 D-dot"),
                                  ("C225_Ddot_kV", COL["C225"], "C225 D-dot"),
                                  ("RVM1_kV", COL["R1"], "RVM1"),
                                  ("RVM2_kV", COL["R2"], "RVM2")):
                ax.plot(x, [_f(r[key]) for r in ok], "o", color=col, mfc=col, ms=7, label=lab)
            ax.set_xticks(x, [r["label"] for r in ok], rotation=45, ha="right")
            ax.legend(loc="center left", bbox_to_anchor=(1.0, 0.5))
        else:
            ax.text(0.5, 0.5, "no fired shots yet", ha="center", va="center",
                    transform=ax.transAxes)
        ax.set_ylabel("Peak |V| (kV)")
        ax.set_title("Peaks, fired shots")

        ax = axs[1]
        if timed:
            x = np.arange(len(timed))
            cmd = np.array([_f(r["spacing_cmd_ns"]) for r in timed])
            ax.axhline(0, color="k", lw=1.2)
            ax.plot(x, np.array([_f(r["spacing_qsw_ns"]) for r in timed]) - cmd, "o",
                    color=COL["Q1"], mfc=COL["Q1"], ms=7, label="Q-switch rise")
            ax.plot(x, np.array([_f(r["spacing_rvm_ns"]) for r in timed]) - cmd, "d",
                    color="#0000ff", mfc="#0000ff", ms=7, label="RVM collapse")
            ax.set_xticks(x, [r["label"] + "\n" + _num(r["spacing_cmd_ns"], "%.0f ns")
                              + ("" if r["status"] == "ok" else " dry")
                              for r in timed], rotation=45, ha="right")
            ax.legend(loc="center left", bbox_to_anchor=(1.0, 0.5))
        else:
            ax.text(0.5, 0.5, "no spacing measured yet", ha="center", va="center",
                    transform=ax.transAxes)
        ax.set_ylabel("Measured - commanded (ns)")
        ax.set_title("Pulse spacing error (commanded value under each shot)")
        fig.savefig(path, dpi=100, bbox_inches="tight")
        plt.close(fig)


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return np.nan


def open_file(path):
    """Open a file with the system viewer (Windows photo viewer, etc.)."""
    try:
        if hasattr(os, "startfile"):
            os.startfile(path)  # type: ignore[attr-defined]
    except OSError:
        pass
