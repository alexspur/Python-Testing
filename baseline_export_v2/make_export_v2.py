"""
Checks and export for the py-3 output-probe baseline, session
experiment_log_20260924_170806.

Read-only on the data. Reads the rigol CSVs, the new py-3 .mat files in
logs/processed_shots, the py-2 .mat files saved in analysis_backup_py2, and
the summary cache. Writes only into this folder (and, with --matlab-input,
one CSV of Python edges into the given folder for the MATLAB comparison).

    python make_export_v2.py [--matlab-input DIR]
"""

import contextlib
import csv
import io
import json
import os
import sys
from pathlib import Path

import numpy as np
from scipy.io import loadmat

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                                             # Python Testing
sys.path.insert(0, str(ROOT / "ScopeDelayGUI"))
sys.path.insert(0, str(ROOT / "logs"))

from analysis import pipeline as P                             # noqa: E402
from analysis import process_shots as PS                       # noqa: E402
import shot_timing as ST                                       # noqa: E402

import matplotlib                                              # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                # noqa: E402

STAMP = "20260924_170806"
SDIR = ROOT / "logs" / "2026.09.24" / f"experiment_log_{STAMP}"
NEW = ROOT / "logs" / "processed_shots"
OLD = ROOT / "analysis_backup_py2" / "processed_shots"
CHECK_SHOTS = (43, 44, 45, 46)
LEVELS = (10, 15, 20, 25, 50, 90)
EXPECT_WIDTH = {43: 129.6, 44: 129.8, 45: 129.7, 46: 129.6}
EXPECT_CMD_GAP = {43: 71.1, 44: 70.2, 45: 70.1, 46: 70.5}
UNCHANGED = ("Dt", "Dv", "Dv_raw", "Bt", "Bv", "Rt", "Rv", "Qt", "Qv",
             "rvm_gain", "rvm_ref", "rvm_rampRMS", "G", "ddot_factor", "rvm_factor",
             "G_consistency", "tPulse", "tEnd", "qsw_rise_trig_us",
             "spacing_rvm_ns", "spacing_qsw_ns")
UNCHANGED_PEAKS = ("LTGS1_Ddot", "LTGS2_Ddot", "LTGS1_Bdot", "LTGS2_Bdot",
                   "RVM1", "RVM2", "t_Qsw1", "t_Qsw2")


# ---------------------------------------------------------------- helpers
def load(path):
    from types import SimpleNamespace
    d = loadmat(path, squeeze_me=True, struct_as_record=False)
    return SimpleNamespace(**{k: v for k, v in d.items() if not k.startswith("__")})


def same(a, b):
    """Exact equality, NaN == NaN, through cells and structs."""
    if hasattr(a, "_fieldnames"):
        return (hasattr(b, "_fieldnames") and set(a._fieldnames) == set(b._fieldnames)
                and all(same(getattr(a, f), getattr(b, f)) for f in a._fieldnames))
    a, b = np.asarray(a), np.asarray(b)
    if a.dtype == object or b.dtype == object:
        return a.shape == b.shape and all(same(x, y) for x, y in zip(a.ravel(), b.ravel()))
    if a.shape != b.shape:
        return False
    if a.dtype.kind in "fc":
        return bool(np.array_equal(a, b, equal_nan=True))
    return bool(np.array_equal(a, b))


def win_us(S):
    """pulseWin() in ltgs_gui3_5.m: -1 us .. tEnd - tPulse + 1 us."""
    return (-1.0, (float(S.tEnd) - float(S.tPulse)) * 1e6 + 1.0)


def crop(S, probe):
    """outputCrop() in ltgs_gui3_5.m: the trace within win +/- 0.2 us."""
    t, y = np.ravel(getattr(S, f"{probe}_t")), np.ravel(getattr(S, probe))
    w = win_us(S)
    k = (t > w[0] - 0.2) & (t < w[1] + 0.2)
    return t[k], y[k]


def qsw_cross(t, v, frac):
    """qswCross() in ltgs_gui3_5.m. t in us."""
    t, v = np.ravel(t), np.ravel(v)
    if t.size < 3:
        return np.nan
    dt = t[1] - t[0]
    hi = P.movmean(v, 2 * P.mround(0.020 / dt / 2) + 1).max()
    if hi < 0.3:
        return np.nan
    vs = P.movmean(v, max(1, 2 * P.mround(0.005 / dt / 2) + 1))
    i50 = np.flatnonzero(vs >= 0.5 * hi)
    if not i50.size:
        return np.nan
    i50 = int(i50[0])
    thr = frac * hi
    if frac <= 0.5:
        a = np.flatnonzero(vs[:i50 + 1] < thr)
        if not a.size:
            return float(t[i50])
        a = int(a[-1])
        b = a + 1
    else:
        b = np.flatnonzero(vs[i50:] >= thr)
        if not b.size:
            return np.nan
        b = int(b[0]) + i50
        a = max(0, b - 1)
    if vs[b] == vs[a]:
        return float(t[b])
    return float(t[a] + (thr - vs[a]) * (t[b] - t[a]) / (vs[b] - vs[a]))


def edges_at(S, probe, frac):
    t, y = crop(S, probe)
    return P.out_edges(t, y, frac, win_us(S))


def f(x, fmt="{:.4f}"):
    return "" if x is None or not np.isfinite(x) else fmt.format(x)


# ---------------------------------------------------------------- checks
def check_unchanged(n, old, new):
    bad = [k for k in UNCHANGED if not same(getattr(old, k), getattr(new, k))]
    bad += [f"peaks.{k}" for k in UNCHANGED_PEAKS
            if not same(getattr(old.peaks, k), getattr(new.peaks, k))]
    for k in ("C225_t", "C315_t"):
        if not same(getattr(old, k), getattr(new, k)):
            bad.append(f"{k} (extent)")
    return bad


def baseline_check(S, t_ref):
    """C225 level 60..20 ns and slope 2.0..0.15 us before t_ref (us)."""
    t, y = np.ravel(S.C225_t), np.ravel(S.C225)
    lv = (t > t_ref - 0.060) & (t < t_ref - 0.020)
    sl = (t >= t_ref - 2.0) & (t < t_ref - 0.15)
    return float(y[lv].mean()), float(np.polyfit(t[sl], y[sl], 1)[0])


def shot_timing_numbers(n):
    """shot_timing.run_shot(), no figures, its printout swallowed."""
    a = ST.build_parser().parse_args(
        ["--shot-log", str(SDIR / f"shot_log_{STAMP}.csv"), "--shot", str(n)])
    row = ST.read_shot_row(a.shot_log, n)
    with contextlib.redirect_stdout(io.StringIO()):
        summ = ST.run_shot(a, row, make_figures=False)
    return (summ.get("Output: pulse 1 width"), summ.get("Output: pulse 2 width"),
            summ.get("Output: gap, pulse 1 end to pulse 2 start"))


# ---------------------------------------------------------------- export
def write_output_csv(n, old, new):
    sh = shots()[n]
    M3 = P.read_rigol(sh["files"][2])
    t3 = M3[:, 0]
    tp = float(new.tPulse)
    tpl = (t3 - tp) * 1e6
    assert np.array_equal(tpl, np.ravel(new.C225_t))
    m = (tpl >= -3.0) & (tpl <= 4.0)
    idx = np.flatnonzero(m)

    def on_full(S, probe):
        tt, yy = np.ravel(getattr(S, f"{probe}_t")), np.ravel(getattr(S, probe))
        out = np.full(t3.size, np.nan)
        j0 = int(np.searchsorted(tpl, tt[0])) if tt.size else 0
        assert tt.size == 0 or np.array_equal(tpl[j0:j0 + tt.size], tt)
        out[j0:j0 + tt.size] = yy
        return out

    cols = {"c225_kv_py2": on_full(old, "C225"), "c225_kv_py3": on_full(new, "C225"),
            "c315_kv_py2": on_full(old, "C315"), "c315_kv_py3": on_full(new, "C315")}
    with open(HERE / f"shot_{n:04d}_output.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["t_record_ns", "t_pipeline_us", "c225_raw_v", "c225_kv_py2",
                    "c225_kv_py3", "c315_raw_v", "c315_kv_py2", "c315_kv_py3"])
        for i in idx:
            w.writerow([f"{t3[i] * 1e9:.4f}", f"{tpl[i]:.7f}", f"{M3[i, 4]:.6g}",
                        f(cols["c225_kv_py2"][i], "{:.6f}"), f(cols["c225_kv_py3"][i], "{:.6f}"),
                        f"{M3[i, 3]:.6g}",
                        f(cols["c315_kv_py2"][i], "{:.6f}"), f(cols["c315_kv_py3"][i], "{:.6f}")])


def edge_table(ok_shots):
    hdr = ["Version", "Shot", "Probe", "Level %", "Cmd ns", "Laser ns",
           "P1 peak kV", "P2 peak kV", "P1 level kV", "P2 level kV",
           "P1 start us", "P1 end us", "P2 start us", "P2 end us",
           "P1 width ns", "P2 width ns", "Gap ns", "Start-start ns"]
    rows = []
    for n in ok_shots:
        for ver, S in (("py-2", load(OLD / f"shot_{n:04d}.mat")),
                       ("py-3", load(NEW / f"shot_{n:04d}.mat"))):
            cmd = float(S.settings.pulse_spacing_cmd_ns)
            for pct in LEVELS:
                frac = pct / 100.0
                q = [qsw_cross(S.Qt[k], S.Qv[k], frac) for k in (0, 1)]
                laser = (q[1] - q[0]) * 1e3
                for probe in ("C225", "C315"):
                    L, T, A = edges_at(S, probe, frac)
                    rows.append([ver, f"#{n:04d}", probe, pct, f(cmd, "{:.1f}"), f(laser, "{:.3f}"),
                                 f(A[0], "{:.3f}"), f(A[1], "{:.3f}"),
                                 f(frac * A[0], "{:.3f}"), f(frac * A[1], "{:.3f}"),
                                 f(L[0], "{:.6f}"), f(T[0], "{:.6f}"),
                                 f(L[1], "{:.6f}"), f(T[1], "{:.6f}"),
                                 f((T[0] - L[0]) * 1e3), f((T[1] - L[1]) * 1e3),
                                 f((L[1] - T[0]) * 1e3), f((L[1] - L[0]) * 1e3)])
    with open(HERE / "edge_table.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(hdr)
        w.writerows(rows)


def summary_rows():
    cache = json.loads((NEW / "summary_cache.json").read_text(encoding="utf-8"))
    rows = sorted((v["row"] for v in cache.values() if v["row"].get("stamp") == STAMP),
                  key=PS._sort_key)
    PS.write_summary(HERE / "shot_summary_20260924_170806.csv", rows)
    return rows


def plot(n, old, new):
    fig, ax = plt.subplots(1, 2, figsize=(14, 5.5))
    a = ax[0]
    for S, lab, col in ((old, "py-2 (cubic over the record)", "0.55"),
                        (new, "py-3 (local baseline)", "m")):
        t, y = np.ravel(S.C225_t), np.ravel(S.C225)
        m = (t >= -2.0) & (t <= 0.0)
        a.plot(t[m], y[m], color=col, lw=0.9, label=lab)
    a.axhline(0, color="k", lw=0.6)
    a.set_xlim(-2.0, 0.0)
    a.set_ylim(-26, 26)
    a.set_xlabel("time from tPulse (us)")
    a.set_ylabel("C225 (kV)")
    a.set_title(f"Shot {n}: C225 before pulse 1")
    a.legend(loc="upper left", fontsize=9)

    a = ax[1]
    for S, lab, col in ((old, "py-2", "0.55"), (new, "py-3", "m")):
        t, y = crop(S, "C225")
        L, T, A = P.out_edges(t, y, 0.5, win_us(S))
        x = (t - L[0]) * 1e3
        m = (x >= 104) & (x <= 152)
        a.plot(x[m], y[m], color=col, lw=1.2, label=f"{lab}, width {(T[0] - L[0]) * 1e3:.2f} ns")
        xc = (T[0] - L[0]) * 1e3
        a.axvline(xc, color=col, ls="--", lw=0.9)
        a.plot([xc], [0.5 * A[0]], "o", color=col, ms=6)
    a.set_xlim(104, 152)
    a.set_xlabel("ns after pulse 1 50% start (each version its own start)")
    a.set_ylabel("C225 (kV)")
    a.set_title("End of pulse 1, 50% crossings marked")
    a.legend(loc="best", fontsize=9)
    fig.tight_layout()
    fig.savefig(HERE / f"shot_{n:04d}_before_after.png", dpi=130)
    plt.close(fig)


_SHOTS = {}


def shots():
    if not _SHOTS:
        for sh in PS.session_shots(SDIR, STAMP):
            if np.isfinite(sh["shot_number"]):
                _SHOTS[int(sh["shot_number"])] = sh
    return _SHOTS


# ---------------------------------------------------------------- main
def main():
    out = {"checks": {}}
    rows = summary_rows()
    ok_shots = [int(float(r["shot_number"])) for r in rows if r["status"] == "ok"]
    out["ok_shots"] = ok_shots
    print("ok shots:", ok_shots)

    for n in CHECK_SHOTS:
        old, new = load(OLD / f"shot_{n:04d}.mat"), load(NEW / f"shot_{n:04d}.mat")
        assert str(old.pipeline_version) == "py-2" and str(new.pipeline_version) == "py-3"
        c = {}
        c["changed_unchanged_fields"] = check_unchanged(n, old, new)
        on = float(new.out_onset_us.C225)
        e = new.edges.C225
        lead1 = float(np.ravel(e.lead_us)[0])
        c["onset_us"] = on
        c["onset_c315_us"] = float(new.out_onset_us.C315)
        c["level_kV_vs_onset"], c["slope_kV_per_us_vs_onset"] = baseline_check(new, on)
        c["level_kV_vs_50pct_start"], c["slope_kV_per_us_vs_50pct_start"] = baseline_check(new, lead1)
        c["py2_level_kV_vs_50pct_start"], c["py2_slope_kV_per_us_vs_50pct_start"] = \
            baseline_check(old, lead1)
        w = np.ravel(e.width_ns)
        cmd = float(new.settings.pulse_spacing_cmd_ns)
        c["p1_width_ns"], c["p2_width_ns"] = float(w[0]), float(w[1])
        c["gap_ns"] = float(e.gap_ns)
        c["start_to_start_ns"] = float(e.start_to_start_ns)
        c["cmd_minus_gap_ns"] = cmd - float(e.gap_ns)
        c["expect_width_ns"], c["expect_cmd_minus_gap_ns"] = EXPECT_WIDTH[n], EXPECT_CMD_GAP[n]
        c["peak_C225_kV"] = float(new.peaks.C225_Ddot)
        c["peak_C225_kV_py2"] = float(old.peaks.C225_Ddot)
        c["peak_C315_kV"] = float(new.peaks.C315_Bdot)
        c["peak_C315_kV_py2"] = float(old.peaks.C315_Bdot)
        e315 = new.edges.C315
        c["c315_p1_width_ns"] = float(np.ravel(e315.width_ns)[0])
        c["c315_gap_ns"] = float(e315.gap_ns)
        sw1, sw2, sgap = shot_timing_numbers(n)
        c["shot_timing_p1_width_ns"], c["shot_timing_p2_width_ns"], c["shot_timing_gap_ns"] = sw1, sw2, sgap
        out["checks"][n] = c
        print(n, json.dumps(c, default=str))

        write_output_csv(n, old, new)
        plot(n, old, new)

    edge_table(ok_shots)
    (HERE / "checks.json").write_text(json.dumps(out, indent=1, default=str))

    if "--matlab-input" in sys.argv:
        d = Path(sys.argv[sys.argv.index("--matlab-input") + 1])
        with open(d / "python_edges.csv", "w", newline="") as fh:
            wr = csv.writer(fh)
            wr.writerow(["shot", "probe", "pct", "lead1", "trail1", "lead2", "trail2", "A1", "A2"])
            for n in ok_shots:
                S = load(NEW / f"shot_{n:04d}.mat")
                for probe in ("C225", "C315"):
                    for pct in LEVELS:
                        L, T, A = edges_at(S, probe, pct / 100.0)
                        wr.writerow([n, probe, pct] + [repr(float(x)) for x in (*L[:1], T[0], L[1], T[1], *A)])
    print("done")


if __name__ == "__main__":
    main()
