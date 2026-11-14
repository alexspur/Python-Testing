"""
Export how the analysis pipeline (pipeline_version py-2) builds the C225
output trace, for shots 43-46 of session experiment_log_20260924_170806.

Read-only: it reads the saved rigol CSV files, the shot log, the saved
shot_NNNN.mat files and the timing summary, and writes only into this folder.
It calls the existing pipeline functions unchanged:

  analysis/pipeline.py      process_waveforms() for the final trace, and the
                            same helpers it uses (read_rigol, detect_activity,
                            movmax, cumtrapz, inwin, sample_dt, mround) to
                            expose the intermediate steps
  logs/shot_timing.py       the 50% edge finder out_edges() and its own
                            output_trace(), find_bursts(), predict(), ...

The intermediate steps are recomputed with the same calls and arguments as
process_waveforms() lines 293-310, and the script checks that they give the
same C225 as process_waveforms() and as the saved .mat file ltgs_gui3 reads.

Run from anywhere:  python make_export.py
"""

import csv
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                                   # Python Testing
sys.path.insert(0, os.path.join(ROOT, "ScopeDelayGUI"))
sys.path.insert(0, os.path.join(ROOT, "logs"))

from analysis import pipeline as P                             # noqa: E402
from analysis import process_shots as PS                       # noqa: E402
import shot_timing as ST                                       # noqa: E402

import matplotlib                                              # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                # noqa: E402

STAMP = "20260924_170806"
SDIR = os.path.join(ROOT, "logs", "2026.09.24", f"experiment_log_{STAMP}")
SHOT_LOG = os.path.join(SDIR, f"shot_log_{STAMP}.csv")
TIMING_SUMMARY = os.path.join(SDIR, f"timing_summary_{STAMP}_shots_43_to_46.csv")
MAT_DIR = os.path.join(ROOT, "logs", "processed_shots")
SHOTS = (43, 44, 45, 46)

WIN_US = (-3.0, 4.0)          # export window around pulse 1 (tPulse)
DECIMATE = 100                # whole-record files keep every 100th sample
EDGE_SPAN_US = (-2.0, 3.5)    # span handed to out_edges for the pipeline trace,
                              # the same span shot_timing.output_trace uses
LEVEL = ST.OUTPUT_LEVEL / 100.0


def runs(mask, t_us):
    """Contiguous True runs of mask as (start_us, end_us)."""
    d = np.diff(np.concatenate(([0], mask.astype(np.int8), [0])))
    a, b = np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1
    return [(float(t_us[i]), float(t_us[j])) for i, j in zip(a, b)]


def c225_steps(M3, tPulse):
    """process_waveforms() lines 293-310, step by step, same calls."""
    t3 = M3[:, 0]
    r3_pre = (max(tPulse - 2e-6, t3[0] + 0.1e-6), tPulse - 0.3e-6)     # line 257
    c3_zero = (max(tPulse - 0.9e-6, t3[0]), tPulse - 0.1e-6)           # line 258
    bm = P.inwin(t3, r3_pre)                                            # line 293
    premean = float(M3[bm, 4].mean())
    v = M3[:, 4] - premean                                              # line 304
    _, _, act = P.detect_activity(t3, v)                                # line 305
    padN = P.mround(0.3e-6 / P.sample_dt(t3))                           # line 306
    act = P.movmax(act.astype(float), 2 * padN + 1) > 0                 # line 307
    # reconstruct_quiet(t3, v, CF3_CH4, c3_zero, act, 3), lines 210-216
    integ = P.cumtrapz(t3, v)
    q = ~act
    x = t3[q]
    mu0, mu1 = float(x.mean()), float(x.std(ddof=1))                    # polyfit_mu
    p = np.polyfit((x - mu0) / mu1, integ[q], 3)
    base = np.polyval(p, (t3 - mu0) / mu1)
    zoff = float((integ - base)[P.inwin(t3, c3_zero)].mean())
    CF = P.CAL["CF3_CH4"]
    c225_kv = CF * (integ - base - zoff) / 1e3                          # line 310
    # The cubic is subtracted from the integral. Its time derivative plus the
    # pre-pulse mean is the same correction expressed in raw scope volts.
    dbase = np.polyval(np.polyder(p), (t3 - mu0) / mu1) / mu1
    return dict(t3=t3, r3_pre=r3_pre, c3_zero=c3_zero, premean=premean, v=v,
                act=act, padN=padN, integ=integ, p=p, mu0=mu0, mu1=mu1,
                base=base, zoff=zoff, CF=CF, c225_kv=c225_kv,
                base_raw=premean + dbase)


def shot_timing_edges(shot):
    """shot_timing.py's own C225 output trace and 50% edges, same calls as
    run_shot() lines 797-873. Times returned in scope record ns."""
    row = ST.read_shot_row(SHOT_LOG, shot)
    ST.use_trigger_cables(row.get("datetime"))
    dgl, _, _ = ST.laser_dg_delays(row)
    pred = ST.predict(ST.fnum(row, "bnc575_A_delay_us"),
                      ST.fnum(row, "bnc575_B_delay_us"), 180.0, dgl)
    t, chans = ST.load_scope_csv(os.path.join(SDIR, row["rigol3_file"]))
    shift = ST.record_to_sensor(3, 4)
    ts, v = t * 1e9 - shift, chans[4]
    tg_in = pred["TG-100 trigger in"]
    m = (ts >= tg_in - 2000.0) & (ts <= tg_in + 12000.0)
    tt, vv = ts[m], v[m]
    pre = tt < (tg_in - 200.0)
    bursts = ST.find_bursts(tt, vv, pre)
    first = bursts[0]["t"]
    tr = ST.output_trace(ts, v, first)
    lead, trail, amp = ST.out_edges(tr[0], tr[1], LEVEL)
    back = lambda x: None if x is None else x + shift          # sensor -> record ns
    return dict(shift=shift, first_rec=first + shift,
                lead=[back(x) for x in lead], trail=[back(x) for x in trail],
                amp=amp, t_rec=tr[0] + shift, y=tr[1])


def derived(lead, trail):
    l1, l2 = lead
    f1, f2 = trail
    ok = lambda *a: all(x is not None for x in a)                # noqa: E731
    return dict(p1_width_ns=(f1 - l1) if ok(f1, l1) else None,
                p2_width_ns=(f2 - l2) if ok(f2, l2) else None,
                gap_ns=(l2 - f1) if ok(l2, f1) else None,
                start_to_start_ns=(l2 - l1) if ok(l2, l1) else None)


def fmt(x, f="{:.6f}"):
    return "" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f.format(x)


def write_csv(path, cols):
    names = list(cols)
    n = len(cols[names[0]])
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(names)
        for i in range(n):
            w.writerow([c[i] for c in (cols[k] for k in names)])


def trace_columns(s, tPulse, idx):
    t3 = s["t3"][idx]
    return {
        "t_record_ns": [f"{x:.4f}" for x in t3 * 1e9],
        "t_pipeline_us": [f"{x:.7f}" for x in (t3 - tPulse) * 1e6],
        "raw_v": [f"{x:.6g}" for x in s["v"][idx] + s["premean"]],
        "baseline": [f"{x:.9e}" for x in s["base"][idx]],
        "integral_before": [f"{x:.9e}" for x in s["integ"][idx]],
        "c225_kv": [f"{x:.6f}" for x in s["c225_kv"][idx]],
        "integrand_v": [f"{x:.6g}" for x in s["v"][idx]],
        "baseline_raw_equiv_v": [f"{x:.6g}" for x in s["base_raw"][idx]],
        "in_fit": ["0" if a else "1" for a in s["act"][idx]],
    }


def main():
    from scipy.io import loadmat

    saved = {}
    with open(TIMING_SUMMARY, newline="") as fh:
        for r in csv.DictReader(fh):
            saved[int(r["shot_number"])] = r

    shots = {int(sh["shot_number"]): sh
             for sh in PS.session_shots(__import__("pathlib").Path(SDIR), STAMP)
             if np.isfinite(sh["shot_number"])}
    edge_rows = []
    for n in SHOTS:
        sh = shots[n]
        print(f"shot {n}: {[f.name for f in sh['files']]}")
        M1, M2, M3 = (P.read_rigol(f) for f in sh["files"])
        S = P.process_waveforms(M1, M2, M3)                       # unchanged
        tPulse, tEnd = S["tPulse"], S["tEnd"]
        s = c225_steps(M3, tPulse)

        # checks: the step-by-step trace equals the pipeline's and the saved one
        d_pipe = float(np.max(np.abs(s["c225_kv"] - S["C225"])))
        mat = loadmat(os.path.join(MAT_DIR, f"shot_{n:04d}.mat"))
        c_mat = mat["C225"].ravel()
        t_mat = mat["C225_t"].ravel()
        d_mat = float(np.max(np.abs(S["C225"] - c_mat))) if c_mat.size == S["C225"].size else np.nan
        dt_mat = float(np.max(np.abs(S["C225_t"] - t_mat))) if t_mat.size == S["C225_t"].size else np.nan
        d_tp = abs(float(mat["tPulse"].ravel()[0]) - tPulse)
        print(f"  max |steps - process_waveforms| = {d_pipe:.3e} kV")
        print(f"  max |process_waveforms - saved .mat| = {d_mat:.3e} kV, "
              f"time axis {dt_mat:.3e} us, tPulse {d_tp:.3e} s")

        t_us = (s["t3"] - tPulse) * 1e6
        win = (t_us >= WIN_US[0]) & (t_us <= WIN_US[1])
        write_csv(os.path.join(HERE, f"shot_{n:04d}_c225.csv"),
                  trace_columns(s, tPulse, np.flatnonzero(win)))
        write_csv(os.path.join(HERE, f"shot_{n:04d}_c225_whole_record.csv"),
                  trace_columns(s, tPulse, np.arange(0, s["t3"].size, DECIMATE)))

        # 50% edges, (a) out_edges on the pipeline trace, (b) shot_timing's own
        em = (t_us >= EDGE_SPAN_US[0]) & (t_us <= EDGE_SPAN_US[1])
        lead_p, trail_p, amp_p = ST.out_edges(t_us[em] * 1e3, s["c225_kv"][em], LEVEL)
        to_us = lambda x: None if x is None else x / 1e3              # ns -> us
        pl = dict(lead=[to_us(x) for x in lead_p], trail=[to_us(x) for x in trail_p],
                  amp=amp_p)
        st = shot_timing_edges(n)
        rec_to_us = lambda x: None if x is None else (x * 1e-9 - tPulse) * 1e6
        stu = dict(lead=[rec_to_us(x) for x in st["lead"]],
                   trail=[rec_to_us(x) for x in st["trail"]], amp=st["amp"])
        dp = derived(lead_p, trail_p)
        ds = derived(st["lead"], st["trail"])

        excl = runs(s["act"], t_us)
        row = {
            "shot": n,
            "tPulse_record_s": f"{tPulse:.9e}",
            "tEnd_record_s": f"{tEnd:.9e}",
            "pulse_window_us_start": "0",
            "pulse_window_us_end": f"{(tEnd - tPulse) * 1e6:.4f}",
            "premean_window_us": f"{(s['r3_pre'][0] - tPulse) * 1e6:.3f} to {(s['r3_pre'][1] - tPulse) * 1e6:.3f}",
            "premean_v": f"{s['premean']:.6g}",
            "zero_window_us": f"{(s['c3_zero'][0] - tPulse) * 1e6:.3f} to {(s['c3_zero'][1] - tPulse) * 1e6:.3f}",
            "zero_offset_Vs": f"{s['zoff']:.9e}",
            "fit_p3": f"{s['p'][0]:.9e}", "fit_p2": f"{s['p'][1]:.9e}",
            "fit_p1": f"{s['p'][2]:.9e}", "fit_p0": f"{s['p'][3]:.9e}",
            "fit_mu0_record_s": f"{s['mu0']:.9e}", "fit_mu1_s": f"{s['mu1']:.9e}",
            "fit_range_us": f"{t_us[0]:.3f} to {t_us[-1]:.3f}",
            "fit_samples_used": int((~s["act"]).sum()),
            "fit_samples_excluded": int(s["act"].sum()),
            "excluded_intervals_us": "; ".join(f"{a:.3f} to {b:.3f}" for a, b in excl),
            "CF_V_per_Vs": f"{s['CF']:.4g}",
            "check_max_diff_vs_saved_mat_kV": f"{d_mat:.3e}",
        }
        for tag, e, dd in (("pl", pl, dp), ("st", stu, ds)):
            row[f"{tag}_p1_start_us"] = fmt(e["lead"][0])
            row[f"{tag}_p1_end_us"] = fmt(e["trail"][0])
            row[f"{tag}_p2_start_us"] = fmt(e["lead"][1])
            row[f"{tag}_p2_end_us"] = fmt(e["trail"][1])
            row[f"{tag}_p1_width_ns"] = fmt(dd["p1_width_ns"], "{:.3f}")
            row[f"{tag}_p2_width_ns"] = fmt(dd["p2_width_ns"], "{:.3f}")
            row[f"{tag}_gap_ns"] = fmt(dd["gap_ns"], "{:.3f}")
            row[f"{tag}_start_to_start_ns"] = fmt(dd["start_to_start_ns"], "{:.3f}")
            row[f"{tag}_p1_peak"] = fmt(e["amp"][0], "{:.6g}")
            row[f"{tag}_p2_peak"] = fmt(e["amp"][1], "{:.6g}")
        sv = saved.get(n, {})
        row["saved_timing_summary_p1_width_ns"] = sv.get("Output: pulse 1 width", "")
        row["saved_timing_summary_p2_width_ns"] = sv.get("Output: pulse 2 width", "")
        row["saved_timing_summary_gap_ns"] = sv.get("Output: gap, pulse 1 end to pulse 2 start", "")
        row["saved_timing_summary_start_to_start_ns"] = sv.get("Output: start to start", "")
        edge_rows.append(row)
        print(f"  edges on pipeline trace: width {fmt(dp['p1_width_ns'], '{:.3f}')} ns, "
              f"gap {fmt(dp['gap_ns'], '{:.3f}')} ns, s2s {fmt(dp['start_to_start_ns'], '{:.3f}')} ns")
        print(f"  edges on shot_timing trace: width {fmt(ds['p1_width_ns'], '{:.3f}')} ns, "
              f"gap {fmt(ds['gap_ns'], '{:.3f}')} ns  (saved: "
              f"{row['saved_timing_summary_p1_width_ns']} / {row['saved_timing_summary_gap_ns']})")
        print(f"  {len(excl)} excluded interval(s): {row['excluded_intervals_us'][:200]}")

        plot_shot(n, s, tPulse, t_us, pl, stu, excl)

    with open(os.path.join(HERE, "edges.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(edge_rows[0]))
        w.writeheader()
        w.writerows(edge_rows)
    print("done")


def plot_shot(n, s, tPulse, t_us, pl, stu, excl):
    fig, ax = plt.subplots(3, 1, figsize=(11, 12))

    # 1: raw CH4 before pulse 1, with the baseline in raw volts
    m = (t_us >= -2.3) & (t_us <= 0.0)
    raw = s["v"] + s["premean"]
    a = ax[0]
    a.plot(t_us[m], raw[m], color="0.6", lw=0.5, label="raw CH4 (scope V)")
    a.plot(t_us[m], s["base_raw"][m], color="C3", lw=1.5,
           label="baseline in raw volts: pre-mean + d/dt(cubic)")
    a.axhline(s["premean"], color="C0", ls=":", lw=1, label="pre-pulse mean (subtracted first)")
    r0, r1 = (s["r3_pre"][0] - tPulse) * 1e6, (s["r3_pre"][1] - tPulse) * 1e6
    a.axvspan(r0, r1, color="C0", alpha=0.08, label="pre-mean window")
    for x0, x1 in excl:
        if x1 >= -2.3 and x0 <= 0:
            a.axvspan(max(x0, -2.3), min(x1, 0), color="C1", alpha=0.15)
    lo, hi = np.percentile(raw[m], [1, 99])
    pad = 0.6 * (hi - lo) + 1e-3
    a.set_ylim(lo - pad, hi + pad)
    a.set_xlim(-2.3, 0)
    a.set_xlabel("pipeline time (us, pulse 1 = tPulse = 0)")
    a.set_ylabel("V")
    a.set_title(f"Shot {n}: raw C225 D-dot (scope 3 CH4) before pulse 1. "
                "Orange = samples left out of the fit")
    a.legend(fontsize=8, loc="upper left")

    # 2: integral before baseline removal, with the cubic, whole record
    a = ax[1]
    k = slice(None, None, 10)
    a.plot(t_us[k], s["integ"][k], color="0.3", lw=0.8, label="cumtrapz(raw - pre-mean)")
    a.plot(t_us[k], s["base"][k], color="C3", lw=1.2, label="cubic baseline (fit to the integral)")
    for i, (x0, x1) in enumerate(excl):
        a.axvspan(x0, x1, color="C1", alpha=0.2, label="excluded from fit" if i == 0 else None)
    a.set_xlabel("pipeline time (us)")
    a.set_ylabel("V s")
    a.set_title("Integrated trace before baseline removal, whole record")
    a.legend(fontsize=8, loc="best")

    # 3: final C225 with the 50% edges
    a = ax[2]
    m = (t_us >= -0.4) & (t_us <= 1.4)
    a.plot(t_us[m], s["c225_kv"][m], color="m", lw=1, label="C225 (pipeline, saved trace)")
    for e, style, lab in ((pl, "-", "50% edges, out_edges on this trace"),
                          (stu, "--", "50% edges, shot_timing.py own trace")):
        first = True
        for x in e["lead"] + e["trail"]:
            if x is not None and -0.4 <= x <= 1.4:
                a.axvline(x, color="k" if style == "-" else "C2", ls=style, lw=0.9,
                          label=lab if first else None)
                first = False
    for amp in pl["amp"]:
        if amp is not None:
            a.axhline(LEVEL * amp, color="0.5", ls=":", lw=0.8)
    a.set_xlim(-0.4, 1.4)
    a.set_xlabel("pipeline time (us)")
    a.set_ylabel("kV")
    a.set_title("Final C225 output trace. Dotted = 50% of each pulse's own peak")
    a.legend(fontsize=8, loc="best")

    fig.tight_layout()
    fig.savefig(os.path.join(HERE, f"shot_{n:04d}_baseline.png"), dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    main()
