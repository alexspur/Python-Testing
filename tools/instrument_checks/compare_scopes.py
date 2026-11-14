"""
Compare settings across the three Rigol scopes and flag real mismatches.

Three scopes watching the same shot must AGREE on some settings and are
SUPPOSED to differ on others. Lumping those together produces noise, so this
splits them:

  MUST MATCH     memory depth, trigger sweep, acquisition type. These decide
                 whether a capture happened at all and how much of it you got.
                 A difference here is a bug.

  PER SCOPE      V/div, offset, probe ratio, channel coupling. Each scope
                 watches different signals through different probes, so these
                 are supposed to differ. Shown for the record, never flagged.
                 NEVER normalize these. Forcing a common probe ratio would
                 silently corrupt every voltage you have ever recorded.

  WORTH A LOOK   timebase, trigger level, sample rate. Legitimately different
                 sometimes, worth your eye when they are.

NON-DESTRUCTIVE by default. --set-depth and --set-sweep each write exactly one
setting and touch nothing else.

Usage:
    python compare_scopes.py
    python compare_scopes.py --set-depth 1M
    python compare_scopes.py --set-sweep SINGle
    python compare_scopes.py --hosts 192.168.10.51 192.168.10.52
"""

import argparse
import sys

DEFAULT_HOSTS = ["192.168.10.51", "192.168.10.52", "192.168.10.53"]

# (query, label). A difference here is a real problem.
MUST_MATCH = [
    (":ACQuire:MDEPth?", "memory depth"),
    (":ACQuire:TYPE?", "acquisition type"),
    (":TRIGger:SWEep?", "trigger sweep"),
    (":TRIGger:MODE?", "trigger mode"),
    (":TRIGger:EDGE:SOURce?", "trigger source"),
    (":TRIGger:EDGE:SLOPe?", "trigger slope"),
]

# Shown, and a difference is worth a glance but not automatically wrong.
WORTH_A_LOOK = [
    (":ACQuire:SRATe?", "sample rate"),
    (":TIMebase:MAIN:SCALe?", "timebase s/div"),
    (":TIMebase:MAIN:OFFSet?", "timebase offset"),
    (":TRIGger:EDGE:LEVel?", "trigger level"),
    (":TRIGger:HOLDoff?", "trigger holdoff"),
    (":ACQuire:AVERages?", "averages"),
    (":TRIGger:STATus?", "state now"),
]

# Per-channel. Only the on/off state must match. The rest is the measurement
# setup for that particular scope and is expected to differ.
CHANNEL_MUST_MATCH = [
    (":CHANnel{ch}:DISPlay?", "CH{ch} on"),
]
CHANNEL_PER_SCOPE = [
    (":CHANnel{ch}:SCALe?", "CH{ch} V/div"),
    (":CHANnel{ch}:OFFSet?", "CH{ch} offset"),
    (":CHANnel{ch}:PROBe?", "CH{ch} probe"),
    (":CHANnel{ch}:COUPling?", "CH{ch} coupling"),
    (":CHANnel{ch}:BWLimit?", "CH{ch} BW limit"),
]


def connect(host, timeout_ms=10000):
    import pyvisa
    rm = pyvisa.ResourceManager()
    instr = rm.open_resource(f"TCPIP0::{host}::INSTR")
    instr.timeout = timeout_ms
    instr.read_termination = "\n"
    instr.write_termination = "\n"
    return rm, instr


def ask(instr, cmd):
    try:
        return instr.query(cmd).strip()
    except Exception:
        return None


def read_scope(host, set_depth=None, set_sweep=None):
    rm, instr = connect(host)
    data = {}
    try:
        idn = ask(instr, "*IDN?") or ""
        parts = [p.strip() for p in idn.split(",")]
        data["_serial"] = parts[2] if len(parts) > 2 else "?"
        data["_firmware"] = parts[3] if len(parts) > 3 else "?"

        if set_depth:
            instr.write(f":ACQuire:MDEPth {set_depth}")
        if set_sweep:
            instr.write(f":TRIGger:SWEep {set_sweep}")

        for cmd, label in MUST_MATCH + WORTH_A_LOOK:
            data[label] = ask(instr, cmd)
        for ch in range(1, 5):
            for cmd, label in CHANNEL_MUST_MATCH + CHANNEL_PER_SCOPE:
                data[label.format(ch=ch)] = ask(instr, cmd.format(ch=ch))
        return data
    finally:
        try:
            instr.close()
            rm.close()
        except Exception:
            pass


def build_rows():
    """Return [(label, category)] in display order."""
    rows = [(l, "match") for _, l in MUST_MATCH]
    rows += [(l, "look") for _, l in WORTH_A_LOOK]
    for ch in range(1, 5):
        rows += [(l.format(ch=ch), "match") for _, l in CHANNEL_MUST_MATCH]
        rows += [(l.format(ch=ch), "perscope") for _, l in CHANNEL_PER_SCOPE]
    return rows


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hosts", nargs="+", default=DEFAULT_HOSTS)
    ap.add_argument("--set-depth", metavar="DEPTH",
                    help="write this memory depth to every scope, e.g. 1M")
    ap.add_argument("--set-sweep", metavar="SWEEP",
                    help="write this trigger sweep to every scope, "
                         "normally SINGle")
    args = ap.parse_args()

    results = {}
    for host in args.hosts:
        try:
            results[host] = read_scope(host, args.set_depth, args.set_sweep)
            print(f"read {host}")
        except Exception as e:
            print(f"FAILED {host}: {e}")

    if len(results) < 2:
        print("\nNeed at least two scopes to compare.")
        return 1

    hosts = [h for h in args.hosts if h in results]
    w = 20

    def line(label, cells, mark=""):
        print(f"{label:<20}" + "".join(f"{str(c):>{w}}" for c in cells) + mark)

    print()
    line("", [h.split(".")[-1] for h in hosts])
    line("serial", [results[h]["_serial"] for h in hosts])
    line("firmware", [results[h]["_firmware"] for h in hosts])
    print("-" * (20 + w * len(hosts)))

    problems = []
    look = []
    section = None

    for label, category in build_rows():
        values = [results[h].get(label) for h in hosts]
        if all(v is None for v in values):
            continue
        differs = len(set(values)) > 1

        # Averages only matters when the scope is actually averaging.
        if label == "averages":
            types = {results[h].get("acquisition type") for h in hosts}
            if types == {"NORM"}:
                differs = False

        if category == "match" and differs:
            mark = "  <-- MISMATCH"
            problems.append((label, dict(zip(hosts, values))))
        elif category == "look" and differs:
            mark = "  <-- differs"
            look.append((label, dict(zip(hosts, values))))
        elif category == "perscope" and differs:
            mark = "  (per scope)"
        else:
            mark = ""

        if category == "perscope" and section != "perscope":
            section = "perscope"
        line(label, values, mark)

    print()
    if problems:
        print(f"{len(problems)} real mismatch(es). These must agree:")
        for label, values in problems:
            pairs = ", ".join(f"{h.split('.')[-1]}={v}" for h, v in values.items())
            print(f"  {label}: {pairs}")
    else:
        print("No mismatches in the settings that must agree.")

    if look:
        print(f"\n{len(look)} setting(s) worth a look:")
        for label, values in look:
            pairs = ", ".join(f"{h.split('.')[-1]}={v}" for h, v in values.items())
            print(f"  {label}: {pairs}")

    # Specific, actionable guidance for the two that actually break captures.
    sweeps = {h: results[h].get("trigger sweep") for h in hosts}
    bad_sweep = [h for h, s in sweeps.items() if s and s != "SING"]
    if bad_sweep:
        print("\nTRIGGER SWEEP is not SINGle on: " +
              ", ".join(h.split(".")[-1] for h in bad_sweep))
        print("In AUTO the scope free-runs and triggers itself when no real")
        print("trigger arrives, so it reports a successful capture full of")
        print("noise. In NORM it re-arms after each trigger and the next one")
        print("overwrites your shot. Fix with:")
        print("    python compare_scopes.py --set-sweep SINGle")

    depths = {results[h].get("memory depth") for h in hosts}
    if len(depths) > 1:
        print("\nMEMORY DEPTH differs, so the scopes record different numbers")
        print("of points for the same shot. Pin them all with:")
        print("    python compare_scopes.py --set-depth 1M")

    print("\nRows marked (per scope) are supposed to differ. V/div, offset and")
    print("probe ratio describe what each scope is measuring. Do not normalize")
    print("them, and check the probe ratios against the physical dividers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())