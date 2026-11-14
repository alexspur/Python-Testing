"""
One-way transit time of a TF1 / fiber / X22 link, by substitution.

Timing the fiber edge against the scope's t=0 would need the generator's own
trigger-to-output delay, which is not measured, and the 129 ns screen-room
cable to a precision the cable cannot give. So measure the same edge twice
and subtract:

    run "direct"   gen A -> screen-room cable -> scope CH4 at 50 ohm
    run "fiber"    gen A -> the SAME cable -> TF1 -> fiber -> X22 -> scope CH4

    t_fiber - t_direct  =  d_TF1 + tau_fiber + d_X22 + tau_out

Everything upstream of the TF1 is common and cancels exactly: the generator's
internal delay, the 129 ns cable and all its dispersion, the scope's -87.4 ns
trigger offset, the trigger-path cable. The only cable delay you still need is
tau_out, the 1 ft run from the X22 (RG-58 = 1.54 ns).

For the better version of the same measurement, which uses the delay
generator as the ruler and gives a slope as a free validity check, see
fiber_delay_sweep.py. Use this one for the survey and for quick single-point
checks.

    python fiber_transit.py 192.168.10.51 4 survey --tscale 2e-7
    python fiber_transit.py 192.168.10.51 4 run --label direct --shots 50
    python fiber_transit.py 192.168.10.51 4 run --label fiber  --shots 50
    python fiber_transit.py solve --tau-out 1.54
    python fiber_transit.py --notes
"""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, ".")

STORE = "fiber_transit.json"

# TTL input thresholds, volts. The TF1 is spec'd only as "TTL Levels", so
# 2.0 V is the worst-case guaranteed logic-high threshold for TTL families.
TTL_VIH = 2.0
TTL_VIL = 0.8

# 62.5/125 um step-index multimode, 850 nm. Group index ~1.47-1.49 depending
# on core dopant, so this is good to about 1%.
FIBER_NS_PER_M = 4.90
FIBER_NS_PER_M_RANGE = (4.85, 4.98)

NOTES = """
WHAT THE DATASHEETS DO AND DO NOT TELL YOU
==========================================================================
  TF1-850       propagation delay  <= 25 ns   TTL to optical
  X22-ST-850    propagation delay  <= 15 ns   optical to TTL
                propagation jitter <  1 ns

Both delays are upper bounds. No typical value, no unit-to-unit tolerance,
no temperature coefficient. "<= 40 ns" for the pair is all you can claim
from paper, which is why measuring is the only route to a real number.

The jitter spec is the one that should change how you take the data. 1 ns rms
from the X22 alone dominates everything else in your chain: 208-273 ps of
scope shot jitter, 3 ps of cable metrology. Averaging is the only defence,
and it goes as 1/sqrt(N):

    20 shots  ->  224 ps standard error
    50 shots  ->  141 ps
   100 shots  ->  100 ps
   400 shots  ->   50 ps

That same 1 ns is a hard floor on anything you TRIGGER through this link. It
is random per shot, so no calibration removes it. If a fiber-triggered LTGS
needs better than 1 ns, the link is the wrong tool, not the calibration.

THE TF1 IS SELF-POWERED FROM ITS INPUT SIGNAL
==========================================================================
It scavenges drive for the LED from the pulse you send it: 10 mA minimum,
30 mA for full fiber length or full rate. So its propagation delay is a
function of how hard it is driven. A TF1 measured on the bench with a short
cable does not have the same delay as the same TF1 at the end of 25.6 m.

That is why the substitution runs must be done without moving anything else,
and why the "direct" run is not just a reference. It is the diagnostic that
tells you what the TF1 is actually being fed.

YOUR SCREEN-ROOM CABLE, MEASURED
==========================================================================
  delay          129.3 to 129.9 ns depending on fit band
  length         25.58 m at VF 0.66
  one-way loss   -1.2 dB at 10 MHz,  -3.0 dB at 50 MHz,  -4.2 dB at 100 MHz
  3 dB bandwidth ~60 MHz one way
  risetime floor ~5.9 ns at the far end

The 0.55 ns spread across fit bands is dispersion, not fit error: the sqrt(f)
skin-effect loss of coax makes group delay frequency-dependent, so this cable
does not have a single delay. It has a delay that depends on your edge. In
the substitution method this does not matter at all, because the cable
cancels. Do not try to use 129.3 ns as an absolute number.

The bandwidth is the part that matters. A generator edge of 2-3 ns arrives at
the TF1 slewed to about 6 ns, at roughly 70% amplitude. If the pulse arrives
near 2 V, the TF1's TTL threshold sits far up the shoulder of a 6 ns edge,
where it is slowest and most curved, and the delay becomes strongly
amplitude-dependent. Check the direct run's amplitude before trusting
anything else.

If the amplitude is marginal, the real fix is architectural: a fiber link
exists to avoid long coax, so putting 25.6 m of coax in FRONT of the
converter spends the cable loss anyway and puts the TF1 at the worst-driven
point in the system. Converting at the generator and running fiber the whole
way would remove both problems at once.

X22 OUTPUT LOADING
==========================================================================
  "47 ohm output series impedance driving TTL levels into >= 5 kohm"

Into your 50 ohm scope input that is a 47/50 divider, so you see about 52% of
the open-circuit swing. Take the amplitude hit: 47 ohm in series is close
enough to 50 that the line is matched and reflection-free, which is what you
want for timing. At 1 Mohm the line is unterminated, the edge doubles and
rings, and the 50% crossing moves around with the ringing.

Record both polarity switch positions. Inverted output means you are timing a
falling edge against a rising one, and the two directions need not have the
same delay.
"""


def multi_edges(t, v, min_sep_ns=5.0, max_report=40, min_consec=3):
    """Transitions found by a Schmitt trigger referenced to the NOISE FLOOR.

    Two normalizations fail here and both were tried first. Percentiles fail
    because a few-ns pulse in a 400 us record sits above the 99th percentile,
    so a trimmed range measures the baseline and every wiggle is an edge.
    Min-to-max span fails because for N Gaussian samples the span is always
    about 2*sigma*sqrt(2 ln N) -- 10 sigma at a million points -- so pure
    noise always looks like it has a 10 sigma "signal", and because a second
    smaller pulse never reaches a threshold set at 75% of the largest one.

    So: baseline from the median, noise from the MAD, and the signal's reach
    measured from the baseline. A pulse has to clear the noise by a wide
    margin before any threshold is placed.
    """
    v = np.asarray(v, float); t = np.asarray(t, float)
    n = v.size
    if n < 16:
        return [], {"reason": "record too short"}

    base = float(np.median(v))
    noise = float(np.median(np.abs(v - base))) * 1.4826
    noise = max(noise, 1e-12)
    up, dn = float(np.max(v)) - base, base - float(np.min(v))
    pos = up >= dn
    reach = up if pos else dn

    info = {"baseline": base, "noise_rms": noise, "reach": reach,
            "polarity": "positive" if pos else "negative",
            "reach_sigma": reach / noise}

    # For N Gaussian samples the expected range is 2*sigma*sqrt(2 ln N), so
    # require the reach to beat that by 50% before believing in a pulse.
    expect = np.sqrt(2.0 * np.log(max(n, 10)))
    need = 1.5 * expect * noise
    info["threshold_sigma"] = 1.5 * expect
    if reach < need:
        info["reason"] = (f"signal reaches only {reach/noise:.1f} sigma from "
                          f"baseline; {1.5*expect:.1f} sigma needed at "
                          f"{n} samples")
        return [], info

    s = 1.0 if pos else -1.0
    v_hi = base + s * 0.60 * reach
    v_lo = base + s * 0.20 * reach
    v_mid = base + s * 0.50 * reach
    info.update(v_lo=v_lo, v_hi=v_hi)

    dt = float(t[1] - t[0])
    min_sep = max(1, int(min_sep_ns * 1e-9 / dt))
    x = s * v
    x_hi, x_lo, x_mid = s * v_hi, s * v_lo, s * v_mid

    state = 1 if x[0] > x_hi else 0
    hits, last = [], -10 * min_sep
    run = 0
    for i in range(1, n):
        if state == 0:
            run = run + 1 if x[i] > x_hi else 0
            if run >= min_consec:
                j = i - run + 1
                while j > 0 and x[j] > x_mid:
                    j -= 1
                if j - last >= min_sep:
                    hits.append((j, "rising" if pos else "falling")); last = j
                state, run = 1, 0
        else:
            run = run + 1 if x[i] < x_lo else 0
            if run >= min_consec:
                j = i - run + 1
                while j > 0 and x[j] < x_mid:
                    j -= 1
                if j - last >= min_sep:
                    hits.append((j, "falling" if pos else "rising")); last = j
                state, run = 0, 0

    res = []
    for j, d in hits:
        w = slice(max(0, j - min_sep), min(n, j + min_sep))
        local = float(np.ptp(v[w]))
        if local >= 0.25 * reach and local >= 8 * noise:
            res.append((float(t[j]), d, local))
    info["n_found"] = len(res)
    info["truncated"] = max(0, len(res) - max_report)
    return res[:max_report], info



def probe_window(instr, ch, search, min_sep_ns=5.0):
    """One shot, to see what is actually in the search window.

    Asking for the wrong edge direction is the easiest way to get a confident
    wrong answer: edge_stats will happily fit the largest noise wiggle of the
    requested polarity and report it with a plausible-looking jitter. So look
    first, then decide.
    """
    from calibrate_channel import one_shot
    t, v = one_shot(instr, ch)
    edges, info = multi_edges(t, v, min_sep_ns=min_sep_ns, max_report=200)
    info["record"] = (float(t[0]), float(t[-1]))
    info["dt"] = float(t[1] - t[0])
    if search:
        inside = [e for e in edges if search[0] <= e[0] <= search[1]]
    else:
        inside = list(edges)
    info["in_window"] = inside
    info["best"] = max(inside, key=lambda e: e[2]) if inside else None
    return info


def set_window(instr, tscale, out=sys.stdout):
    """Set s/div and PROVE it landed. Rigol silently ignores some writes."""
    want = float(tscale)
    instr.write(":STOP")
    for attempt, text in enumerate((f"{want:.12G}", f"{want:.12f}")):
        instr.write(f":TIMebase:MAIN:SCALe {text}")
        try:
            got = float(instr.query(":TIMebase:MAIN:SCALe?"))
        except Exception:
            got = float("nan")
        if np.isfinite(got) and abs(got - want) <= 0.02 * want:
            print(f"  timebase set     {got:.4G} s/div "
                  f"(window {got*10*1e6:.3f} us)", file=out)
            return got
        if attempt == 0:
            print(f"  scientific format was ignored, retrying as decimal",
                  file=out)
    print(f"  TIMEBASE WRITE FAILED. asked for {want:.4G}, scope reports "
          f"{got:.4G} s/div.\n  Set it on the front panel instead: "
          f"{want*1e9:.0f} ns/div.", file=out)
    return got


def load():
    return json.load(open(STORE)) if os.path.exists(STORE) else {}


def save(d):
    json.dump(d, open(STORE, "w"), indent=2)


def describe_drive(amp, risetime, label=""):
    """Is the TF1 being driven hard enough for its delay to be stable?

    Only the DIRECT run measures the TF1's input. On the fiber run this same
    channel is carrying the X22's OUTPUT, where a TTL threshold verdict is
    meaningless, so say nothing rather than something wrong.
    """
    if label and "direct" not in label.lower():
        return [f"This run measures the X22 output, not the TF1 input, so the "
                f"TTL drive\n    check does not apply. Amplitude "
                f"{amp:.2f} V, risetime {risetime*1e9:.2f} ns."]
    msgs = []
    if amp < TTL_VIH:
        msgs.append(
            f"CRITICAL: {amp:.2f} V peak is below the 2.0 V TTL logic-high\n"
            f"    threshold. The TF1 may not be switching reliably at all, and "
            f"any\n    delay you measure is not reproducible. Fix the drive "
            f"before going on.")
    elif amp < 1.5 * TTL_VIH:
        msgs.append(
            f"WARNING: {amp:.2f} V peak puts the 2.0 V TTL threshold at "
            f"{100*TTL_VIH/amp:.0f}% of the\n    edge amplitude, high on the "
            f"shoulder. On a {risetime*1e9:.1f} ns edge a 10% amplitude\n"
            f"    change moves the TF1's switching point by roughly "
            f"{0.1*risetime*1e12/3:.0f} ps. The link\n    delay will drift "
            f"with anything that changes the drive.")
    else:
        msgs.append(
            f"Drive looks healthy: {amp:.2f} V peak against a 2.0 V threshold, "
            f"so the\n    TF1 switches near the middle of the edge where it is "
            f"steepest.")
    if risetime > 4e-9:
        msgs.append(
            f"The {risetime*1e9:.1f} ns risetime is the 25.6 m cable, not the "
            f"generator. It\n    sets how much a threshold shift costs you in "
            f"time.")
    return msgs


def report_settings(instr, ch, out=sys.stdout):
    for q, label in ((":TRIGger:SWEep?", "trigger sweep"),
                     (":TRIGger:EDGE:SOURce?", "trigger source"),
                     (":TRIGger:EDGE:LEVel?", "trigger level"),
                     (":TIMebase:MAIN:SCALe?", "timebase s/div"),
                     (":TIMebase:MAIN:OFFSet?", "timebase offset"),
                     (":ACQuire:MDEPth?", "memory depth"),
                     (f":CHANnel{ch}:IMPedance?", f"CH{ch} impedance"),
                     (f":CHANnel{ch}:SCALe?", f"CH{ch} V/div"),
                     (f":CHANnel{ch}:PROBe?", f"CH{ch} probe ratio")):
        try:
            print(f"  {label:<18} {instr.query(q).strip()}", file=out)
        except Exception:
            pass


def do_survey(instr, ch, args):
    from calibrate_channel import one_shot

    out = open(args.output, "w") if args.output else sys.stdout
    try:
        print(f"SURVEY, CH{ch}", file=out)
        print("=" * 60, file=out)
        if args.tscale:
            set_window(instr, args.tscale, out=out)
        report_settings(instr, ch, out=out)

        t, v = one_shot(instr, ch)
        dt = float(t[1] - t[0])
        span_ns = (t[-1] - t[0]) * 1e9
        print(f"\n  window        {t[0]*1e9:+.1f} to {t[-1]*1e9:+.1f} ns "
              f"({span_ns:.0f} ns span)", file=out)
        print(f"  samples       {v.size}  at {dt*1e12:.0f} ps", file=out)
        print(f"  signal range  {v.min():+.3f} to {v.max():+.3f} V "
              f"(ptp {np.ptp(v):.3f} V)", file=out)

        edges, info = multi_edges(t, v)
        print(f"  baseline      {info.get('baseline', 0):+.3f} V, "
              f"noise {info.get('noise_rms', 0)*1e3:.1f} mV rms", file=out)
        print(f"  signal reach  {info.get('reach', 0):.3f} V from baseline "
              f"= {info.get('reach_sigma', 0):.1f} sigma "
              f"(needs {info.get('threshold_sigma', 0):.1f})", file=out)
        if "v_lo" in info:
            print(f"  polarity      {info['polarity']}-going", file=out)
            print(f"  thresholds    {info['v_lo']:+.3f} / {info['v_hi']:+.3f} V"
                  f"  (20% / 60% of reach)", file=out)

        if not edges:
            print(f"\n  NO PULSE FOUND. {info.get('reason', '')}", file=out)
            print(f"\n  Either the pulse is outside this window, or nothing is "
                  f"reaching CH{ch}.\n  Try --tscale 2e-7 for a 2 us window, or "
                  f"check the cable.", file=out)
            return 1

        print(f"\n  {info['n_found']} transition(s)"
              + (f", showing the first 40" if info["truncated"] else ""),
              file=out)
        print(f"    {'time':>14}{'direction':>12}{'local ptp':>12}", file=out)
        print("    " + "-" * 38, file=out)
        for te, d, a in edges:
            print(f"    {te*1e9:11.2f} ns{d:>12}{a:11.3f} V", file=out)

        rising = [e for e in edges if e[1] == "rising"]
        if rising:
            te = rising[0][0] * 1e9
            print(f"\n  First rising edge at {te:.2f} ns. Use\n"
                  f"    --search {te-15:.0f} {te+15:.0f}", file=out)

        if span_ns > 20000:
            print(f"\n  A {span_ns/1000:.0f} us window is far too wide for this "
                  f"measurement. Rerun with\n  --tscale 2e-7 so the edge is "
                  f"sampled densely enough to fit.", file=out)
        return 0
    finally:
        if args.output:
            out.close()
            print(f"written to {args.output}")


def do_run(instr, ch, args):
    from calibrate_channel import one_shot
    from edge_timing import edge_stats

    search = None
    if args.search:
        search = (args.search[0] * 1e-9, args.search[1] * 1e-9)
    if args.tscale:
        set_window(instr, args.tscale)

    # Look before fitting. edge_stats will fit the largest noise wiggle of
    # whatever polarity you ask for and report it with a believable jitter,
    # so the direction has to be settled against the actual waveform.
    print(f"\nProbing CH{ch} to see what is in the window...")
    info = probe_window(instr, ch, search)
    r0, r1 = info["record"]
    print(f"  record        {r0*1e9:+.0f} to {r1*1e9:+.0f} ns at "
          f"{info['dt']*1e12:.0f} ps")
    print(f"  baseline      {info['baseline']:+.3f} V, noise "
          f"{info['noise_rms']*1e3:.1f} mV rms")
    print(f"  reach         {info['reach']:.3f} V "
          f"({info['reach_sigma']:.0f} sigma), "
          f"{info.get('polarity', '?')}-going")

    best = info["best"]
    if best is None:
        print(f"\n  No real transition inside the search window. Everything "
              f"there is within\n  the noise, so any fit would be a fit to "
              f"noise. Run survey and pick a\n  window around a listed edge.")
        if info["in_window"] == [] and info.get("n_found"):
            print(f"  The record does contain {info['n_found']} transition(s), "
                  f"just not in this window.")
        return 1

    detected = best[1] == "rising"
    print(f"  largest edge  {best[0]*1e9:+.2f} ns, {best[1]}, "
          f"{best[2]:.3f} V")

    if args.rising and args.falling:
        print("\n  Pass only one of --rising and --falling.")
        return 1
    if args.rising or args.falling:
        rising = bool(args.rising)
        if rising != detected:
            print(f"\n  WARNING: you asked for a {'rising' if rising else 'falling'}"
                  f" edge but the real transition in\n  this window is "
                  f"{best[1]}. Honouring your choice, but the fit will land on "
                  f"noise.\n  Drop the flag to let it follow the waveform.")
    else:
        rising = detected
        print(f"  -> timing the {best[1]} edge. Override with "
              f"--rising or --falling.")

    print(f"\nRun '{args.label}', {args.shots} shots on CH{ch}, "
          f"{'rising' if rising else 'falling'} edge")
    if search:
        print(f"  restricted to {args.search[0]:.1f} to {args.search[1]:.1f} ns")
    print()
    reach = info["reach"]

    times, amps, rises, nsamp = [], [], [], []
    for i in range(args.shots):
        t, v = one_shot(instr, ch)
        kw = {"rising": rising}
        if search:
            kw["search"] = search
        st = edge_stats(t, v, **kw)
        te = st["edge_time"]
        if not np.isfinite(te):
            print(f"  shot {i+1:4d}: no edge (ptp {np.ptp(v)*1e3:.0f} mV)")
            continue
        times.append(te); amps.append(st["amplitude"])
        rises.append(st["risetime_20_80"]); nsamp.append(st["samples_on_edge"])
        if i == 0 or (i + 1) % 10 == 0 or i == args.shots - 1:
            print(f"  shot {i+1:4d}: {te*1e9:+11.4f} ns")

    if len(times) < 3:
        print("\nNot enough good shots.")
        return 1

    a = np.array(times)
    mean = float(a.mean()); sd = float(a.std(ddof=1))
    se = sd / np.sqrt(a.size)
    amp = float(np.mean(amps)); rt = float(np.mean(rises))

    print(f"\n  {'shots used':<24}{a.size}")
    print(f"  {'mean edge time':<24}{mean*1e9:+11.4f} ns")
    print(f"  {'shot-to-shot jitter':<24}{sd*1e12:11.1f} ps rms")
    print(f"  {'standard error':<24}{se*1e12:11.1f} ps")
    print(f"  {'amplitude':<24}{amp:11.3f} V")
    print(f"  {'risetime 20-80':<24}{rt*1e9:11.2f} ns")
    print(f"  {'samples on edge':<24}{np.mean(nsamp):11.1f}")

    if amp < 0.25 * reach:
        print(f"\n  THIS IS A FIT TO NOISE, NOT THE PULSE. The fitted amplitude "
              f"{amp:.3f} V is only\n  {100*amp/reach:.0f}% of the "
              f"{reach:.3f} V the signal actually reaches. Nothing below\n  is "
              f"meaningful. Fix the search window or the edge direction and "
              f"re-run.")
    if np.mean(nsamp) < 4:
        print(f"\n  WARNING: only {np.mean(nsamp):.1f} samples on the edge, and "
              f"the fit needs 4 or more.\n  Narrowing the timebase will NOT help: "
              f"at 1M points over this window you\n  are already at the scope's "
              f"2.5 GSa/s ceiling, so the 400 ps interval is\n  fixed. This few "
              f"samples on an edge means you fit noise, not the pulse.\n  Check "
              f"the edge direction and the search window.")
    if sd > 1.5e-9:
        print(f"\n  {sd*1e12:.0f} ps of jitter is above the X22's 1 ns spec. "
              f"Something else is\n  adding noise: check the drive amplitude "
              f"and that you are locked onto\n  the right edge.")

    print()
    for m in describe_drive(amp, rt, args.label):
        print(f"  {m}")

    d = load()
    d[args.label] = {"mean_s": mean, "sd_s": sd, "se_s": se, "n": a.size,
                     "amplitude_v": amp, "risetime_s": rt,
                     "channel": ch, "rising": rising,
                     "samples_on_edge": float(np.mean(nsamp))}
    save(d)
    print(f"\n  saved as '{args.label}' in {STORE}")
    return 0


def do_solve(args):
    d = load()
    for k in (args.fiber, args.direct):
        if k not in d:
            print(f"No run called '{k}' in {STORE}. Have: {sorted(d)}")
            return 1
    F, D = d[args.fiber], d[args.direct]

    if F["rising"] != D["rising"]:
        print("  NOTE: the two runs timed opposite edge directions. That is "
              "correct only\n  if the X22 polarity switch is inverting. The "
              "pulse width then enters the\n  answer as well.\n")

    raw = F["mean_s"] - D["mean_s"]
    link = raw - args.tau_out * 1e-9
    u = np.sqrt(F["se_s"]**2 + D["se_s"]**2 + (args.tau_out_se * 1e-12)**2)

    print("ONE-WAY TRANSIT, TF1 + FIBER + X22")
    print("=" * 66)
    print(f"  {'run':<14}{'mean':>15}{'jitter':>11}{'s.e.':>10}{'N':>6}"
          f"{'amp':>9}")
    print("  " + "-" * 64)
    for name, r in ((args.fiber, F), (args.direct, D)):
        print(f"  {name:<14}{r['mean_s']*1e9:12.4f} ns{r['sd_s']*1e12:8.0f} ps"
              f"{r['se_s']*1e12:7.1f} ps{r['n']:6d}{r['amplitude_v']:8.2f} V")

    print(f"\n  difference            {raw*1e9:12.4f} ns")
    print(f"  minus output cable    {-args.tau_out:12.4f} ns")
    print("  " + "-" * 38)
    print(f"  LINK DELAY            {link*1e9:12.4f} ns  +/- {u*1e12:.0f} ps")

    print(f"\n  Cancelled, so never needed: the generator's internal delay,\n"
          f"  the 129 ns screen-room cable and its dispersion, the scope's\n"
          f"  -87.4 ns trigger offset, the trigger-path cable.")

    if args.fiber_m:
        tf = args.fiber_m * FIBER_NS_PER_M
        lo = args.fiber_m * FIBER_NS_PER_M_RANGE[0]
        hi = args.fiber_m * FIBER_NS_PER_M_RANGE[1]
        el = link * 1e9 - tf
        print(f"\n  SPLIT, using {args.fiber_m:.1f} m of 62.5/125 fiber")
        print("  " + "-" * 50)
        print(f"  fiber at {FIBER_NS_PER_M:.2f} ns/m   {tf:10.2f} ns"
              f"   (range {lo:.1f} to {hi:.1f})")
        print(f"  electronics, implied  {el:10.2f} ns   (datasheet max 40)")
        if el > 40:
            print(f"\n  {el-40:.1f} ns over the datasheet maximum. The fiber is "
                  f"longer than\n  {args.fiber_m:.1f} m, or the drive is near "
                  f"threshold, or the two runs are not on\n  corresponding "
                  f"edges.")
        elif el < 0:
            print(f"\n  Negative is impossible, so the fiber length is wrong or "
                  f"the two runs\n  are not the same edge.")
        else:
            print(f"\n  Within the datasheet bound. The fiber length now "
                  f"dominates, at "
                  f"{FIBER_NS_PER_M:.1f} ns\n  per metre of length error. "
                  f"Measure the link twice with two known fiber\n  lengths and "
                  f"take the slope to drop the length guess entirely.")
    else:
        print(f"\n  Pass --fiber-m LENGTH to split this into fiber "
              f"({FIBER_NS_PER_M:.2f} ns/m) and\n  converter electronics "
              f"(datasheet max 40 ns for the pair).")

    print(f"\n  Per-shot jitter through the link is {F['sd_s']*1e12:.0f} ps "
          f"rms. That is irreducible\n  by calibration and is your floor for "
          f"anything triggered this way.")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--notes", action="store_true",
                    help="datasheet findings and cable analysis, then exit")
    ap.add_argument("ip", nargs="?")
    ap.add_argument("channel", nargs="?", type=int)
    sub = ap.add_subparsers(dest="cmd")

    sp = sub.add_parser("survey", help="one shot, list every edge found")
    sp.add_argument("--output", help="save the report to a file")
    sp.add_argument("--tscale", help="set s/div first, e.g. 2e-7, and verify")

    sp = sub.add_parser("run", help="N shots, save the mean edge time")
    sp.add_argument("--label", required=True, help="e.g. direct, fiber")
    sp.add_argument("--shots", type=int, default=50)
    sp.add_argument("--falling", action="store_true",
                    help="force falling edges. Default: follow the waveform")
    sp.add_argument("--rising", action="store_true",
                    help="force rising edges. Default: follow the waveform")
    sp.add_argument("--search", nargs=2, type=float, metavar=("LO", "HI"),
                    help="restrict the edge search to this window, ns")
    sp.add_argument("--tscale", help="set s/div first, e.g. 2e-7, and verify")

    sp = sub.add_parser("solve", help="difference two runs")
    sp.add_argument("--fiber", default="fiber")
    sp.add_argument("--direct", default="direct")
    sp.add_argument("--tau-out", type=float, required=True,
                    help="X22-to-scope cable delay, ns. 1 ft RG-58 = 1.54")
    sp.add_argument("--tau-out-se", type=float, default=150.0,
                    help="its uncertainty, ps. 150 if estimated from length")
    sp.add_argument("--fiber-m", type=float,
                    help="fiber length, m, to split fiber from electronics")

    args = ap.parse_args()

    if args.notes:
        print(NOTES)
        return 0
    if args.cmd == "solve":
        return do_solve(args)
    if not args.cmd:
        ap.print_help()
        return 1
    if not args.ip or args.channel is None:
        print("Need IP and channel for survey/run.")
        return 1

    from calibrate_channel import connect
    rm, instr, res = connect(args.ip, socket=True)
    try:
        idn = instr.query("*IDN?").strip()
        print(idn)
        print(f"via {res}")
        if args.cmd == "survey":
            return do_survey(instr, args.channel, args)
        report_settings(instr, args.channel)
        return do_run(instr, args.channel, args)
    finally:
        try:
            instr.close(); rm.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())