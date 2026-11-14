"""
Measure one channel's timing offset. Run this once per channel, twelve times.

What it does, per shot: arms the scope, waits for the trigger, reads the
calibration channel, and finds the edge to sub-sample precision. It repeats
that N times and averages, because one shot carries the trigger jitter and the
average does not.

It never changes the trigger level, slope or source. Those set the comparator
timing you are measuring, so disturbing them invalidates the result.

    offset = τ_cal − τ_trig − t_rec

Usage:
    python calibrate_channel.py 192.168.10.51 4 --tau-cal 4.599 --tau-trig 4.471
    python calibrate_channel.py 192.168.10.51 4 --tau-cal 4.599 --tau-trig 4.471 \
        --shots 20 --save timing_cal.json --scope 1

Fired from the BNC 575 instead of an outside trigger, scope 3, all four
channels (prompts to move the cal cable between channels):
    python calibrate_channel.py 3 1 2 3 4 --tau-cal 4.599 --tau-trig 4.471 \
        --bnc COM5 --save timing_cal.json
"""

import argparse
import os
import sys
import time

import numpy as np

sys.path.insert(0, ".")
from edge_timing import edge_time, edge_stats          # noqa: E402


def connect(ip, socket=True, timeout_ms=20000):
    import pyvisa
    res = f"TCPIP0::{ip}::5555::SOCKET" if socket else f"TCPIP0::{ip}::INSTR"
    rm = pyvisa.ResourceManager()
    instr = rm.open_resource(res)
    instr.timeout = timeout_ms
    instr.read_termination = "\n"
    instr.write_termination = "\n"
    return rm, instr, res


def read_block(instr, cmd):
    """TMC block read by declared length. Required on a raw socket."""
    old = instr.read_termination
    instr.read_termination = None
    try:
        instr.write(cmd)
        head = instr.read_bytes(2)
        if head[0:1] != b"#":
            raise IOError(f"bad TMC header {head!r}")
        n = int(head[1:2])
        length = int(instr.read_bytes(n))
        data = instr.read_bytes(length)
        try:
            instr.read_bytes(1)
        except Exception:
            pass
        return data
    finally:
        instr.read_termination = old


def preamble(instr):
    p = instr.query(":WAVeform:PREamble?").strip().split(",")
    return dict(points=int(p[2]), xinc=float(p[4]), xorig=float(p[5]),
                yinc=float(p[7]), yorig=float(p[8]), yref=float(p[9]))


def read_channel(instr, ch, chunk=250_000):
    """Full RAW record for one channel. Scope must already be stopped."""
    instr.write(f":WAVeform:SOURce CHANnel{ch}")
    instr.write(":WAVeform:MODE RAW")
    instr.write(":WAVeform:FORMat BYTE")

    depth = instr.query(":ACQuire:MDEPth?").strip()
    try:
        total = int(float(depth.replace("M", "e6").replace("k", "e3")))
    except ValueError:
        instr.write(":WAVeform:STARt 1")
        instr.write(":WAVeform:STOP 1000000000")
        total = int(float(instr.query(":WAVeform:STOP?")))

    instr.write(":WAVeform:STARt 1")
    instr.write(f":WAVeform:STOP {min(chunk, total)}")
    pre = preamble(instr)

    parts, start = [], 1
    while start <= total:
        stop = min(start + chunk - 1, total)
        instr.write(f":WAVeform:STARt {start}")
        instr.write(f":WAVeform:STOP {stop}")
        vals = np.frombuffer(read_block(instr, ":WAVeform:DATA?"), dtype=np.uint8)
        if vals.size == 0:
            break
        parts.append(vals)
        start += vals.size

    raw = np.concatenate(parts) if parts else np.array([], np.uint8)
    v = (raw.astype(np.float64) - pre["yref"] - pre["yorig"]) * pre["yinc"]
    t = pre["xorig"] + np.arange(v.size) * pre["xinc"]
    return t, v


def _trig_status(instr):
    return instr.query(":TRIGger:STATus?").strip().upper()


def arm_and_wait(instr, timeout=30.0, arm_timeout=5.0, retries=3, fire=None):
    """Arm for one shot and wait for it, without accepting the previous one.

    fire, if given, is called once the scope is armed and is what produces
    the trigger (the BNC 575). It is held until the scope reports WAIT,
    because a trigger that arrives while it is still filling the pre-trigger
    record (RUN) is ignored.

    The trap: right after :STOP the scope reports STOP, and it still reports
    STOP for a few milliseconds after :SINGle while it processes the command.
    Polling straight for TD/STOP therefore exits immediately and you read the
    PREVIOUS acquisition. So first confirm the scope is stopped, then send
    :SINGle, then wait until it leaves STOP before watching for the trigger.

    Any state other than STOP after :SINGle belongs to the new acquisition.
    That includes AUTO, which is what the scope reports while armed when the
    trigger sweep is AUTO, and TD, which means the trigger came before the
    first poll. If the scope never leaves STOP, the :SINGle is sent again.
    """
    seen = []

    def note(st):
        if not seen or seen[-1] != st:
            seen.append(st)

    left_stop = False
    for _ in range(retries):
        instr.write(":STOP")
        t0 = time.time()
        while time.time() - t0 < 1.0:
            if _trig_status(instr) == "STOP":
                break
            time.sleep(0.005)
        instr.write(":SINGle")

        deadline = time.time() + arm_timeout
        while time.time() < deadline:
            st = _trig_status(instr)
            note(st)
            if st != "STOP":
                left_stop = True
                break
            time.sleep(0.005)
        if left_stop:
            break
    if not left_stop:
        raise RuntimeError(
            f"scope never left STOP after :SINGle, {retries} tries. "
            f"States seen: {seen}. It may be in waveform record mode, "
            f"or have a pending error")

    if fire is not None:
        deadline = time.time() + arm_timeout
        while time.time() < deadline:
            st = _trig_status(instr)
            note(st)
            if st in ("WAIT", "AUTO", "TD"):
                break
            time.sleep(0.005)
        fire()

    deadline = time.time() + timeout
    while time.time() < deadline:
        st = _trig_status(instr)
        note(st)
        if st in ("TD", "STOP"):
            break
        time.sleep(0.02)
    else:
        raise TimeoutError(f"no trigger within {timeout:.0f} s. "
                           f"States seen: {seen}")

    instr.write(":STOP")
    time.sleep(0.05)


def one_shot(instr, ch, timeout=30.0, fire=None):
    arm_and_wait(instr, timeout, fire=fire)
    return read_channel(instr, ch)


SCOPE_IPS = {"1": "192.168.10.51", "2": "192.168.10.52", "3": "192.168.10.53"}


def open_bnc(port, assume_yes=False):
    """Connect to the BNC 575 and return a fire() callable for one_shot.

    Refuses unless the 575's trigger mode is DIS: fire_internal() only sends
    :PULSE0:MODE SING and :PULSE0:STATE ON, which in TRIG/DUAL just re-arms
    it for an external edge and produces no pulse.
    """
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "ScopeDelayGUI"))
    from instruments.bnc575 import BNC575Controller, TriggerMode

    bnc = BNC575Controller()
    bnc.connect(port)
    print(f"BNC 575: {bnc.identify() or '(no *IDN? reply)'} on {port}")
    mode = bnc.get_trigger_mode()
    if mode is not TriggerMode.DISABLED:
        bnc.close()
        raise RuntimeError(
            f"BNC 575 trigger mode is {mode.value if mode else 'unknown'}, not "
            f"DIS, so a software fire would produce no pulse. Set it to DIS "
            f"on the front panel and run again.")

    if not assume_yes:
        print("\n  Every BNC 575 output fires on each shot. In the shot setup,\n"
              "  A drives the Marx DG535 and B the laser DG535. Make sure only\n"
              "  the calibration cabling is connected.")
        if input("  Fire the BNC 575 for this calibration? [y/N] ").strip().lower() != "y":
            bnc.close()
            raise SystemExit("aborted")
    return bnc, bnc.fire_internal


def measure(instr, args, ch, fire):
    """Take args.shots shots on one channel. Returns (t_rec, jitter, n, amp)."""
    timeout = 5.0 if fire else 30.0
    print(f"\nTaking {args.shots} shots on CH{ch}...")
    times, amps = [], []
    for i in range(args.shots):
        try:
            t, v = one_shot(instr, ch, timeout=timeout, fire=fire)
        except TimeoutError as e:
            if not fire:
                raise
            print(f"  shot {i+1:3d}: missed ({e})")
            continue
        st = edge_stats(t, v, rising=args.rising)
        te = st["edge_time"]
        if not np.isfinite(te):
            print(f"  shot {i+1:3d}: no edge found "
                  f"(amplitude {st['amplitude']*1e3:.0f} mV)")
            continue
        times.append(te)
        amps.append(st["amplitude"])
        if len(times) == 1:
            print(f"  first shot: edge at {te*1e9:+.3f} ns, "
                  f"amplitude {st['amplitude']:.3f} V, "
                  f"risetime {st['risetime_20_80']*1e9:.2f} ns, "
                  f"{st['samples_on_edge']:.1f} samples on the edge")
        print(f"  shot {i+1:3d}: {te*1e9:+9.4f} ns")

    if len(times) < 2:
        return None
    return (float(np.mean(times)), float(np.std(times, ddof=1)),
            len(times), float(np.mean(amps)))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ip", help="scope IP, or 1/2/3 for that scope's IP")
    ap.add_argument("channels", type=int, nargs="+",
                    help="one or more channels; you are prompted to move the "
                         "cal cable between them")
    ap.add_argument("--tau-cal", type=float, required=True,
                    help="calibration cable delay, ns")
    ap.add_argument("--tau-trig", type=float, required=True,
                    help="cumulative trigger path delay to this scope, ns")
    ap.add_argument("--dg-delay", type=float, default=0.0,
                    help="programmed delay of the cal output vs ch A, ns")
    ap.add_argument("--shots", type=int, default=20)
    ap.add_argument("--rising", action="store_true", default=True)
    ap.add_argument("--falling", dest="rising", action="store_false")
    ap.add_argument("--instr", action="store_true",
                    help="use VXI-11 instead of raw socket")
    ap.add_argument("--bnc", metavar="PORT",
                    help="fire each shot from the BNC 575 on this serial port "
                         "(e.g. COM5) instead of waiting for an outside trigger")
    ap.add_argument("--yes", action="store_true",
                    help="skip the BNC 575 fire confirmation")
    ap.add_argument("--save", help="TimingCal JSON to update")
    ap.add_argument("--scope", help="scope id for the saved entry")
    args = ap.parse_args()

    if args.ip in SCOPE_IPS:
        args.scope = args.scope or args.ip
        args.ip = SCOPE_IPS[args.ip]

    bnc, fire = (open_bnc(args.bnc, args.yes) if args.bnc else (None, None))
    rm, instr, res = connect(args.ip, socket=not args.instr)
    try:
        print(instr.query("*IDN?").strip())
        print(f"via {res}\n")

        # Report the settings that matter, without changing any of them.
        for q, label in ((":TRIGger:SWEep?", "trigger sweep"),
                         (":TRIGger:EDGE:SOURce?", "trigger source"),
                         (":TRIGger:EDGE:LEVel?", "trigger level"),
                         (":TIMebase:MAIN:SCALe?", "timebase s/div"),
                         (":TIMebase:MAIN:OFFSet?", "timebase offset"),
                         (":ACQuire:MDEPth?", "memory depth")):
            try:
                print(f"  {label:<18} {instr.query(q).strip()}")
            except Exception:
                pass

        off = float(instr.query(":TIMebase:MAIN:OFFSet?"))
        if abs(off) > 1e-6:
            print(f"\n  WARNING: timebase offset is {off*1e6:.1f} us. The trigger "
                  f"point is far outside\n  the window and the calibration pulse "
                  f"will not be in the record. Set it to 0.")
        if fire and instr.query(":TRIGger:SWEep?").strip().upper().startswith("AUTO"):
            print("\n  WARNING: trigger sweep is AUTO. The scope can trigger itself "
                  "before\n  the BNC 575 pulse arrives. Set it to SINGLE or NORMAL.")

        results, rc = {}, 0
        for n, ch in enumerate(args.channels):
            if n > 0:
                input(f"\nMove the calibration cable to CH{ch}, then press Enter...")
            for q, label in ((f":CHANnel{ch}:IMPedance?", "cal ch impedance"),
                             (f":CHANnel{ch}:SCALe?", "cal ch V/div")):
                try:
                    print(f"  {label:<18} {instr.query(q).strip()}")
                except Exception:
                    pass

            r = measure(instr, args, ch, fire)
            if r is None:
                print("\nNot enough good shots. Check the pulse is reaching the "
                      "channel and the\ntimebase offset is zero.")
                rc = 1
                continue
            t_rec, jitter, n_used, amp = r
            offset = (args.dg_delay + args.tau_cal - args.tau_trig) * 1e-9 - t_rec
            results[ch] = (offset, jitter / np.sqrt(n_used))

            print(f"\n{'shots used':<22}{n_used}")
            print(f"{'mean edge time':<22}{t_rec*1e9:+9.4f} ns")
            print(f"{'shot-to-shot jitter':<22}{jitter*1e12:9.1f} ps rms")
            print(f"{'amplitude':<22}{amp:9.3f} V")
            print(f"\n  offset = (dg {args.dg_delay:+.3f} + cal {args.tau_cal:.3f}"
                  f" − trig {args.tau_trig:.3f}) ns − t_rec")
            print(f"{'OFFSET':<22}{offset*1e9:+9.4f} ns")
            print(f"{'uncertainty':<22}{jitter/np.sqrt(n_used)*1e12:9.1f} ps "
                  f"(standard error of the mean)")

            if args.save and args.scope:
                from cable_cal import TimingCal
                cal = TimingCal.load(args.save) if os.path.exists(args.save) else TimingCal()
                cal.trig_delay[str(args.scope)] = args.tau_trig * 1e-9
                cal.offset[f"{args.scope}/{ch}"] = offset
                cal.save(args.save)
                print(f"\nsaved to {args.save}")

        if len(args.channels) > 1:
            print("\nSummary")
            for ch in args.channels:
                if ch in results:
                    o, u = results[ch]
                    print(f"  CH{ch}  {o*1e9:+9.4f} ns  ± {u*1e12:.1f} ps")
                else:
                    print(f"  CH{ch}  failed")
        return rc

    finally:
        try:
            instr.close(); rm.close()
        except Exception:
            pass
        if bnc is not None:
            bnc.close()


if __name__ == "__main__":
    sys.exit(main())