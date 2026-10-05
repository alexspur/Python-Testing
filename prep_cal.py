"""
Put a scope into calibration horizontal setup, and put it back afterward.

The calibration pulse arrives within nanoseconds of the trigger, so the
trigger point has to be inside the acquisition window. With your campaign
settings it is 183 us outside it and the pulse is simply not in the record.

Saves the settings it changes to a JSON file so --restore puts them back
exactly. It never touches the trigger level, slope or source: those set the
comparator timing you are measuring.

    python prep_cal.py 192.168.10.51 4
    ... run calibrate_channel.py ...
    python prep_cal.py 192.168.10.51 4 --restore
"""

import argparse
import json
import os
import sys

sys.path.insert(0, ".")
from calibrate_channel import connect      # noqa: E402

SAVED = "prep_cal_saved.json"

# Queried and restored. Trigger settings are deliberately absent.
KEYS = [
    (":TIMebase:MAIN:OFFSet", "timebase offset"),
    (":TIMebase:MAIN:SCALe", "timebase s/div"),
    (":ACQuire:MDEPth", "memory depth"),
]


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ip")
    ap.add_argument("channel", type=int)
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("--tscale", default="2e-8", help="s/div for calibration")
    ap.add_argument("--depth", default="100k", help="memory depth for calibration")
    ap.add_argument("--instr", action="store_true")
    args = ap.parse_args()

    rm, instr, _ = connect(args.ip, socket=not args.instr)
    try:
        idn = instr.query("*IDN?").strip()
        print(idn)
        serial = idn.split(",")[2] if len(idn.split(",")) > 2 else args.ip
        store = json.load(open(SAVED)) if os.path.exists(SAVED) else {}

        if args.restore:
            if serial not in store:
                print(f"\nNo saved settings for {serial}. Nothing restored.")
                return 1
            print("\nRestoring:")
            for cmd, label in KEYS:
                val = store[serial].get(cmd)
                if val is None:
                    continue
                instr.write(f"{cmd} {val}")
                print(f"  {label:<18} {val}")
            ch = store[serial].get("channel")
            imp = store[serial].get("impedance")
            if ch and imp:
                instr.write(f":CHANnel{ch}:IMPedance {imp}")
                print(f"  CH{ch} impedance    {imp}")
            del store[serial]
            json.dump(store, open(SAVED, "w"), indent=2)
            print("\nBack to campaign settings.")
            return 0

        # Save what we are about to change.
        cur = {}
        print("\nCurrent settings, saved:")
        for cmd, label in KEYS:
            v = instr.query(cmd + "?").strip()
            cur[cmd] = v
            print(f"  {label:<18} {v}")
        cur["channel"] = args.channel
        cur["impedance"] = instr.query(
            f":CHANnel{args.channel}:IMPedance?").strip()
        print(f"  CH{args.channel} impedance    {cur['impedance']}")
        store[serial] = cur
        json.dump(store, open(SAVED, "w"), indent=2)

        print("\nSetting up for calibration:")
        instr.write(":TIMebase:MAIN:OFFSet 0")
        instr.write(f":TIMebase:MAIN:SCALe {args.tscale}")
        instr.write(f":ACQuire:MDEPth {args.depth}")
        instr.write(f":CHANnel{args.channel}:DISPlay ON")
        instr.write(f":CHANnel{args.channel}:IMPedance FIFTy")
        for cmd, label in KEYS:
            print(f"  {label:<18} {instr.query(cmd + '?').strip()}")
        print(f"  CH{args.channel} impedance    "
              f"{instr.query(f':CHANnel{args.channel}:IMPedance?').strip()}")

        print("\nUnchanged on purpose (these set the comparator timing):")
        for q, label in ((":TRIGger:EDGE:SOURce?", "trigger source"),
                         (":TRIGger:EDGE:SLOPe?", "trigger slope"),
                         (":TRIGger:EDGE:LEVel?", "trigger level")):
            print(f"  {label:<18} {instr.query(q).strip()}")

        print(f"\nCheck CH{args.channel} shows the pulse, then run "
              f"calibrate_channel.py.")
        return 0
    finally:
        try:
            instr.close(); rm.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
