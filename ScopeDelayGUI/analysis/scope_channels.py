"""Scope channel assignments and probe calibrations, by shot number.

THIS IS THE ONLY PLACE THE WIRING IS WRITTEN DOWN. Three tables:

  PROBES    probe serial -> calibration factor. Add a line for a new probe.
  LAYOUTS   one named dict per way the scopes have been cabled.
  SCHEDULE  (first shot number, layout) pairs. The last pair whose shot
            number is <= the shot wins. Add a pair when the cables move.

Going back to an earlier cabling is one SCHEDULE line that names the old
layout again. A new cabling is a new LAYOUTS entry plus one SCHEDULE line.
Earlier shots keep their own layout, so old shot_NNNN.mat files come out
the same when reprocessed. Shots processed before the change are cached:
redo one with  python -m analysis ..\\logs --force --shot N

Check what a shot number resolves to, from the ScopeDelayGUI folder:
    python -m analysis.scope_channels          the schedule
    python -m analysis.scope_channels 80       the layout shot 80 gets

A layout has, per scope, one line per channel:
    channel: (signal, kind, probe)      or None when nothing is connected

signal   the name the pipeline knows the channel by. Fixed names with their
         own processing: LTGS1_Ddot, LTGS2_Ddot, LTGS1_Bdot, LTGS2_Bdot,
         RVM1, RVM2, CVR, Qsw1, Qsw2, TrigMon, TrigOut. Any other name with kind
         ddot or bdot is an output probe (C225, A225, ...): integrated and
         saved as <name>_t / <name> with peak <name>_Ddot or <name>_Bdot,
         and picked up by name in ltgs_gui3.
kind     ddot  D-dot, integrated with the probe factor -> kV
         bdot  B-dot, integrated with probe factor * geom * bScale -> Z*I kV
         rvm   resistive voltage monitor, probe = divider correction
         cvr   current viewing resistor, probe = amps per scope volt; saved
               as CVR_A and as CVR_kV = CVR_A * LOAD_OHM / 1e3
         qsw   laser Q-switch monitor, gated raw volts
         raw   recorded but not processed (uncalibrated probes, trigger lines)
probe    key into PROBES, or None for raw / qsw channels
anchors  (scope, channel) pairs whose activity defines the pulse window

LTGS1_Ddot, LTGS2_Ddot, RVM1 and RVM2 must be present in every layout; the
RVM-referenced D-dot correction needs all four. Everything else is optional
and leaves empty traces and NaN peaks when absent. The file checks all of
this when it is imported and stops with a plain message on a mistake.
"""

# ===================== probes =====================
# Calibration factor by probe serial (L-3 certificates, 2019). D-dots in
# V/(V*s), B-dots in A/(V*s*in). The 20 dB pads are already in the scope
# probe ratio (x10), so exported volts include them.
PROBES = {
    "2019FC011": 1.85e11,    # LTGS2-232 D-dot
    "2019FC013": -6.51e8,    # LTGS2-007 B-dot
    "2019FC017": 1.83e11,    # LTGS1-232 D-dot
    "2019FC016": -6.70e8,    # LTGS1-007 B-dot
    "2019FC027": -6.96e8,    # C315 B-dot
    "2019FC032": 1.56e11,    # C225 D-dot
    "2019FC033": 1.56e11,    # A225 D-dot
    "2019FC030": 1.64e11,    # B225 D-dot
    "RVM1": 19588.6 / 20000,  # scope probe ratio is 20000:1; this corrects it
    "RVM2": 19970.7 / 20000,
    "CVR": 1 / 0.00980,       # 9.80 milliohm CVR: amps per scope volt
}

# Total series resistance the CVR current flows through, including the CVR
# itself, ohm. CVR_kV = CVR_A * LOAD_OHM / 1e3 is the voltage across it.
LOAD_OHM = 204.6

# ===================== layouts =====================
# Scope 1 has been the same in every layout so far.
RIGOL1_STANDARD = {
    1: ("RVM1", "rvm", "RVM1"),
    2: ("RVM2", "rvm", "RVM2"),
    3: ("TrigMon", "raw", None),
    4: ("TrigOut", "raw", None),
}

JULY_2026 = {
    "name": "JULY_2026",
    "note": "LTGS D-dots and B-dots on scope 2; Q-switches, C315, C225 on scope 3",
    "rigol1": RIGOL1_STANDARD,
    "rigol2": {
        1: ("LTGS2_Ddot", "ddot", "2019FC011"),
        2: ("LTGS2_Bdot", "bdot", "2019FC013"),
        3: ("LTGS1_Ddot", "ddot", "2019FC017"),
        4: ("LTGS1_Bdot", "bdot", "2019FC016"),
    },
    "rigol3": {
        1: ("Qsw1", "qsw", None),
        2: ("Qsw2", "qsw", None),
        3: ("C315", "bdot", "2019FC027"),
        4: ("C225", "ddot", "2019FC032"),
    },
    "anchors": [("rigol2", 3), ("rigol2", 4), ("rigol3", 4)],
}

NOV_2026_TESTS = {
    "name": "NOV_2026_TESTS",
    "note": "A225 / B225 / C225 D-dots and CVR; no LTGS B-dots, no Q-switches",
    "rigol1": RIGOL1_STANDARD,
    "rigol2": {
        1: ("LTGS2_Ddot", "ddot", "2019FC011"),
        2: None,
        3: ("LTGS1_Ddot", "ddot", "2019FC017"),
        4: ("A225", "ddot", "2019FC033"),
    },
    "rigol3": {
        1: None,
        2: ("CVR", "cvr", "CVR"),
        3: ("B225", "ddot", "2019FC030"),
        4: ("C225", "ddot", "2019FC032"),
    },
    "anchors": [("rigol2", 3), ("rigol2", 1), ("rigol3", 4)],
}

NOV_2026_NE_SW = {
    "name": "NOV_2026_NE_SW",
    "note": "July cabling, but the LTGS B-dots replaced by the NE and SW D-dots "
            "(no calibration: recorded raw, not processed)",
    "rigol1": RIGOL1_STANDARD,
    "rigol2": {
        1: ("LTGS2_Ddot", "ddot", "2019FC011"),
        2: ("NE_Ddot", "raw", None),
        3: ("LTGS1_Ddot", "ddot", "2019FC017"),
        4: ("SW_Ddot", "raw", None),
    },
    "rigol3": JULY_2026["rigol3"],
    "anchors": [("rigol2", 3), ("rigol2", 1), ("rigol3", 4)],
}

NOV_2026_QSW_ON_2 = {
    "name": "NOV_2026_QSW_ON_2",
    "note": "Q-switches moved to scope 2 in place of the NE/SW D-dots; scope 3 is "
            "CVR, C225, NE, SW (NE/SW still raw, no calibration). No C315.",
    "rigol1": RIGOL1_STANDARD,
    "rigol2": {
        1: ("LTGS2_Ddot", "ddot", "2019FC011"),
        2: ("Qsw1", "qsw", None),
        3: ("LTGS1_Ddot", "ddot", "2019FC017"),
        4: ("Qsw2", "qsw", None),
    },
    "rigol3": {
        1: ("CVR", "cvr", "CVR"),
        2: ("C225", "ddot", "2019FC032"),
        3: ("NE_Ddot", "raw", None),
        4: ("SW_Ddot", "raw", None),
    },
    "anchors": [("rigol2", 3), ("rigol2", 1), ("rigol3", 2)],
}

LAYOUTS = [JULY_2026, NOV_2026_TESTS, NOV_2026_NE_SW, NOV_2026_QSW_ON_2]

# ===================== schedule =====================
# (first shot number, layout). Keep it in shot order. Unnumbered shots (the
# July files with no shot log) get the first line.
SCHEDULE = [
    (0, JULY_2026),           # shots 1-64
    (65, NOV_2026_TESTS),     # 2 to 16 Nov 2026
    (72, JULY_2026),          # back to the July cabling, 16 Nov 2026
    (77, NOV_2026_NE_SW),     # NE / SW D-dots in place of the LTGS B-dots, 16 Nov 2026
    (79, NOV_2026_QSW_ON_2),  # Q-switches on scope 2, CVR/C225/NE/SW on scope 3, 17 Nov 2026
]


# ===================== derived table and lookups =====================
# One entry per SCHEDULE line, each a layout plus its from_shot. This is
# what the pipeline and the tests use.
WIRINGS = [dict(layout, from_shot=first) for first, layout in SCHEDULE]

REQUIRED = ("LTGS1_Ddot", "LTGS2_Ddot", "RVM1", "RVM2")
KINDS = ("ddot", "bdot", "rvm", "cvr", "qsw", "raw")


def wiring_for(shot_number):
    """The WIRINGS entry for a shot. Unnumbered shots (NaN) get the first."""
    try:
        n = float(shot_number)
    except (TypeError, ValueError):
        n = float("nan")
    chosen = WIRINGS[0]
    for w in WIRINGS:
        if n >= w["from_shot"]:
            chosen = w
    return chosen


def scope_channel(wiring, signal):
    """(scope number, column in the CSV, calibration factor) of a signal in
    a wiring, or None when that wiring does not record it. The column is
    the channel number, since column 0 of a Rigol export is time."""
    for k in (1, 2, 3):
        for ch, entry in wiring[f"rigol{k}"].items():
            if entry and entry[0] == signal:
                probe = entry[2]
                cf = PROBES[probe] if probe is not None else 1.0
                return k, int(ch), cf
    return None


def output_probes(wiring):
    """[(signal, kind, scope, column, cf)] for every ddot/bdot channel that
    is not one of the LTGS probes, in name order."""
    out = []
    for k in (1, 2, 3):
        for ch, entry in wiring[f"rigol{k}"].items():
            if not entry:
                continue
            name, kind, probe = entry
            if kind in ("ddot", "bdot") and not name.startswith("LTGS"):
                out.append((name, kind, k, int(ch), PROBES[probe]))
    return sorted(out)


def raw_channels(wiring):
    """[(signal, scope, column)] for every kind-raw channel except the scope 1
    trigger lines, which have their own fields. Saved into the .mat as
    raw_<signal>_t / raw_<signal>_v for ltgs_gui4 to plot and integrate."""
    out = []
    for k in (1, 2, 3):
        for ch, entry in wiring[f"rigol{k}"].items():
            if entry and entry[1] == "raw" and entry[0] not in ("TrigMon", "TrigOut"):
                out.append((entry[0], k, int(ch)))
    return sorted(out)


def channel_names(wiring):
    """{"rigol1": [4 names], ...}, "" for an unused channel. Saved into the
    .mat as S.channels and used for the raw-channel figure titles."""
    return {f"rigol{k}": [(wiring[f"rigol{k}"].get(ch) or ("",))[0] for ch in (1, 2, 3, 4)]
            for k in (1, 2, 3)}


# ===================== self-check =====================
def _check():
    """Catch a typo here instead of halfway through a shot."""
    problems = []
    for lay in LAYOUTS:
        nm = lay.get("name", "?")
        seen = set()
        for k in (1, 2, 3):
            table = lay.get(f"rigol{k}")
            if not isinstance(table, dict):
                problems.append(f"{nm}: rigol{k} table missing")
                continue
            for ch, entry in table.items():
                if ch not in (1, 2, 3, 4):
                    problems.append(f"{nm}: rigol{k} channel {ch!r} is not 1-4")
                if entry is None:
                    continue
                if not (isinstance(entry, tuple) and len(entry) == 3):
                    problems.append(f"{nm}: rigol{k} CH{ch} must be (signal, kind, probe) or None")
                    continue
                signal, kind, probe = entry
                if signal in seen:
                    problems.append(f"{nm}: {signal} appears on two channels")
                seen.add(signal)
                if kind not in KINDS:
                    problems.append(f"{nm}: rigol{k} CH{ch} kind {kind!r} not in {KINDS}")
                if kind in ("ddot", "bdot", "rvm", "cvr") and probe not in PROBES:
                    problems.append(f"{nm}: rigol{k} CH{ch} probe {probe!r} is not in PROBES")
        for req in REQUIRED:
            if req not in seen:
                problems.append(f"{nm}: required signal {req} is not on any channel")
        for scope, ch in lay.get("anchors", []):
            if scope not in ("rigol1", "rigol2", "rigol3") or not lay.get(scope, {}).get(ch):
                problems.append(f"{nm}: anchor ({scope}, {ch}) is not a connected channel")
    firsts = [f for f, _ in SCHEDULE]
    if firsts != sorted(firsts) or len(set(firsts)) != len(firsts):
        problems.append(f"SCHEDULE shot numbers must increase: {firsts}")
    if firsts and firsts[0] != 0:
        problems.append("SCHEDULE must start at shot 0 for the unnumbered July files")
    for first, lay in SCHEDULE:
        if lay not in LAYOUTS:
            problems.append(f"SCHEDULE entry for shot {first} uses a layout that is not in LAYOUTS")
    if problems:
        raise ValueError("scope_channels.py: " + "; ".join(problems))


_check()


# ===================== command line =====================
def describe(wiring):
    """Multi-line text of one wiring: scope by scope, channel by channel."""
    lines = [f"from shot {wiring['from_shot']}: {wiring.get('name', '?')}  ({wiring.get('note', '')})"]
    for k in (1, 2, 3):
        for ch in (1, 2, 3, 4):
            entry = wiring[f"rigol{k}"].get(ch)
            if entry is None:
                lines.append(f"  scope {k} CH{ch}: -")
            else:
                signal, kind, probe = entry
                cf = f"  {PROBES[probe]:.4g}" if probe in PROBES else ""
                lines.append(f"  scope {k} CH{ch}: {signal:<12} {kind:<5} {probe or '':<10}{cf}")
    lines.append("  anchors: " + ", ".join(f"{s} CH{c}" for s, c in wiring["anchors"]))
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(describe(wiring_for(sys.argv[1])))
    else:
        for w in WIRINGS:
            print(describe(w))
            print()
