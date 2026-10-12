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
"""

import argparse
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


def arm_and_wait(instr, timeout=30.0, arm_timeout=5.0):
    """Arm for one shot and wait for it, without accepting the previous one.

    The trap: right after :STOP the scope reports STOP, and it still reports
    STOP for a few milliseconds after :SINGle while it processes the command.
    Polling straight for TD/STOP therefore exits immediately and you read the
    PREVIOUS acquisition. So wait for the scope to actually reach WAIT or RUN
    first, and only then watch for the trigger.
    """
    instr.write(":STOP")
    instr.write(":SINGle")

    deadline = time.time() + arm_timeout
    while time.time() < deadline:
        if instr.query(":TRIGger:STATus?").strip() in ("WAIT", "RUN"):
            break
        time.sleep(0.005)
    else:
        raise RuntimeError(
            "scope never reached WAIT after :SINGle — it may be in waveform "
            "record mode, or have a pending error")

    deadline = time.time() + timeout
    while time.time() < deadline:
        if instr.query(":TRIGger:STATus?").strip() in ("TD", "STOP"):
            break
        time.sleep(0.02)
    else:
        raise TimeoutError("no trigger")

    instr.write(":STOP")
    time.sleep(0.05)


def one_shot(instr, ch, timeout=30.0):
    arm_and_wait(instr, timeout)
    return read_channel(instr, ch)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ip")
    ap.add_argument("channel", type=int)
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
    ap.add_argument("--save", help="TimingCal JSON to update")
    ap.add_argument("--scope", help="scope id for the saved entry")
    args = ap.parse_args()

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
                         (":ACQuire:MDEPth?", "memory depth"),
                         (f":CHANnel{args.channel}:IMPedance?", "cal ch impedance"),
                         (f":CHANnel{args.channel}:SCALe?", "cal ch V/div")):
            try:
                print(f"  {label:<18} {instr.query(q).strip()}")
            except Exception:
                pass

        off = float(instr.query(":TIMebase:MAIN:OFFSet?"))
        if abs(off) > 1e-6:
            print(f"\n  WARNING: timebase offset is {off*1e6:.1f} us. The trigger "
                  f"point is far outside\n  the window and the calibration pulse "
                  f"will not be in the record. Set it to 0.")

        print(f"\nTaking {args.shots} shots on CH{args.channel}...")
        times, amps = [], []
        for i in range(args.shots):
            t, v = one_shot(instr, args.channel)
            st = edge_stats(t, v, rising=args.rising)
            te = st["edge_time"]
            if not np.isfinite(te):
                print(f"  shot {i+1:3d}: no edge found "
                      f"(amplitude {st['amplitude']*1e3:.0f} mV)")
                continue
            times.append(te)
            amps.append(st["amplitude"])
            if i == 0:
                print(f"  first shot: edge at {te*1e9:+.3f} ns, "
                      f"amplitude {st['amplitude']:.3f} V, "
                      f"risetime {st['risetime_20_80']*1e9:.2f} ns, "
                      f"{st['samples_on_edge']:.1f} samples on the edge")
            print(f"  shot {i+1:3d}: {te*1e9:+9.4f} ns")

        if len(times) < 2:
            print("\nNot enough good shots. Check the pulse is reaching the "
                  "channel and the\ntimebase offset is zero.")
            return 1

        t_rec = float(np.mean(times))
        jitter = float(np.std(times, ddof=1))
        offset = (args.dg_delay + args.tau_cal - args.tau_trig) * 1e-9 - t_rec

        print(f"\n{'shots used':<22}{len(times)}")
        print(f"{'mean edge time':<22}{t_rec*1e9:+9.4f} ns")
        print(f"{'shot-to-shot jitter':<22}{jitter*1e12:9.1f} ps rms")
        print(f"{'amplitude':<22}{np.mean(amps):9.3f} V")
        print(f"\n  offset = (dg {args.dg_delay:+.3f} + cal {args.tau_cal:.3f}"
              f" − trig {args.tau_trig:.3f}) ns − t_rec")
        print(f"{'OFFSET':<22}{offset*1e9:+9.4f} ns")
        print(f"{'uncertainty':<22}{jitter/np.sqrt(len(times))*1e12:9.1f} ps "
              f"(standard error of the mean)")

        if args.save and args.scope:
            from cable_cal import TimingCal
            import os
            cal = TimingCal.load(args.save) if os.path.exists(args.save) else TimingCal()
            cal.trig_delay[str(args.scope)] = args.tau_trig * 1e-9
            cal.offset[f"{args.scope}/{args.channel}"] = offset
            cal.save(args.save)
            print(f"\nsaved to {args.save}")
        return 0

    finally:
        try:
            instr.close(); rm.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())