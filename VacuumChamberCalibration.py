"""
Vacuum chamber calibration: capture and export from Rigol scope 3 over USB.

Standalone. Imports nothing from ScopeDelayGUI and opens only the one scope.

The scope is found by USB serial, not by "first Rigol on the bus": Rigol2
(DS7A230800035) shares this PC's USB, and calibration data silently taken
from the wrong scope would be worse than no data. If rigol3 is not attached
the script lists what is and stops.

Each capture writes, into VacuumChamberCalibration_data/YYYY.MM.DD/:
    rigol3_<stamp>[_label].csv         Time (s), Voltage_CH<n> (V)
    rigol3_<stamp>[_label].json        IDN, timebase, per-channel setup,
                                       preamble and ADC clip counts
    rigol3_<stamp>[_label].png         decimated preview (skip: --no-plot)

Only displayed channels are read, at full memory depth (RAW mode). Nothing
in the scope's setup is changed: the script writes :SINGle, :STOP and the
:WAVeform:* readout commands, nothing else.

Do not run this while the main GUI is capturing on rigol3 over Ethernet.
Both would be driving :WAVeform:SOURce on the same scope.

    python VacuumChamberCalibration.py              interactive loop
    python VacuumChamberCalibration.py --now        grab what is on screen, exit
    python VacuumChamberCalibration.py --shots 10   arm/capture 10 times, exit
    python VacuumChamberCalibration.py --list       show attached USB scopes

Interactive commands (anything after the letter is used as a file label):
    <Enter> or a [label]   arm SINGLE, wait for a trigger, capture
    n [label]              stop and capture whatever is in memory now
    q                      quit
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime

import numpy as np
import pandas as pd
import pyvisa


RIGOL3_SERIAL = "DS7A233300256"     # from *IDN? in the GUI session logs
RIGOL_USB_PATTERN = "USB?*::0x1AB1::?*::INSTR"

OUT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "VacuumChamberCalibration_data")

DATA_TIMEOUT_MS = 30000      # one 250k-point chunk is far under this on USB
QUERY_TIMEOUT_MS = 3000      # settings answer in ms, or never
CHUNK_POINTS = 250000        # Rigol caps a single :WAVeform:DATA? in BYTE mode

ADC_MIN, ADC_MAX = 0, 255

SCOPE_QUERIES = {
    "idn": "*IDN?",
    "memory_depth": ":ACQuire:MDEPth?",
    "sample_rate_sa_s": ":ACQuire:SRATe?",
    "acquisition_type": ":ACQuire:TYPE?",
    "timebase_scale_s_div": ":TIMebase:MAIN:SCALe?",
    "timebase_offset_s": ":TIMebase:MAIN:OFFSet?",
    "trigger_source": ":TRIGger:EDGE:SOURce?",
    "trigger_slope": ":TRIGger:EDGE:SLOPe?",
    "trigger_level_v": ":TRIGger:EDGE:LEVel?",
}

# No :LABel? - R2's firmware never answers it, and these scopes get swapped.
CHANNEL_QUERIES = {
    "scale_v_div": ":CHANnel{ch}:SCALe?",
    "offset_v": ":CHANnel{ch}:OFFSet?",
    "probe_ratio": ":CHANnel{ch}:PROBe?",
    "coupling": ":CHANnel{ch}:COUPling?",
    "impedance": ":CHANnel{ch}:IMPedance?",
    "bandwidth_limit": ":CHANnel{ch}:BWLimit?",
    "invert": ":CHANnel{ch}:INVert?",
    "units": ":CHANnel{ch}:UNITs?",
}

_SI = {"": 1, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9}


def parse_points(text):
    """':ACQuire:MDEPth?' -> int. Replies look like '1M', '125M', '1000000'."""
    m = re.fullmatch(r"([0-9.]+(?:[eE][+-]?\d+)?)\s*([kKMG]?)(?:pts)?",
                     (text or "").strip())
    return int(float(m.group(1)) * _SI[m.group(2)]) if m else None


def find_rigol_usb(rm):
    """{serial: resource} for every Rigol on USB."""
    found = {}
    try:
        resources = rm.list_resources(RIGOL_USB_PATTERN)
    except pyvisa.errors.VisaIOError:
        resources = ()              # NI-VISA raises when nothing matches
    for res in resources:
        parts = res.split("::")
        if len(parts) >= 4:
            found[parts[3]] = res
    return found


class Rigol3:
    def __init__(self, resource):
        self.rm = pyvisa.ResourceManager()
        self.resource = resource
        self.inst = None
        self.idn = ""

    def connect(self):
        self.inst = self.rm.open_resource(self.resource)
        self.inst.timeout = DATA_TIMEOUT_MS
        self.inst.read_termination = "\n"
        self.inst.write_termination = "\n"
        self.inst.chunk_size = 1024 * 1024
        self.idn = self.query("*IDN?")
        return self.idn

    def close(self):
        if self.inst is not None:
            self.inst.close()
            self.inst = None

    def write(self, cmd):
        self.inst.write(cmd)

    def query(self, cmd):
        return self.inst.query(cmd).strip()

    def query_quick(self, cmd):
        """Settings read: short timeout, None instead of raising."""
        saved = self.inst.timeout
        self.inst.timeout = QUERY_TIMEOUT_MS
        try:
            return self.query(cmd)
        except pyvisa.errors.VisaIOError:
            return None
        finally:
            self.inst.timeout = saved

    def trigger_status(self):
        return self.query(":TRIGger:STATus?")

    def arm_and_wait(self, timeout_s):
        """:SINGle, then poll until the acquisition is finished (STOP).

        TD means triggered but the post-trigger record may still be filling,
        so keep polling for STOP rather than reading at TD. *OPC? makes sure
        the scope has processed :SINGle before the first poll, or the STOP
        left over from the previous capture reads as an instant trigger.
        """
        self.write(":SINGle")
        self.query_quick("*OPC?")
        t0 = time.monotonic()
        seen_td = None
        while time.monotonic() - t0 < timeout_s:
            status = self.trigger_status()
            if status == "STOP":
                return True
            if status == "TD" and seen_td is None:
                seen_td = time.monotonic()
            # Should never stick at TD in single mode; don't hang on it if it does.
            if seen_td is not None and time.monotonic() - seen_td > 5.0:
                return True
            time.sleep(0.05)
        return False

    def displayed_channels(self):
        return [ch for ch in range(1, 5)
                if self.query(f":CHANnel{ch}:DISPlay?") in ("1", "ON")]

    def settings(self, channels):
        out = {"scope": {k: self.query_quick(c) for k, c in SCOPE_QUERIES.items()},
               "channels": {}}
        for ch in channels:
            out["channels"][ch] = {k: self.query_quick(c.format(ch=ch))
                                   for k, c in CHANNEL_QUERIES.items()}
        return out

    def _preamble(self):
        p = self.query(":WAVeform:PREamble?").split(",")
        return {"format": int(p[0]), "type": int(p[1]), "points": int(p[2]),
                "count": int(p[3]), "xincrement": float(p[4]),
                "xorigin": float(p[5]), "xreference": float(p[6]),
                "yincrement": float(p[7]), "yorigin": float(p[8]),
                "yreference": float(p[9])}

    def read_channel(self, ch, total):
        """Full memory of one channel in RAW/BYTE, walked in chunks.

        Returns (time, volts, codes, preamble). The scope must be stopped.
        """
        self.write(f":WAVeform:SOURce CHANnel{ch}")
        self.write(":WAVeform:MODE RAW")
        self.write(":WAVeform:FORMat BYTE")
        self.write(":WAVeform:STARt 1")
        self.write(f":WAVeform:STOP {min(CHUNK_POINTS, total)}")
        pre = self._preamble()
        if pre["format"] != 0:
            raise RuntimeError(f"CH{ch}: preamble format {pre['format']}, expected BYTE (0)")

        chunks = []
        start = 1
        while start <= total:
            stop = min(start + CHUNK_POINTS - 1, total)
            self.write(f":WAVeform:STARt {start}")
            self.write(f":WAVeform:STOP {stop}")
            vals = self.inst.query_binary_values(
                ":WAVeform:DATA?", datatype="B", container=np.array,
                header_fmt="ieee", expect_termination=True)
            if vals.size == 0:
                break
            chunks.append(vals.astype(np.uint8))
            start += vals.size

        codes = np.concatenate(chunks) if chunks else np.array([], dtype=np.uint8)
        volts = (codes.astype(float) - pre["yreference"] - pre["yorigin"]) * pre["yincrement"]
        t = pre["xorigin"] + (np.arange(codes.size) - pre["xreference"]) * pre["xincrement"]
        return t, volts, codes, pre

    def capture(self):
        """Stop, then read every displayed channel at full depth."""
        self.write(":STOP")
        channels = self.displayed_channels()
        if not channels:
            raise RuntimeError("No channels displayed on the scope")

        total = parse_points(self.query_quick(":ACQuire:MDEPth?"))
        if not total:
            # AUTO depth: ask the preamble how much is there.
            self.write(f":WAVeform:SOURce CHANnel{channels[0]}")
            self.write(":WAVeform:MODE RAW")
            total = self._preamble()["points"]

        info = self.settings(channels)
        info["capture"] = {"expected_points": total, "channels": {}}
        data = {}
        for ch in channels:
            t, v, codes, pre = self.read_channel(ch, total)
            low = int(np.count_nonzero(codes <= ADC_MIN))
            high = int(np.count_nonzero(codes >= ADC_MAX))
            info["capture"]["channels"][ch] = {
                "points": int(v.size), "preamble": pre,
                "clipped_low": low, "clipped_high": high,
                "v_min": float(v.min()) if v.size else None,
                "v_max": float(v.max()) if v.size else None,
            }
            data[ch] = (t, v)
            if v.size == 0:
                print(f"  CH{ch}: no data returned")
                continue
            note = ""
            if v.size < total:
                note += f"  SHORT ({v.size} of {total})"
            if low or high:
                note += f"  CLIPPED ({low} low, {high} high)"
            print(f"  CH{ch}: {v.size} pts, {v.min():+.4g} .. {v.max():+.4g} V{note}")
        return data, info


def export(data, info, label, make_plot, show_plot):
    stamp = datetime.now()
    out_dir = os.path.join(OUT_ROOT, stamp.strftime("%Y.%m.%d"))
    os.makedirs(out_dir, exist_ok=True)
    name = "rigol3_" + stamp.strftime("%Y%m%d_%H%M%S")
    if label:
        name += "_" + re.sub(r"[^A-Za-z0-9._-]+", "_", label).strip("_")
    base = os.path.join(out_dir, name)

    # All channels share one timebase; pad a short channel with NaN.
    n = max(len(t) for t, _ in data.values())
    t_axis = next(t for t, _ in data.values() if len(t) == n)
    cols = {"Time (s)": t_axis}
    for ch, (_, v) in data.items():
        col = np.full(n, np.nan)
        col[:len(v)] = v
        cols[f"Voltage_CH{ch} (V)"] = col
    pd.DataFrame(cols).to_csv(base + ".csv", index=False)

    info["captured_at"] = stamp.isoformat(timespec="seconds")
    info["label"] = label or ""
    with open(base + ".json", "w") as f:
        json.dump(info, f, indent=2, default=str)

    if make_plot or show_plot:
        import matplotlib
        if not show_plot:
            matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        step = max(1, n // 20000)
        fig, ax = plt.subplots(figsize=(11, 5))
        for ch, (t, v) in data.items():
            ax.plot(t[::step], v[::step], lw=0.8, label=f"CH{ch}")
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Voltage (V)")
        ax.set_title(name)
        ax.grid(True, alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(base + ".png", dpi=110)
        if show_plot:
            plt.show()
        plt.close(fig)

    print(f"  saved {base}.csv")
    return base


def open_scope(args):
    rm = pyvisa.ResourceManager()
    if args.resource:
        return Rigol3(args.resource)
    found = find_rigol_usb(rm)
    if args.serial in found:
        return Rigol3(found[args.serial])
    print(f"Rigol scope with serial {args.serial} is not on USB.")
    if found:
        print("Attached Rigol scopes:")
        for serial, res in found.items():
            print(f"  {serial}   {res}")
        print("Use --serial <serial> to pick one of these on purpose.")
    else:
        print("No Rigol scopes on USB. Check the cable and that the scope's "
              "USB device port is enabled (Utility > IO).")
    sys.exit(1)


def do_capture(scope, arm, label, args):
    if arm:
        print(f"  armed SINGLE, waiting for trigger (Ctrl+C to abort, "
              f"timeout {args.timeout:g} s) ...")
        try:
            if not scope.arm_and_wait(args.timeout):
                print("  no trigger before timeout; nothing saved")
                return None
        except KeyboardInterrupt:
            print("\n  aborted; nothing saved")
            return None
    t0 = time.monotonic()
    data, info = scope.capture()
    print(f"  read in {time.monotonic() - t0:.1f} s")
    return export(data, info, label, not args.no_plot, args.show)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serial", default=RIGOL3_SERIAL,
                    help=f"USB serial of the scope (default rigol3, {RIGOL3_SERIAL})")
    ap.add_argument("--resource", help="full VISA resource string; overrides --serial")
    ap.add_argument("--list", action="store_true", help="list Rigol scopes on USB and exit")
    ap.add_argument("--now", action="store_true",
                    help="capture what is in memory now, without arming, and exit")
    ap.add_argument("--shots", type=int, default=0,
                    help="arm and capture this many triggers, then exit")
    ap.add_argument("--label", default="", help="text appended to file names")
    ap.add_argument("--timeout", type=float, default=600.0,
                    help="seconds to wait for each trigger (default 600)")
    ap.add_argument("--no-plot", action="store_true", help="skip the PNG preview")
    ap.add_argument("--show", action="store_true",
                    help="open each preview in a window (blocks until closed)")
    args = ap.parse_args()

    if args.list:
        found = find_rigol_usb(pyvisa.ResourceManager())
        for serial, res in found.items():
            tag = "  <- rigol3" if serial == RIGOL3_SERIAL else ""
            print(f"{serial}   {res}{tag}")
        if not found:
            print("No Rigol scopes on USB.")
        return

    scope = open_scope(args)
    print(f"Connecting to {scope.resource} ...")
    print(f"Connected: {scope.connect()}")
    try:
        if args.now:
            do_capture(scope, False, args.label, args)
            return
        if args.shots:
            for i in range(1, args.shots + 1):
                print(f"Shot {i}/{args.shots}")
                label = f"{args.label}_{i:03d}" if args.label else f"{i:03d}"
                do_capture(scope, True, label, args)
            return

        print(f"Saving to {OUT_ROOT}")
        print("Enter/a [label] = arm & capture   n [label] = capture now   q = quit")
        while True:
            try:
                line = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            cmd, _, rest = line.partition(" ")
            cmd = cmd.lower()
            label = rest.strip() or args.label
            if cmd == "q":
                break
            if cmd not in ("", "a", "n"):
                print("  ? Enter/a = arm, n = now, q = quit")
                continue
            try:
                do_capture(scope, cmd != "n", label, args)
            except (pyvisa.errors.VisaIOError, RuntimeError, ValueError) as e:
                print(f"  capture failed: {e}")
    finally:
        scope.close()


if __name__ == "__main__":
    main()
