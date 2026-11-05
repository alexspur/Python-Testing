"""Scope channel assignments and probe calibrations, by shot number.

THIS IS THE ONLY PLACE THE WIRING IS WRITTEN DOWN. When the cables move:
  1. add any new probe to PROBES (serial -> calibration factor),
  2. append a new entry to WIRINGS with the first shot number it applies to.
Earlier entries keep serving earlier shots, so old shot_NNNN.mat files come
out the same when reprocessed.

Each WIRINGS entry has, per scope, one line per channel:
    channel: (signal, kind, probe)      or None when nothing is connected

signal   the name the pipeline knows the channel by. Fixed names with their
         own processing: LTGS1_Ddot, LTGS2_Ddot, LTGS1_Bdot, LTGS2_Bdot,
         RVM1, RVM2, Qsw1, Qsw2, TrigMon, TrigOut. Any other name with kind
         ddot or bdot is an output probe (C225, A225, ...): integrated and
         saved as <name>_t / <name> with peak <name>_Ddot or <name>_Bdot.
kind     ddot  D-dot, integrated with the probe factor -> kV
         bdot  B-dot, integrated with probe factor * geom * bScale -> Z*I kV
         rvm   resistive voltage monitor, probe = divider correction
         qsw   laser Q-switch monitor, gated raw volts
         raw   recorded but not processed (CVR, trigger lines)
probe    key into PROBES, or None for raw / qsw channels
anchors  (scope, channel) pairs whose activity defines the pulse window

LTGS1_Ddot, LTGS2_Ddot, RVM1 and RVM2 must be present in every wiring; the
RVM-referenced D-dot correction needs all four. Everything else is optional
and leaves empty traces and NaN peaks when absent.
"""

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
}

# Scope 1 has not changed.
_RIGOL1 = {
    1: ("RVM1", "rvm", "RVM1"),
    2: ("RVM2", "rvm", "RVM2"),
    3: ("TrigMon", "raw", None),
    4: ("TrigOut", "raw", None),
}

WIRINGS = [
    {
        "from_shot": 0,
        "note": "July 2026 wiring (shots 1-64 and the unnumbered July files)",
        "rigol1": _RIGOL1,
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
    },
    {
        "from_shot": 65,
        "note": "Nov 2026 tests: A225 / B225 / C225 D-dots, CVR, no B-dots, no Q-switches",
        "rigol1": _RIGOL1,
        "rigol2": {
            1: ("LTGS2_Ddot", "ddot", "2019FC011"),
            2: None,
            3: ("LTGS1_Ddot", "ddot", "2019FC017"),
            4: ("A225", "ddot", "2019FC033"),
        },
        "rigol3": {
            1: None,
            2: ("CVR", "raw", None),
            3: ("B225", "ddot", "2019FC030"),
            4: ("C225", "ddot", "2019FC032"),
        },
        "anchors": [("rigol2", 3), ("rigol2", 1), ("rigol3", 4)],
    },
]


# ===================== lookups =====================
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


def channel_names(wiring):
    """{"rigol1": [4 names], ...}, "" for an unused channel. Saved into the
    .mat as S.channels and used for the raw-channel figure titles."""
    return {f"rigol{k}": [(wiring[f"rigol{k}"].get(ch) or ("",))[0] for ch in (1, 2, 3, 4)]
            for k in (1, 2, 3)}
