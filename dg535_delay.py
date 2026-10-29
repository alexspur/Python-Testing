"""
DG535 insertion delay and jitter, relative to its own EXT TRIG input.

Why the scope can see this at all: the scope's EXT trigger and the DG535's
EXT TRIG input are both fed from BNC575 channel A. So when channel A jitters,
the scope's t=0 and the DG535's output move TOGETHER and the common part
cancels. The record therefore measures the DG535's output against its own
input, which is exactly what you asked for, with no tee anywhere.

Two modes.

  single    DG535 output -> a calibrated scope channel through a measured
            cable. Uses the September EXT trigger calibration as the time
            reference, so it gives the absolute d_DG. The scatter contains
            the scope's trigger comparator as well as the DG535, so the
            DG535's own jitter comes out by quadrature subtraction against
            --baseline-jitter.

  diff      DG535 output on one channel, a DIRECT BNC575 output on another,
            both read from the SAME acquisition. The scope's trigger jitter
            shifts both channels equally and cancels exactly, so the residual
            scatter is the DG535 alone. Best jitter number, and it needs a
            spare BNC575 output and a second channel.

Both sweep the programmed delay rather than taking one point, because:
  - the SLOPE must be 1.000000, which checks the DG535's timebase against the
    scope's and catches a mistracked edge
  - the INTERCEPT is d_DG, and many points beat one
  - generators of this class specify jitter as a fixed floor PLUS a term
    proportional to the delay setting, so jitter-versus-delay is a real
    measurement and the sweep gives it for free

    python dg535_delay.py 192.168.10.51 4 single --tau-cable 1.54 \\
        --delays 0,200,500,1000,2000 --shots 50
    python dg535_delay.py 192.168.10.51 4 diff --ref-channel 3 \\
        --tau-cable 1.54 --tau-ref 4.599 --delays 0,200,500,1000,2000
"""

import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, ".")

STORE = "dg535_delay.json"
CAL = "timing_cal.json"

TAU_BNC_TO_DG = 1.455      # BNC575 chA -> DG535 EXT TRIG, measured
CH3_CH4_SKEW = -0.0176     # measured CH3 - CH4 front-end skew, scope 1, ns
SCOPE_BASELINE_JITTER = 208.4   # ps, scope 1 CH4, September calibration


def load_cal(path=CAL):
    if not os.path.exists(path):
        return {}, {}
    d = json.load(open(path))
    return d.get("trig_delay", {}), d.get("offset", {})


def mean_edge(instr, ch, shots, rising, search, probe_reach=None):
    """Mean and rms of the edge time over N shots."""
    from calibrate_channel import one_shot
    from edge_timing import edge_stats
    ts, amps, rts, ns = [], [], [], []
    for _ in range(shots):
        t, v = one_shot(instr, ch)
        kw = {"rising": rising}
        if search:
            kw["search"] = search
        st = edge_stats(t, v, **kw)
        if not np.isfinite(st["edge_time"]):
            continue
        ts.append(st["edge_time"]); amps.append(st["amplitude"])
        rts.append(st["risetime_20_80"]); ns.append(st["samples_on_edge"])
    if len(ts) < 3:
        return None
    a = np.array(ts)
    return {"mean": float(a.mean()), "sd": float(a.std(ddof=1)),
            "se": float(a.std(ddof=1) / np.sqrt(a.size)), "n": a.size,
            "amp": float(np.mean(amps)), "rt": float(np.mean(rts)),
            "nsamp": float(np.mean(ns))}


def pair_edges(instr, ch_a, ch_b, shots, rising, sa, sb):
    """Same-shot difference. Arms once, reads both channels from that shot."""
    from calibrate_channel import arm_and_wait, read_channel
    from edge_timing import edge_stats
    da, db, dd, amps = [], [], [], []
    for _ in range(shots):
        arm_and_wait(instr)
        ta, va = read_channel(instr, ch_a)
        tb, vb = read_channel(instr, ch_b)
        ka = {"rising": rising}; kb = {"rising": rising}
        if sa: ka["search"] = sa
        if sb: kb["search"] = sb
        ea = edge_stats(ta, va, **ka)
        eb = edge_stats(tb, vb, **kb)
        if not (np.isfinite(ea["edge_time"]) and np.isfinite(eb["edge_time"])):
            continue
        da.append(ea["edge_time"]); db.append(eb["edge_time"])
        dd.append(ea["edge_time"] - eb["edge_time"])
        amps.append((ea["amplitude"], eb["amplitude"]))
    if len(dd) < 3:
        return None
    A, B, D = np.array(da), np.array(db), np.array(dd)
    return {"mean": float(D.mean()), "sd": float(D.std(ddof=1)),
            "se": float(D.std(ddof=1) / np.sqrt(D.size)), "n": D.size,
            "sd_a": float(A.std(ddof=1)), "sd_b": float(B.std(ddof=1)),
            "amp": float(np.mean([x[0] for x in amps])),
            "amp_ref": float(np.mean([x[1] for x in amps])), "rt": float("nan"),
            "nsamp": float("nan")}


def jitter_model(prog_ns, sd_ps):
    """Fit jitter = floor + k * delay, the usual form for this class of box."""
    p = np.asarray(prog_ns, float); s = np.asarray(sd_ps, float)
    if p.size < 3 or np.ptp(p) == 0:
        return None
    k, floor = np.polyfit(p, s, 1)
    pred = k * p + floor
    return {"floor_ps": float(floor), "slope_ps_per_ns": float(k),
            "ppm": float(k * 1e6 / 1e3), "resid_ps": float(np.std(s - pred))}


def run(instr, args):
    from edge_timing import fit_delay_sweep
    from fiber_delay_sweep import DG535, ManualDelay

    delays = [float(x) for x in args.delays.split(",")]
    rising = not args.falling
    gen = (DG535(args.dg_visa, args.dg_channel) if args.dg_visa
           else ManualDelay(args.dg_channel))
    half = args.track_window / 2.0
    diff = args.cmd == "diff"

    print(f"\nDG535 output {args.dg_channel} -> CH{args.channel}"
          + (f", reference BNC575 -> CH{args.ref_channel}" if diff else ""))
    print(f"  mode            {'same-shot difference' if diff else 'single channel vs calibrated t=0'}")
    print(f"  delays          {len(delays)} points, {args.shots} shots each")
    print(f"  edge            {'rising' if rising else 'falling'}\n")
    hdr = "difference" if diff else "edge time"
    print(f"  {'D (ns)':>9}{hdr:>16}{'jitter':>10}{'s.e.':>9}{'amp':>8}")
    print("  " + "-" * 54)

    prog, meas, sds, rows = [], [], [], []
    anchor = anchor_d = None
    try:
        for d in delays:
            gen.set(d)
            time.sleep(args.settle)

            if anchor is None:
                sa = tuple(np.array(args.search) * 1e-9) if args.search else None
            else:
                c = anchor + (d - anchor_d) * 1e-9
                sa = (c - half * 1e-9, c + half * 1e-9)
            sb = (tuple(np.array(args.ref_search) * 1e-9)
                  if args.ref_search else None)

            r = (pair_edges(instr, args.channel, args.ref_channel,
                            args.shots, rising, sa, sb) if diff
                 else mean_edge(instr, args.channel, args.shots, rising, sa))
            if r is None:
                print(f"  {d:9.2f}   no usable edge")
                continue
            if anchor is None:
                anchor, anchor_d = (r["mean"] if not diff else
                                    r["mean"] + (sb[0] if sb else 0)), d
                if diff:
                    anchor = None  # difference does not track; needs ref_search
            prog.append(d); meas.append(r["mean"]); sds.append(r["sd"] * 1e12)
            rows.append((d, r))
            print(f"  {d:9.2f}{r['mean']*1e9:14.4f} n{r['sd']*1e12:8.0f} ps"
                  f"{r['se']*1e12:7.1f} ps{r['amp']:7.2f} V")
    finally:
        gen.close()

    if len(prog) < 2:
        print("\nNeed at least two good points.")
        return 1

    fit = fit_delay_sweep(np.array(prog) * 1e-9, meas)
    ppm = fit["timebase_error_ppm"]
    se_int = fit["residual_rms"] / np.sqrt(max(fit["n"] - 2, 1))

    print(f"\n  {'points':<24}{fit['n']}")
    print(f"  {'slope':<24}{fit['slope']:.7f}  ({ppm:+.0f} ppm)")
    print(f"  {'intercept':<24}{fit['offset']*1e9:+.4f} ns  "
          f"+/- {se_int*1e12:.0f} ps")
    print(f"  {'fit residual rms':<24}{fit['residual_rms']*1e12:.1f} ps")

    if abs(ppm) > 100:
        print(f"\n  SLOPE IS WRONG at {ppm:+.0f} ppm. Either the DG535 did not "
              f"take a setting or\n  the fit moved to a different edge. "
              f"d_DG below is not usable.")
    elif abs(ppm) > 30:
        print(f"\n  Slope {ppm:+.0f} ppm off, larger than a DS7054 timebase "
              f"spec but small enough\n  that the intercept is probably sound. "
              f"That residual is the DG535's\n  timebase against the scope's.")
    else:
        print(f"\n  Slope clean to {abs(ppm):.0f} ppm. The DG535's timebase and "
              f"the scope's agree,\n  and one edge was tracked throughout.")

    # ---- d_DG --------------------------------------------------------
    print(f"\n\n  INSERTION DELAY")
    print("  " + "=" * 54)
    if diff:
        d_dg = (fit["offset"] * 1e9 - args.tau_cable + args.tau_ref
                + args.skew)
        print(f"  intercept (CH{args.channel} - CH{args.ref_channel})"
              f"{fit['offset']*1e9:14.4f} ns")
        print(f"  minus DG535 output cable      {-args.tau_cable:10.4f} ns")
        print(f"  plus reference cable          {args.tau_ref:+10.4f} ns")
        print(f"  plus CH-to-CH skew            {args.skew:+10.4f} ns")
    else:
        trig, off = load_cal(args.cal)
        key = f"{args.scope}/{args.channel}"
        if key not in off:
            print(f"  No calibration for {key} in {args.cal}. Cannot give an "
                  f"absolute d_DG.\n  The slope and jitter above still stand.")
            return 0
        o = off[key] * 1e9; tt = trig[str(args.scope)] * 1e9
        T = o + tt + fit["offset"] * 1e9 - args.tau_cable
        d_dg = T - TAU_BNC_TO_DG
        print(f"  scope offset                  {o:10.4f} ns")
        print(f"  trigger path                  {tt:+10.4f} ns")
        print(f"  intercept                     {fit['offset']*1e9:+10.4f} ns")
        print(f"  minus DG535 output cable      {-args.tau_cable:10.4f} ns")
        print(f"  = T0 to DG535 output          {T:10.4f} ns")
        print(f"  minus BNC575 chA to ext trig  {-TAU_BNC_TO_DG:10.4f} ns")
    print("  " + "-" * 44)
    print(f"  d_DG                          {d_dg:10.4f} ns")

    if not 0 < d_dg < 500:
        print(f"\n  {d_dg:.1f} ns is not plausible for a DG535. Check the cable "
              f"delays and that\n  you timed the edge you meant to.")

    # ---- jitter ------------------------------------------------------
    print(f"\n\n  JITTER")
    print("  " + "=" * 54)
    sd_arr = np.array(sds)
    if diff:
        a_sd = np.mean([r["sd_a"] for _, r in rows]) * 1e12
        b_sd = np.mean([r["sd_b"] for _, r in rows]) * 1e12
        print(f"  CH{args.channel} alone                     {a_sd:8.0f} ps rms")
        print(f"  CH{args.ref_channel} alone                     {b_sd:8.0f} ps rms")
        print(f"  same-shot difference          {sd_arr.mean():8.0f} ps rms")
        if sd_arr.mean() < min(a_sd, b_sd):
            print(f"\n  The difference is quieter than either channel, by "
                  f"{min(a_sd,b_sd)/sd_arr.mean():.1f}x. That is\n  the scope's "
                  f"trigger jitter cancelling, which is the proof the "
                  f"same-shot\n  method is working. What is left is the DG535.")
        else:
            print(f"\n  WARNING: the difference is NOT quieter than the "
                  f"individual channels.\n  Something is adding independent "
                  f"noise per channel. Check both\n  amplitudes and that each "
                  f"search window holds a real edge.")
        dg_jit = sd_arr.mean()
    else:
        tot = sd_arr.mean()
        base = args.baseline_jitter
        print(f"  measured, total               {tot:8.0f} ps rms")
        print(f"  scope baseline (September)    {base:8.0f} ps rms")
        if tot > base:
            dg_jit = np.sqrt(tot**2 - base**2)
            print(f"  quadrature difference         {dg_jit:8.0f} ps rms")
            print(f"\n  That is the DG535's contribution, assuming the two are "
                  f"independent.\n  It is an estimate, not a measurement: run "
                  f"`diff` for the real number.")
        else:
            dg_jit = float("nan")
            print(f"\n  The total is at or below the scope baseline, so the "
                  f"DG535's jitter is\n  buried. All you can say is that it is "
                  f"under about {base:.0f} ps.")

    jm = jitter_model(prog, sds)
    if jm:
        print(f"\n  JITTER vs DELAY SETTING")
        print("  " + "-" * 54)
        print(f"  {'D (ns)':>10}{'jitter (ps)':>14}")
        for d, s in zip(prog, sds):
            print(f"  {d:10.0f}{s:14.0f}")
        print(f"\n  fixed floor                   {jm['floor_ps']:8.0f} ps")
        print(f"  growth with delay             "
              f"{jm['slope_ps_per_ns']*1000:8.1f} ps per us")
        print(f"  scatter about the fit         {jm['resid_ps']:8.0f} ps")
        if jm["slope_ps_per_ns"] * 1000 > 20:
            print(f"\n  Jitter grows measurably with the delay setting, which "
                  f"is the normal\n  shape for this class of generator: a fixed "
                  f"floor plus a term\n  proportional to the delay. At your "
                  f"campaign delay the jitter is the\n  floor plus "
                  f"{jm['slope_ps_per_ns']*1000:.0f} ps per microsecond, so "
                  f"quote it at the delay you actually use.")
        else:
            print(f"\n  No significant growth with delay over this range, so "
                  f"the floor is the\n  whole story here.")

    if np.isfinite(dg_jit):
        print(f"\n\n  WHAT THIS MEANS FOR THE FIBER PATH")
        print("  " + "=" * 54)
        x22 = 1000.0
        tot = np.sqrt(dg_jit**2 + x22**2)
        print(f"  DG535                         {dg_jit:8.0f} ps rms")
        print(f"  X22, datasheet bound          {x22:8.0f} ps rms")
        print(f"  in quadrature                 {tot:8.0f} ps rms")
        print(f"\n  The X22 dominates at {100*x22**2/tot**2:.0f}% of the "
              f"variance. Improving the DG535\n  would buy you almost nothing "
              f"until the converter is dealt with.")

    d = load()
    d[args.label] = {"mode": args.cmd, "slope": fit["slope"],
                     "intercept_ns": fit["offset"] * 1e9,
                     "intercept_se_ps": se_int * 1e12, "d_dg_ns": float(d_dg),
                     "jitter_ps": float(np.mean(sds)),
                     "dg_jitter_ps": float(dg_jit) if np.isfinite(dg_jit) else None,
                     "delays_ns": prog, "jitters_ps": sds}
    save(d)
    print(f"\n  saved as '{args.label}' in {STORE}")
    print(f"\n  Feed it back with:")
    print(f"    python fiber_from_cal.py account --t-rec <fiber run> "
          f"--d-dg {d_dg:.4f}")
    return 0


def load():
    return json.load(open(STORE)) if os.path.exists(STORE) else {}


def save(d):
    json.dump(d, open(STORE, "w"), indent=2)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ip")
    ap.add_argument("channel", type=int, help="channel carrying the DG535 output")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--tau-cable", type=float, required=True,
                       help="DG535-output-to-scope cable delay, ns")
        p.add_argument("--delays", default="0,200,500,1000,2000",
                       help="programmed delays to sweep, ns")
        p.add_argument("--shots", type=int, default=50,
                       help="shots per delay point. 50 gives a 10%% rms estimate")
        p.add_argument("--label", default=None)
        p.add_argument("--scope", default="1")
        p.add_argument("--cal", default=CAL)
        p.add_argument("--dg-visa", help="VISA resource. Omit to be prompted")
        p.add_argument("--dg-channel", default="A",
                       help="DG535 output being swept. Use the one you really use")
        p.add_argument("--falling", action="store_true")
        p.add_argument("--search", nargs=2, type=float, metavar=("LO", "HI"),
                       help="edge window for the FIRST delay point, ns")
        p.add_argument("--track-window", type=float, default=40.0)
        p.add_argument("--settle", type=float, default=0.3)

    p = sub.add_parser("single", help="against the calibrated scope t=0")
    common(p)
    p.add_argument("--baseline-jitter", type=float,
                   default=SCOPE_BASELINE_JITTER,
                   help="scope's own jitter, ps, for quadrature subtraction")

    p = sub.add_parser("diff", help="same-shot against a direct BNC575 output")
    common(p)
    p.add_argument("--ref-channel", type=int, required=True)
    p.add_argument("--tau-ref", type=float, required=True,
                   help="BNC575-to-reference-channel cable delay, ns")
    p.add_argument("--ref-search", nargs=2, type=float, metavar=("LO", "HI"))
    p.add_argument("--skew", type=float, default=CH3_CH4_SKEW,
                   help="channel-to-channel skew, ns, measured")
    p.add_argument("--baseline-jitter", type=float,
                   default=SCOPE_BASELINE_JITTER)

    args = ap.parse_args()
    if args.label is None:
        args.label = args.cmd
    if args.cmd == "single":
        args.ref_channel = None
        args.ref_search = None

    from calibrate_channel import connect
    rm, instr, res = connect(args.ip, socket=True)
    try:
        print(instr.query("*IDN?").strip())
        print(f"via {res}")
        for q, label in ((":TRIGger:SWEep?", "trigger sweep"),
                         (":TRIGger:EDGE:SOURce?", "trigger source"),
                         (":TIMebase:MAIN:SCALe?", "timebase s/div"),
                         (":ACQuire:MDEPth?", "memory depth"),
                         (f":CHANnel{args.channel}:IMPedance?", "impedance"),
                         (f":CHANnel{args.channel}:SCALe?", "V/div")):
            try:
                print(f"  {label:<18} {instr.query(q).strip()}")
            except Exception:
                pass
        return run(instr, args)
    finally:
        try:
            instr.close(); rm.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
