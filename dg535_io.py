"""
DG535 insertion delay and jitter, by moving one cable between input and output.

Geometry this assumes, which is the one you have wired:

    CH3   a fixed fiducial. Any output that fires every shot. Never moved.
    CH4   moved between two places, using the SAME cable both times:
            run "input"   the cross at the DG535 EXT TRIG connector
            run "output"  the DG535 output you actually use

Both channels are read from ONE acquisition per shot, so the scope's trigger
jitter shifts them together and cancels in the difference. Then:

    dt_input  = t_CH4(at the ext trig connector) - t_CH3
    dt_output = t_CH4(at the DG535 output)       - t_CH3

    d_DG = (dt_output - dt_input) - D_programmed

Because the same cable carries CH4 in both runs, its delay cancels. So does
CH3's path, the CH3-to-CH4 front-end skew, the scope's -87.47 ns offset, the
1.455 ns cable from BNC575, and BNC575's own timing. None of them has to be
known, which is why this is better than referencing the calibration.

The jitter falls out the same way. The input run has no DG535 in the path, so
its scatter is your measured baseline: scope comparator plus edge fit plus
CH3. The output run adds the DG535 on top. So

    sigma_DG = sqrt(sigma_output^2 - sigma_input^2)

with a baseline you measured rather than one assumed.

TERMINATION. The cross at the ext trig input must present 50 ohms in BOTH
runs, and that 50 ohms must be the same as in normal operation, or the
DG535's comparator fires at a different point on the edge and d_DG is not
the number you run with. With the DG535's ext trig input high-impedance:

    input run    BNC575 in, DG535 ext trig, cable to CH4. NO terminator:
                 the scope's own 50 ohm input is the termination.
    output run   BNC575 in, DG535 ext trig, 50 ohm terminator where the CH4
                 cable was.

Leaving the terminator on during the input run puts a terminator AND a
terminated cable on the cross in parallel, which is 25 ohms, reflects a
third of the edge and drops the DG535's input to two thirds amplitude.

    python dg535_io.py 192.168.10.51 survey
    python dg535_io.py 192.168.10.51 run --label input  --shots 50 \\
        --search 440 500 --ref-search 440 500
    python dg535_io.py 192.168.10.51 run --label output --shots 50 \\
        --dg-prog 0 --search LO HI --ref-search 440 500
    python dg535_io.py 192.168.10.51 solve

Fired from the BNC 575 rather than waiting for an outside trigger. "3" is
scope 3 (192.168.10.53). Each shot arms the scope, then fires the 575:
    python dg535_io.py 3 survey --bnc COM5
    python dg535_io.py 3 run --label input --shots 50 --bnc COM5 \\
        --search 440 500 --ref-search 440 500
"""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, ".")

STORE = "dg535_io.json"


def load():
    return json.load(open(STORE)) if os.path.exists(STORE) else {}


def save(d):
    json.dump(d, open(STORE, "w"), indent=2)


def shot_pair(instr, ch_a, ch_b, fire=None):
    """One acquisition, both channels. Re-arming between them would put a
    fresh dose of trigger jitter in each and the difference would stop
    cancelling, which is the entire point.

    fire, if given, fires the BNC 575 once the scope is armed. A shot with
    no trigger then raises TimeoutError after 5 s instead of waiting 30."""
    from calibrate_channel import arm_and_wait, read_channel
    arm_and_wait(instr, 5.0 if fire else 30.0, fire=fire)
    ta, va = read_channel(instr, ch_a)
    tb, vb = read_channel(instr, ch_b)
    return (ta, va), (tb, vb)


def do_survey(instr, a, fire=None):
    from fiber_transit import multi_edges
    print()
    for ch in (a.channel, a.ref_channel):
        (t, v), _ = shot_pair(instr, ch, ch, fire)
        edges, info = multi_edges(t, v, max_report=12)
        print(f"CH{ch}")
        print(f"  record    {t[0]*1e9:+.0f} to {t[-1]*1e9:+.0f} ns at "
              f"{(t[1]-t[0])*1e12:.0f} ps")
        print(f"  baseline  {info.get('baseline', 0):+.3f} V, noise "
              f"{info.get('noise_rms', 0)*1e3:.1f} mV, reach "
              f"{info.get('reach', 0):.3f} V {info.get('polarity', '?')}-going")
        if not edges:
            print(f"  NO PULSE: {info.get('reason', '')}\n")
            continue
        for te, d, amp in edges:
            print(f"    {te*1e9:11.2f} ns  {d:<9} {amp:.3f} V")
        r = [e for e in edges if e[1] == "rising"]
        if r:
            print(f"  -> --{'' if ch == a.channel else 'ref-'}search "
                  f"{r[0][0]*1e9-20:.0f} {r[0][0]*1e9+20:.0f}")
        print()
    print("Pick one edge per channel. They do NOT have to be the same edge or")
    print("even the same time: only the difference's stability matters, and a")
    print("constant offset between them cancels when you subtract the two runs.")
    return 0


def do_run(instr, a, fire=None):
    from edge_timing import edge_stats
    rising = not a.falling
    sa = tuple(np.array(a.search) * 1e-9) if a.search else None
    sb = tuple(np.array(a.ref_search) * 1e-9) if a.ref_search else None

    print(f"\nRun '{a.label}', {a.shots} shots, CH{a.channel} against "
          f"CH{a.ref_channel}")
    if a.label == "input":
        print(f"  CH{a.channel} cable should be on the TEE at the DG535 EXT TRIG "
              f"input,")
        print("  with NO 50 ohm terminator on the tee.")
    elif a.label == "output":
        print(f"  CH{a.channel} cable should be on the DG535 OUTPUT, programmed "
              f"delay {a.dg_prog:.1f} ns,")
        print("  with the 50 ohm terminator on the open side of the tee.")
    print()

    ds, as_, bs, amps = [], [], [], []
    for i in range(a.shots):
        try:
            (ta, va), (tb, vb) = shot_pair(instr, a.channel, a.ref_channel, fire)
        except TimeoutError as e:
            if not fire:
                raise
            print(f"  shot {i+1:4d}: missed ({e})")
            continue
        ka = {"rising": rising}; kb = {"rising": rising}
        if sa: ka["search"] = sa
        if sb: kb["search"] = sb
        ea = edge_stats(ta, va, **ka)
        eb = edge_stats(tb, vb, **kb)
        if not (np.isfinite(ea["edge_time"]) and np.isfinite(eb["edge_time"])):
            print(f"  shot {i+1:4d}: no edge on one or both channels")
            continue
        as_.append(ea["edge_time"]); bs.append(eb["edge_time"])
        ds.append(ea["edge_time"] - eb["edge_time"])
        amps.append((ea["amplitude"], eb["amplitude"]))
        if i == 0 or (i + 1) % 10 == 0 or i == a.shots - 1:
            print(f"  shot {i+1:4d}: CH{a.channel} {ea['edge_time']*1e9:10.4f}  "
                  f"CH{a.ref_channel} {eb['edge_time']*1e9:10.4f}  "
                  f"diff {(ea['edge_time']-eb['edge_time'])*1e9:+10.4f} ns")

    if len(ds) < 3:
        print("\nNot enough good shots.")
        return 1

    A, B, D = np.array(as_), np.array(bs), np.array(ds)
    amp_a = float(np.mean([x[0] for x in amps]))
    amp_b = float(np.mean([x[1] for x in amps]))

    print(f"\n  {'':<24}{'mean':>14}{'rms':>12}")
    print("  " + "-" * 50)
    print(f"  {'CH'+str(a.channel):<24}{A.mean()*1e9:11.4f} ns"
          f"{A.std(ddof=1)*1e12:9.0f} ps")
    print(f"  {'CH'+str(a.ref_channel):<24}{B.mean()*1e9:11.4f} ns"
          f"{B.std(ddof=1)*1e12:9.0f} ps")
    print(f"  {'difference':<24}{D.mean()*1e9:11.4f} ns"
          f"{D.std(ddof=1)*1e12:9.0f} ps")
    print(f"\n  amplitudes: CH{a.channel} {amp_a:.3f} V, "
          f"CH{a.ref_channel} {amp_b:.3f} V")

    common = min(A.std(ddof=1), B.std(ddof=1))
    if D.std(ddof=1) < common:
        print(f"\n  Trigger jitter cancelled: the difference is "
              f"{common/D.std(ddof=1):.1f}x quieter than\n  either channel "
              f"alone. That is the same-shot method working.")
    else:
        print(f"\n  WARNING: the difference is NOT quieter than the individual "
              f"channels.\n  Independent noise per channel, so check both "
              f"amplitudes and that each\n  search window holds a real edge.")

    d = load()
    key = a.label if a.label != "output" else f"output@{a.dg_prog:g}"
    d[key] = {"mean_ns": float(D.mean() * 1e9),
              "sd_ps": float(D.std(ddof=1) * 1e12),
              "se_ps": float(D.std(ddof=1) / np.sqrt(D.size) * 1e12),
              "n": int(D.size), "dg_prog_ns": a.dg_prog,
              "amp_ch": amp_a, "amp_ref": amp_b,
              "sd_ch_ps": float(A.std(ddof=1) * 1e12),
              "sd_ref_ps": float(B.std(ddof=1) * 1e12)}
    save(d)
    print(f"\n  saved as '{key}' in {STORE}")
    return 0


def do_solve(a):
    d = load()
    if "input" not in d:
        print(f"No 'input' run in {STORE}. Have: {sorted(d)}")
        return 1
    outs = sorted([k for k in d if k.startswith("output@")],
                  key=lambda k: d[k]["dg_prog_ns"])
    if not outs:
        print(f"No 'output@...' runs in {STORE}. Have: {sorted(d)}")
        return 1

    I = d["input"]
    print("DG535 INSERTION DELAY, FROM THE INPUT-TO-OUTPUT DIFFERENCE")
    print("=" * 70)
    print(f"  input run   dt = {I['mean_ns']:+10.4f} ns   "
          f"+/- {I['se_ps']:.1f} ps   jitter {I['sd_ps']:.0f} ps")
    print()
    print(f"  {'D (ns)':>9}{'dt_output':>14}{'d_DG':>12}{'s.e.':>9}"
          f"{'jitter':>10}")
    print("  " + "-" * 56)

    progs, ddgs, jit = [], [], []
    for k in outs:
        O = d[k]
        ddg = O["mean_ns"] - I["mean_ns"] - O["dg_prog_ns"]
        se = np.sqrt(O["se_ps"] ** 2 + I["se_ps"] ** 2)
        progs.append(O["dg_prog_ns"]); ddgs.append(ddg); jit.append(O["sd_ps"])
        print(f"  {O['dg_prog_ns']:9.1f}{O['mean_ns']:13.4f} n"
              f"{ddg:11.4f} n{se:7.1f} ps{O['sd_ps']:8.0f} ps")

    ddgs = np.array(ddgs); progs = np.array(progs); jit = np.array(jit)
    print(f"\n  d_DG mean                {ddgs.mean():10.4f} ns")
    if ddgs.size > 1:
        print(f"  spread across delays     {np.ptp(ddgs)*1000:10.0f} ps")
        slope, inter = np.polyfit(progs, ddgs + progs, 1)
        print(f"  slope of output vs D     {slope:10.7f}  "
              f"({(slope-1)*1e6:+.0f} ppm)")
        if abs((slope - 1) * 1e6) > 200:
            print(f"\n  The slope is {(slope-1)*1e6:+.0f} ppm from 1. The DG535 "
                  f"is not delivering the\n  delays you are dialling in, or the "
                  f"fit moved to another edge. Fix that\n  before using d_DG.")
        else:
            print(f"  The DG535 delivers its programmed delay to "
                  f"{abs((slope-1)*1e6):.0f} ppm.")

    # ---- jitter ------------------------------------------------------
    print(f"\n\n  JITTER")
    print("  " + "=" * 56)
    print(f"  baseline, input run      {I['sd_ps']:10.0f} ps rms")
    print(f"    (scope comparator + edge fit + CH3, no DG535 in the path)")
    for p, j in zip(progs, jit):
        extra = np.sqrt(max(j ** 2 - I["sd_ps"] ** 2, 0.0))
        print(f"  D = {p:7.0f} ns  total {j:6.0f} ps"
              f"   -> DG535 {extra:6.0f} ps")

    extras = np.sqrt(np.clip(jit ** 2 - I["sd_ps"] ** 2, 0, None))
    if progs.size >= 3 and np.ptp(progs) > 0:
        k, floor = np.polyfit(progs, extras, 1)
        print(f"\n  fixed floor              {floor:10.0f} ps")
        print(f"  growth with delay        {k*1000:10.1f} ps per us")
        if k * 1000 > 20:
            print(f"  So quote the jitter at the delay you actually use, not "
                  f"at zero.")
        else:
            print(f"  No real growth over this range, so the floor is the whole "
                  f"story.")
    if np.all(extras < 0.5 * I["sd_ps"]):
        print(f"\n  The DG535 sits well under the {I['sd_ps']:.0f} ps baseline, "
              f"so these numbers are\n  differences of similar quantities and "
              f"carry large relative error. All\n  you can state firmly is that "
              f"it is below roughly {I['sd_ps']:.0f} ps.")

    x22 = 1000.0
    dgj = float(np.max(extras)) if extras.size else 0.0
    tot = np.sqrt(dgj ** 2 + x22 ** 2)
    print(f"\n\n  IN CONTEXT OF THE FIBER PATH")
    print("  " + "=" * 56)
    print(f"  DG535, worst of the above{dgj:10.0f} ps rms")
    print(f"  X22, datasheet bound     {x22:10.0f} ps rms")
    print(f"  in quadrature            {tot:10.0f} ps rms")
    print(f"  The X22 carries {100*x22**2/tot**2:.0f}% of the variance.")

    print(f"\n  Feed the delay into the fiber accounting with:")
    print(f"    python fiber_from_cal.py account --t-rec <fiber run> "
          f"--d-dg {ddgs.mean():.4f}")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ip", nargs="?")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--channel", type=int, default=4,
                       help="the channel you move. Default 4")
        p.add_argument("--ref-channel", type=int, default=3,
                       help="the fixed fiducial. Default 3")
        p.add_argument("--bnc", metavar="PORT",
                       help="fire each shot from the BNC 575 on this serial "
                            "port (e.g. COM5) instead of waiting for a trigger")
        p.add_argument("--yes", action="store_true",
                       help="skip the BNC 575 fire confirmation")

    p = sub.add_parser("survey", help="list edges on both channels")
    common(p)

    p = sub.add_parser("run", help="N shots, same-shot difference")
    common(p)
    p.add_argument("--label", required=True, choices=["input", "output"])
    p.add_argument("--shots", type=int, default=50)
    p.add_argument("--dg-prog", type=float, default=0.0,
                   help="DG535 programmed delay for this run, ns")
    p.add_argument("--falling", action="store_true")
    p.add_argument("--search", nargs=2, type=float, metavar=("LO", "HI"))
    p.add_argument("--ref-search", nargs=2, type=float, metavar=("LO", "HI"))

    p = sub.add_parser("solve", help="difference the runs")

    a = ap.parse_args()
    if a.cmd == "solve":
        return do_solve(a)
    if not a.ip:
        print("Need the scope IP.")
        return 1

    from calibrate_channel import connect, open_bnc, SCOPE_IPS
    a.ip = SCOPE_IPS.get(a.ip, a.ip)
    bnc, fire = open_bnc(a.bnc, a.yes) if a.bnc else (None, None)
    rm, instr, res = connect(a.ip, socket=True)
    sweep0 = None
    try:
        print(instr.query("*IDN?").strip())
        print(f"via {res}")
        for q, label in ((":TRIGger:SWEep?", "trigger sweep"),
                         (":TRIGger:EDGE:SOURce?", "trigger source"),
                         (":TIMebase:MAIN:SCALe?", "timebase s/div"),
                         (":ACQuire:MDEPth?", "memory depth"),
                         (f":CHANnel{a.channel}:IMPedance?",
                          f"CH{a.channel} impedance"),
                         (f":CHANnel{a.ref_channel}:IMPedance?",
                          f"CH{a.ref_channel} impedance")):
            try:
                print(f"  {label:<18} {instr.query(q).strip()}")
            except Exception:
                pass
        # NORM sweep for the measurement. In AUTO the scope can fire without
        # a real trigger, and that record has no fixed relation to T0.
        try:
            sweep0 = instr.query(":TRIGger:SWEep?").strip()
            if not sweep0.upper().startswith("NORM"):
                instr.write(":TRIGger:SWEep NORMal")
                print(f"  trigger sweep set to NORM for this run, "
                      f"restored to {sweep0} at the end")
        except Exception:
            sweep0 = None
        if a.cmd == "survey":
            return do_survey(instr, a, fire)
        return do_run(instr, a, fire)
    finally:
        try:
            if sweep0 and not sweep0.upper().startswith("NORM"):
                instr.write(f":TRIGger:SWEep {sweep0}")
        except Exception:
            pass
        try:
            instr.close(); rm.close()
        except Exception:
            pass
        if bnc is not None:
            bnc.close()


if __name__ == "__main__":
    sys.exit(main())