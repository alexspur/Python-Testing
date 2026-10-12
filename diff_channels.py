"""
Same-shot delay between two channels on one scope.

Arms once, reads BOTH channels from that single acquisition, and differences
the edge times. Trigger jitter shifts the whole record, so it moves both
channels together and cancels exactly in the difference. Expect the scatter on
Δt to be far smaller than the scatter on either channel alone — that is the
check that the measurement is working.

For the BNC575 A-to-B skew with ch A teed into CH3 and ch B into CH4:

    t_CH3 − t_CH4 = (τ_A + ε_CH3) − (skew_AB + τ_B + ε_CH4)

so

    skew_AB = (τ_A − τ_B) − (t_CH3 − t_CH4) + (ε_CH3 − ε_CH4)

The scope's own channel-to-channel skew ε_CH3 − ε_CH4 is entangled with the
generator's. Swap the two cables between the channels, run again, and average
the two results: the channel term flips sign and drops out, the generator term
does not.

Usage:
    python diff_channels.py 192.168.10.51 3 4 --shots 20
    python diff_channels.py 192.168.10.51 3 4 --shots 20 --tau-a 4.599 --tau-b 1.455
"""

import argparse
import sys
import time

import numpy as np

sys.path.insert(0, ".")
from calibrate_channel import connect, read_channel, arm_and_wait   # noqa: E402
from edge_timing import edge_time, edge_stats                       # noqa: E402


def shot_two_channels(instr, ch_a, ch_b, timeout=30.0):
    """Arm once, then read both channels out of that same acquisition.

    Reading them from one acquisition is the whole point. Re-arming between
    the two reads would put a fresh dose of trigger jitter into each and the
    difference would stop cancelling.
    """
    arm_and_wait(instr, timeout)
    ta, va = read_channel(instr, ch_a)
    tb, vb = read_channel(instr, ch_b)
    return (ta, va), (tb, vb)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ip")
    ap.add_argument("ch_a", type=int, help="channel carrying BNC575 ch A")
    ap.add_argument("ch_b", type=int, help="channel carrying BNC575 ch B")
    ap.add_argument("--shots", type=int, default=20)
    ap.add_argument("--tau-a", type=float, help="cable delay into ch_a, ns")
    ap.add_argument("--tau-b", type=float, help="cable delay into ch_b, ns")
    ap.add_argument("--falling", action="store_true", help="time falling edges")
    ap.add_argument("--instr", action="store_true", help="VXI-11 instead of socket")
    args = ap.parse_args()

    rising = not args.falling
    rm, instr, res = connect(args.ip, socket=not args.instr)
    try:
        print(instr.query("*IDN?").strip())
        print(f"via {res}\n")
        for q, label in ((":TRIGger:EDGE:SOURce?", "trigger source"),
                         (":TRIGger:EDGE:LEVel?", "trigger level"),
                         (":TIMebase:MAIN:SCALe?", "timebase s/div"),
                         (":TIMebase:MAIN:OFFSet?", "timebase offset"),
                         (f":CHANnel{args.ch_a}:IMPedance?", f"CH{args.ch_a} impedance"),
                         (f":CHANnel{args.ch_b}:IMPedance?", f"CH{args.ch_b} impedance")):
            try:
                print(f"  {label:<18} {instr.query(q).strip()}")
            except Exception:
                pass

        print(f"\nCH{args.ch_a} = BNC575 ch A,  CH{args.ch_b} = BNC575 ch B")
        print(f"Taking {args.shots} shots, both channels from each single "
              f"acquisition...\n")
        print(f"  {'shot':>5}{'CH'+str(args.ch_a):>14}{'CH'+str(args.ch_b):>14}"
              f"{'difference':>14}")
        print("  " + "-" * 45)

        ta_list, tb_list, d_list = [], [], []
        first = None
        for i in range(args.shots):
            (ta, va), (tb, vb) = shot_two_channels(instr, args.ch_a, args.ch_b)
            ea = edge_time(ta, va, rising=rising)
            eb = edge_time(tb, vb, rising=rising)
            if first is None:
                first = (edge_stats(ta, va, rising=rising),
                         edge_stats(tb, vb, rising=rising))
            if not (np.isfinite(ea) and np.isfinite(eb)):
                print(f"  {i+1:5d}   edge not found on one or both channels")
                continue
            # A genuine stale read repeats BOTH channels exactly, not just
            # their difference.
            dup = "  <-- stale, same acquisition as previous" if (
                ta_list and abs(ea - ta_list[-1]) < 1e-15
                and abs(eb - tb_list[-1]) < 1e-15) else ""
            ta_list.append(ea); tb_list.append(eb); d_list.append(ea - eb)
            print(f"  {i+1:5d}{ea*1e9:13.4f}n{eb*1e9:13.4f}n"
                  f"{(ea-eb)*1e9:13.4f}n{dup}")

        if len(d_list) < 2:
            print("\nNot enough good shots.")
            return 1

        a = np.array(ta_list); b = np.array(tb_list); d = np.array(d_list)

        dups = int(np.sum((np.abs(np.diff(a)) < 1e-15)
                          & (np.abs(np.diff(b)) < 1e-15)))
        if dups:
            print(f"\n  {dups} of {len(d)} shots repeated the previous value "
                  f"exactly. That means the\n  scope returned the same "
                  f"acquisition twice, so the real sample count is\n  lower than "
                  f"it looks and the quoted uncertainty is optimistic.")
        print(f"\n  {'':<22}{'mean':>14}{'rms scatter':>15}")
        print("  " + "-" * 51)
        print(f"  {'CH'+str(args.ch_a)+' edge':<22}{a.mean()*1e9:12.4f} ns"
              f"{a.std(ddof=1)*1e12:12.1f} ps")
        print(f"  {'CH'+str(args.ch_b)+' edge':<22}{b.mean()*1e9:12.4f} ns"
              f"{b.std(ddof=1)*1e12:12.1f} ps")
        print(f"  {'difference':<22}{d.mean()*1e9:12.4f} ns"
              f"{d.std(ddof=1)*1e12:12.1f} ps")

        common = min(a.std(ddof=1), b.std(ddof=1))
        ratio = common / d.std(ddof=1) if d.std(ddof=1) > 0 else float("inf")
        if d.std(ddof=1) < common:
            shown = "inf" if not np.isfinite(ratio) else f"{ratio:.1f}x"
            print(f"\n  Trigger jitter cancelled: the difference scatters "
                  f"{shown} less\n  than either channel alone, which is what a "
                  f"same-shot measurement should do.")
        else:
            print(f"\n  WARNING: the difference is not quieter than the "
                  f"individual channels.\n  Something is adding independent "
                  f"noise per channel — check amplitudes\n  and that both edges "
                  f"are cleanly resolved.")

        se = d.std(ddof=1) / np.sqrt(len(d))
        print(f"\n  Δt = CH{args.ch_a} − CH{args.ch_b} = "
              f"{d.mean()*1e9:+.4f} ns  ± {se*1e12:.1f} ps")

        if args.tau_a is not None and args.tau_b is not None:
            skew = (args.tau_a - args.tau_b) * 1e-9 - d.mean()
            print(f"\n  skew_AB = (τ_A {args.tau_a:.3f} − τ_B {args.tau_b:.3f}) ns"
                  f" − Δt")
            print(f"          = {skew*1e9:+.4f} ns")
            print(f"\n  That is skew_AB − (ε_CH{args.ch_a} − ε_CH{args.ch_b}), so it"
                  f" is off by this scope's\n  own front-end difference between the"
                  f" two channels. Swap the cables\n  between CH{args.ch_a} and"
                  f" CH{args.ch_b}, run again, and average the two numbers: the"
                  f"\n  channel term flips sign and cancels, the generator term"
                  f" does not.")

        if first:
            print(f"\n  First-shot diagnostics:")
            for name, st in ((f"CH{args.ch_a}", first[0]), (f"CH{args.ch_b}", first[1])):
                print(f"    {name}: amplitude {st['amplitude']:.3f} V, "
                      f"risetime {st['risetime_20_80']*1e9:.2f} ns, "
                      f"{st['samples_on_edge']:.1f} samples on the edge")
        return 0

    finally:
        try:
            instr.close(); rm.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())