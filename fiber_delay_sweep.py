"""
Fiber link delay, using the delay generator as the ruler instead of the scope.

The generator's programmed delay is a far better measuring standard than the
scope's timebase: digital, calibrated, picosecond resolution. So sweep it and
fit, rather than trusting one absolute reading.

    for each programmed delay D:  record the CH edge time t(D)
    fit                           t = slope * D + intercept

The SLOPE must come out at 1.000000. It is a free validity check that costs
nothing: it says you tracked the same edge the whole way and that the scope
timebase agrees with the generator. A slope off by more than ~100 ppm means
something is wrong with the measurement, not with the fiber.

The INTERCEPT is every fixed delay in the chain added together:

    intercept = d_gen + tau_long + d_TF1 + tau_fiber + d_X22 + tau_out
                + tau_trig + scope_offset

One sweep cannot separate those. d_gen, the generator's own insertion delay
at D = 0, is not knowable from the outside. So run the sweep TWICE, once with
the fiber in the path and once with it bypassed, and subtract the intercepts:

    intercept_fiber - intercept_direct = d_TF1 + tau_fiber + d_X22 + tau_out

Everything else is identical between the two runs and cancels exactly: the
generator's insertion delay, the 129 ns screen-room cable AND its 0.55 ns of
dispersion, the trigger path, the scope's -87.4 ns offset, the scope timebase.
The only term you have to supply is tau_out, the 1 ft cable from the X22.

That is why your TG-100 .s1p does not enter the arithmetic. It cancels. It is
still worth having, because it tells you the cable's 60 MHz bandwidth puts a
5.9 ns floor on the risetime arriving at the TF1, and that is the number that
decides whether the TF1 is being driven well enough for its delay to be
stable at all.

    python fiber_delay_sweep.py 192.168.10.51 4 sweep --label fiber \
        --delays 0,100,200,300,400 --shots 20
    python fiber_delay_sweep.py 192.168.10.51 4 sweep --label direct \
        --delays 0,100,200,300,400 --shots 20
    python fiber_delay_sweep.py solve --tau-out 1.54 --fiber-m 30
"""

import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, ".")

STORE = "fiber_sweep.json"

FIBER_NS_PER_M = 4.90
FIBER_NS_PER_M_RANGE = (4.85, 4.98)

# DG535 channel codes for the DT command. Not SCPI: the DG535 predates it.
DG_CHANNELS = {"T0": 0, "A": 1, "B": 2, "AB": 3, "C": 4, "D": 5, "CD": 6}


class ManualDelay:
    """No generator connection. Prompt the operator for each setting."""

    def __init__(self, channel):
        self.channel = channel

    def set(self, delay_ns):
        print(f"\n  >>> Set {self.channel} delay to {delay_ns:.4f} ns "
              f"({delay_ns*1e-9:.12f} s), then press Enter.")
        try:
            input()
        except EOFError:
            raise RuntimeError(
                "stdin closed, so manual mode cannot prompt. Pass --dg-visa "
                "to drive the generator directly.")

    def close(self):
        pass


class DG535:
    """DG535 over VISA. 'DT i,j,t' sets channel i's delay from j to t."""

    def __init__(self, resource, channel, ref="T0", timeout_ms=5000):
        import pyvisa
        self.rm = pyvisa.ResourceManager()
        self.instr = self.rm.open_resource(resource)
        self.instr.timeout = timeout_ms
        self.instr.read_termination = "\r\n"
        self.instr.write_termination = "\r\n"
        if channel not in DG_CHANNELS:
            raise ValueError(f"channel must be one of {sorted(DG_CHANNELS)}")
        self.i = DG_CHANNELS[channel]
        self.j = DG_CHANNELS[ref]
        self.channel = channel

    def set(self, delay_ns):
        self.instr.write(f"DT {self.i},{self.j},{delay_ns*1e-9:.12E}")
        time.sleep(0.15)
        try:
            back = float(self.instr.query(f"DT {self.i}").strip())
            err = (back - delay_ns * 1e-9) * 1e12
            if abs(err) > 50:
                print(f"    readback {back*1e9:.4f} ns differs from the "
                      f"request by {err:.0f} ps")
        except Exception:
            pass

    def close(self):
        try:
            self.instr.close(); self.rm.close()
        except Exception:
            pass


def load():
    return json.load(open(STORE)) if os.path.exists(STORE) else {}


def save(d):
    json.dump(d, open(STORE, "w"), indent=2)


def mean_edge(instr, ch, shots, rising, search):
    """Mean edge time over N shots, plus the diagnostics worth seeing."""
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
    if len(ts) < 2:
        return None
    a = np.array(ts)
    return {"mean": float(a.mean()), "sd": float(a.std(ddof=1)),
            "se": float(a.std(ddof=1) / np.sqrt(a.size)), "n": a.size,
            "amp": float(np.mean(amps)), "rt": float(np.mean(rts)),
            "nsamp": float(np.mean(ns)),
            "window": (float(t[0]), float(t[-1]))}


def do_sweep(instr, ch, args):
    from edge_timing import fit_delay_sweep

    delays = [float(x) for x in args.delays.split(",")]
    rising = not args.falling
    gen = (DG535(args.dg_visa, args.dg_channel) if args.dg_visa
           else ManualDelay(args.dg_channel))

    half = args.track_window / 2.0
    print(f"\nSweep '{args.label}' on CH{ch}, {len(delays)} delays, "
          f"{args.shots} shots each")
    print(f"  {'generator':<12}{args.dg_channel}"
          f"{'  (manual)' if not args.dg_visa else '  (VISA)'}")
    print(f"  {'edge':<12}{'rising' if rising else 'falling'}")
    print(f"  tracking the edge in a +/-{half:.0f} ns window around its "
          f"predicted position\n")
    print(f"  {'D (ns)':>9}{'edge (ns)':>14}{'jitter':>10}{'s.e.':>9}"
          f"{'amp':>8}{'rise':>8}{'smp':>6}")
    print("  " + "-" * 64)

    prog, meas, rows = [], [], []
    anchor = None
    try:
        for d in delays:
            gen.set(d)
            time.sleep(args.settle)

            if anchor is None:
                search = (tuple(np.array(args.search) * 1e-9)
                          if args.search else None)
            else:
                centre = anchor + (d - anchor_d) * 1e-9
                search = (centre - half * 1e-9, centre + half * 1e-9)

            r = mean_edge(instr, ch, args.shots, rising, search)
            if r is None:
                print(f"  {d:9.2f}   no edge found in the search window")
                continue
            if anchor is None:
                anchor, anchor_d = r["mean"], d
                w0, w1 = r["window"]
                span = (w1 - w0) * 1e9
                last = r["mean"] * 1e9 + (max(delays) - d)
                if last > w1 * 1e9:
                    print(f"\n  WARNING: at D={max(delays):.0f} ns the edge is "
                          f"predicted at {last:.0f} ns, past the\n  end of the "
                          f"{span:.0f} ns record. Widen the timebase or shorten "
                          f"the sweep.\n")

            prog.append(d * 1e-9); meas.append(r["mean"]); rows.append((d, r))
            print(f"  {d:9.2f}{r['mean']*1e9:13.4f} "
                  f"{r['sd']*1e12:8.0f} ps{r['se']*1e12:7.1f} ps"
                  f"{r['amp']:7.2f} V{r['rt']*1e9:7.2f}n{r['nsamp']:6.1f}")
    finally:
        gen.close()

    if len(prog) < 2:
        print("\nNeed at least two good points.")
        return 1

    fit = fit_delay_sweep(prog, meas)
    ppm = fit["timebase_error_ppm"]
    print(f"\n  {'points':<22}{fit['n']}")
    print(f"  {'slope':<22}{fit['slope']:.7f}   ({ppm:+.0f} ppm from 1)")
    print(f"  {'intercept':<22}{fit['offset']*1e9:+.4f} ns")
    print(f"  {'fit residual rms':<22}{fit['residual_rms']*1e12:.1f} ps")
    print(f"  {'worst residual':<22}{fit['residual_max']*1e12:.1f} ps")

    se_int = fit["residual_rms"] / np.sqrt(max(fit["n"] - 2, 1))
    print(f"  {'intercept s.e.':<22}{se_int*1e12:.1f} ps")

    if abs(ppm) > 100:
        print(f"\n  SLOPE IS WRONG. {ppm:+.0f} ppm is far more than a scope "
              f"timebase error.\n  Most likely you tracked onto a different "
              f"edge partway through, or the\n  generator did not take one of "
              f"the settings. The intercept is not usable\n  until the slope "
              f"reads 1.000.")
    elif abs(ppm) > 30:
        print(f"\n  Slope is {ppm:+.0f} ppm off. Larger than a DS7054 timebase "
              f"spec, so worth\n  a second look, but the intercept is probably "
              f"still sound.")
    else:
        print(f"\n  Slope is clean. You tracked one edge the whole way and the "
              f"scope\n  timebase agrees with the generator to {abs(ppm):.0f} "
              f"ppm.")

    d = load()
    d[args.label] = {"slope": fit["slope"], "intercept_s": fit["offset"],
                     "intercept_se_s": se_int,
                     "resid_rms_s": fit["residual_rms"], "n": fit["n"],
                     "channel": ch, "rising": rising,
                     "amp_v": float(np.mean([r["amp"] for _, r in rows])),
                     "rt_s": float(np.mean([r["rt"] for _, r in rows])),
                     "jitter_s": float(np.mean([r["sd"] for _, r in rows])),
                     "delays_ns": [dd for dd, _ in rows]}
    save(d)
    print(f"  saved as '{args.label}' in {STORE}")
    return 0


def do_solve(args):
    d = load()
    for k in (args.fiber, args.direct):
        if k not in d:
            print(f"No sweep called '{k}' in {STORE}. Have: {sorted(d)}")
            return 1
    F, D = d[args.fiber], d[args.direct]

    print("ONE-WAY TRANSIT, TF1 + FIBER + X22")
    print("=" * 68)
    print(f"  {'sweep':<12}{'slope':>12}{'intercept':>15}{'s.e.':>9}"
          f"{'resid':>9}{'amp':>8}")
    print("  " + "-" * 66)
    for name, r in ((args.fiber, F), (args.direct, D)):
        print(f"  {name:<12}{r['slope']:12.7f}{r['intercept_s']*1e9:12.4f} ns"
              f"{r['intercept_se_s']*1e12:6.1f} ps"
              f"{r['resid_rms_s']*1e12:6.0f} ps{r['amp_v']:7.2f} V")

    bad = [n for n, r in ((args.fiber, F), (args.direct, D))
           if abs((r["slope"] - 1) * 1e6) > 100]
    if bad:
        print(f"\n  STOP: the slope on {', '.join(bad)} is more than 100 ppm "
              f"from 1.\n  Re-take that sweep before believing the answer "
              f"below.")

    raw = F["intercept_s"] - D["intercept_s"]
    link = raw - args.tau_out * 1e-9
    u = np.sqrt(F["intercept_se_s"]**2 + D["intercept_se_s"]**2
                + (args.tau_out_se * 1e-12)**2)

    print(f"\n  intercept difference  {raw*1e9:12.4f} ns")
    print(f"  minus the 1 ft cable  {-args.tau_out:12.4f} ns")
    print("  " + "-" * 38)
    print(f"  LINK DELAY            {link*1e9:12.4f} ns  +/- {u*1e12:.0f} ps")

    print(f"\n  Cancelled by the subtraction, so never needed: the generator's")
    print(f"  insertion delay, the 129 ns screen-room cable and its 0.55 ns of")
    print(f"  dispersion, the trigger path, the scope's -87.4 ns offset, and")
    print(f"  the scope timebase.")

    if args.fiber_m:
        tf = args.fiber_m * FIBER_NS_PER_M
        lo = args.fiber_m * FIBER_NS_PER_M_RANGE[0]
        hi = args.fiber_m * FIBER_NS_PER_M_RANGE[1]
        el = link * 1e9 - tf
        print(f"\n  SPLIT, using {args.fiber_m:.1f} m of 62.5/125 fiber")
        print("  " + "-" * 52)
        print(f"  fiber at {FIBER_NS_PER_M:.2f} ns/m   {tf:10.2f} ns"
              f"   (range {lo:.1f} to {hi:.1f})")
        print(f"  electronics, implied  {el:10.2f} ns   "
              f"(datasheet max 40)")
        if el > 40:
            print(f"\n  {el-40:.1f} ns over the datasheet maximum. The fiber is "
                  f"longer than\n  {args.fiber_m:.1f} m, or the drive is near "
                  f"threshold, or the two sweeps are not\n  on corresponding "
                  f"edges.")
        elif el < 0:
            print(f"\n  Negative is impossible. The fiber length is wrong, or "
                  f"the two sweeps\n  are not on corresponding edges.")
        else:
            print(f"\n  Within the datasheet bound. The fiber LENGTH now "
                  f"dominates: at 1 m of\n  length error that is "
                  f"{FIBER_NS_PER_M:.1f} ns. To do better, sweep the link twice "
                  f"with two\n  known fiber lengths and take the slope, which "
                  f"gives the group index\n  directly and drops the length "
                  f"guess entirely.")

    print(f"\n  Per-shot jitter through the fiber path is "
          f"{F['jitter_s']*1e12:.0f} ps rms against\n  "
          f"{D['jitter_s']*1e12:.0f} ps on the direct path. The difference is "
          f"the X22, spec'd under 1 ns.\n  It is random per shot, so no "
          f"calibration removes it.")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ip", nargs="?")
    ap.add_argument("channel", nargs="?", type=int)
    sub = ap.add_subparsers(dest="cmd")

    sp = sub.add_parser("sweep", help="sweep the generator, fit, save")
    sp.add_argument("--label", required=True, help="fiber or direct")
    sp.add_argument("--delays", default="0,100,200,300,400",
                    help="comma-separated programmed delays, ns")
    sp.add_argument("--shots", type=int, default=20,
                    help="shots averaged per delay point")
    sp.add_argument("--dg-visa",
                    help="VISA resource for the generator. Omit to be prompted")
    sp.add_argument("--dg-channel", default="A",
                    help="generator channel being delayed (A, B, C, D)")
    sp.add_argument("--falling", action="store_true")
    sp.add_argument("--search", nargs=2, type=float, metavar=("LO", "HI"),
                    help="window for the FIRST point only, ns. Later points "
                         "are tracked automatically")
    sp.add_argument("--track-window", type=float, default=30.0,
                    help="width of the tracking window, ns")
    sp.add_argument("--settle", type=float, default=0.3,
                    help="seconds to wait after setting a delay")

    sp = sub.add_parser("solve", help="difference the two intercepts")
    sp.add_argument("--fiber", default="fiber")
    sp.add_argument("--direct", default="direct")
    sp.add_argument("--tau-out", type=float, required=True,
                    help="X22-to-scope cable delay, ns (1 ft RG-58 = 1.54)")
    sp.add_argument("--tau-out-se", type=float, default=150.0,
                    help="its uncertainty, ps. 150 if you estimated it")
    sp.add_argument("--fiber-m", type=float, help="fiber length, m")

    args = ap.parse_args()

    if args.cmd == "solve":
        return do_solve(args)
    if not args.cmd:
        ap.print_help()
        return 1
    if not args.ip or args.channel is None:
        print("Need IP and channel for sweep.")
        return 1

    from calibrate_channel import connect
    rm, instr, res = connect(args.ip, socket=True)
    try:
        print(instr.query("*IDN?").strip())
        print(f"via {res}")
        for q, label in ((":TRIGger:SWEep?", "trigger sweep"),
                         (":TRIGger:EDGE:SOURce?", "trigger source"),
                         (":TIMebase:MAIN:SCALe?", "timebase s/div"),
                         (":TIMebase:MAIN:OFFSet?", "timebase offset"),
                         (":ACQuire:MDEPth?", "memory depth"),
                         (f":CHANnel{args.channel}:IMPedance?", "impedance")):
            try:
                print(f"  {label:<18} {instr.query(q).strip()}")
            except Exception:
                pass
        return do_sweep(instr, args.channel, args)
    finally:
        try:
            instr.close(); rm.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
