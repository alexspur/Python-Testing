# utils/shot_snapshot.py
"""
Turn a frozen SystemState snapshot into one shot row.

Pure data: no hardware access, no file access, no locks. main_window copies
the state under its lock, releases it, then calls build_shot_row() here.

Unit convention: every delay column is microseconds with 6 decimals (1 ps
resolution, so nanosecond timing is never rounded away), and the column names
carry the unit. Missing values are blank rather than invented; a value that is
known to be unavailable is "UNKNOWN".
"""

from utils.system_state import SystemState, UNKNOWN

# DG535 channel ids from instruments/dg535.py (T0=1, A=2, B=3, AB=4, C=5, D=6, CD=7).
DG535_CHANNEL_NAMES = {1: "T0", 2: "A", 3: "B", 4: "AB", 5: "C", 6: "D", 7: "CD"}

# Laser DG535 channel map, as wired on this system:
#   A = laser 1 flashlamp, B = laser 1 Q-switch
#   C = laser 2 flashlamp, D = laser 2 Q-switch
LASER1_QSWITCH = "B"
LASER2_QSWITCH = "D"


def fmt(value, blank=""):
    """Render a scalar for CSV: None becomes blank, bools become 1/0."""
    if value is None:
        return blank
    if isinstance(value, bool):
        return "1" if value else "0"
    return value


def fmt_us(seconds, decimals=6):
    """Seconds -> microseconds string. 6 decimals keeps ps resolution."""
    if seconds is None:
        return ""
    try:
        return f"{float(seconds) * 1e6:.{decimals}f}"
    except (TypeError, ValueError):
        return ""


def fmt_float(value, decimals=3):
    if value is None:
        return ""
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return ""


def fmt_age(age_ms):
    if age_ms is None:
        return ""
    return f"{age_ms:.0f}"


def channel_name(ref):
    """Accept a DG535 reference as an id (2) or a name ('A') and return a name."""
    if ref is None:
        return None
    if isinstance(ref, str):
        return ref.strip().upper() or None
    return DG535_CHANNEL_NAMES.get(int(ref))


def resolve_absolute_delays(channels):
    """Resolve each channel's delay to an absolute time from T0.

    channels: {"A": {"ref": "T0"|"A"|2|..., "delay_s": float}, ...}

    DG535 delays are relative to a reference channel, which may itself be
    relative to another (the live instrument has B referenced to A and D to
    C). Walking the chain to T0 is the only way to compare two channels.

    Returns {"A": seconds_from_T0 or None}. A channel is None when its chain
    is broken, circular, or ends somewhere other than T0.
    """
    resolved = {}

    def walk(name, seen):
        if name in resolved:
            return resolved[name]
        if name == "T0":
            return 0.0
        entry = channels.get(name)
        if not entry:
            return None
        if name in seen:            # circular reference
            return None
        ref = channel_name(entry.get("ref"))
        delay = entry.get("delay_s")
        if ref is None or delay is None:
            return None
        base = walk(ref, seen | {name})
        if base is None:
            return None
        return base + float(delay)

    for ch in channels:
        resolved[ch] = walk(ch, set())
    return resolved


def pulse_spacing_ns(channels):
    """Laser 2 Q-switch minus laser 1 Q-switch, in ns.

    Both Q-switch channels are resolved to absolute time from T0 first, so
    this is correct whether D is referenced to B, to C, or to T0. Returns None
    if either chain cannot be resolved (the caller leaves the column blank).
    """
    absolute = resolve_absolute_delays(channels)
    q1 = absolute.get(LASER1_QSWITCH)
    q2 = absolute.get(LASER2_QSWITCH)
    if q1 is None or q2 is None:
        return None
    return (q2 - q1) * 1e9


def build_shot_row(snapshot, shot_number, session_shot_index, datetime_str,
                   timestamp_sec, session_dir, experiment_log_file,
                   gui_version, scope_files=None, notes=""):
    """Build the full shot row dict from a frozen snapshot.

    snapshot: SystemState.snapshot() output (already deep-copied)
    scope_files: {1: "rigol1_...csv", ...} relative to the session directory
    """
    scope_files = scope_files or {}
    notes_parts = [notes] if notes else []
    row = {
        "shot_number": shot_number,
        "session_shot_index": session_shot_index,
        "datetime": datetime_str,
        "timestamp_sec": f"{timestamp_sec:.6f}",
        "session_dir": session_dir,
        "experiment_log_file": experiment_log_file,
        "gui_version": gui_version,
    }

    # ---------------------------------------------------------- pressure
    pressure = snapshot.get("pressure") or {}
    if pressure:
        row.update({
            "pressure_psi": fmt_float(pressure.get("psi"), 2),
            "pressure_volts": fmt_float(pressure.get("volts"), 3),
            "pressure_counts": fmt(pressure.get("counts")),
            "pressure_status": pressure.get("status", UNKNOWN),
            "pressure_sample_time": pressure.get("sample_time", ""),
            "pressure_age_ms": fmt_age(SystemState.age_ms(pressure)),
        })
    else:
        # Fresh GUI, no poll has landed yet (or the link is down).
        row["pressure_status"] = UNKNOWN
        notes_parts.append("no pressure sample at shot time")

    # ---------------------------------------------------------- WJ supplies
    for unit in ("wj1", "wj2"):
        sec = snapshot.get(unit) or {}
        if not sec:
            notes_parts.append(f"{unit} state unknown")
            continue
        row.update({
            f"{unit}_program_kv": fmt_float(sec.get("program_kv"), 3),
            f"{unit}_measured_kv": fmt_float(sec.get("measured_kv"), 3),
            f"{unit}_current_ma": fmt_float(sec.get("current_ma"), 4),
            f"{unit}_hv_on": fmt(sec.get("hv_on")),
            f"{unit}_fault": fmt(sec.get("fault")),
            f"{unit}_connected": fmt(sec.get("connected")),
            f"{unit}_age_ms": fmt_age(SystemState.age_ms(sec)),
            # Values cached while HV was still on (before the pre-fire dump).
            f"{unit}_charge_kv": fmt_float(sec.get("charge_kv"), 3),
            f"{unit}_charge_ma": fmt_float(sec.get("charge_ma"), 4),
            f"{unit}_charge_age_ms": fmt_age(sec.get("charge_age_ms")),
        })

    # ---------------------------------------------------------- BNC575
    bnc = snapshot.get("bnc575") or {}
    bnc_channels = bnc.get("channels") or {}
    row.update({
        "bnc575_trigger_mode": bnc.get("trigger_mode", UNKNOWN),
        "bnc575_system_mode": bnc.get("system_mode", UNKNOWN),
        "bnc575_period_s": fmt_float(bnc.get("period_s"), 9),
        "bnc575_armed": fmt(bnc.get("armed")),
        "bnc575_config_source": SystemState.source_of(bnc),
    })
    for ch in ("A", "B", "C", "D"):
        entry = bnc_channels.get(ch) or {}
        row.update({
            f"bnc575_{ch}_delay_us": fmt_us(entry.get("delay_s")),
            f"bnc575_{ch}_width_us": fmt_us(entry.get("width_s")),
            f"bnc575_{ch}_enabled": fmt(entry.get("enabled")),
            f"bnc575_{ch}_polarity": entry.get("polarity", ""),
        })
    if not bnc_channels:
        notes_parts.append("BNC575 config not read back")

    # ---------------------------------------------------------- laser DG535
    dg = snapshot.get("dg535_laser") or {}
    dg_channels = dg.get("channels") or {}
    row.update({
        "dg535_laser_trigger_mode": dg.get("trigger_mode", UNKNOWN),
        "dg535_laser_config_source": SystemState.source_of(dg),
    })
    for ch in ("A", "B", "C", "D"):
        entry = dg_channels.get(ch) or {}
        row[f"dg535_laser_{ch}_delay_us"] = fmt_us(entry.get("delay_s"))
        row[f"dg535_laser_{ch}_ref"] = channel_name(entry.get("ref")) or ""
    spacing = pulse_spacing_ns(dg_channels) if dg_channels else None
    row["pulse_spacing_ns"] = "" if spacing is None else f"{spacing:.1f}"
    if not dg_channels:
        notes_parts.append("laser DG535 config not read back")
    elif spacing is None:
        notes_parts.append("pulse spacing unresolved (reference chain)")

    # ---------------------------------------------------------- lasers
    for tag, key in (("laser1", "laser1"), ("laser2", "laser2")):
        sec = snapshot.get(key) or {}
        row.update({
            f"{tag}_armed": fmt(sec.get("armed")),
            f"{tag}_interlock_ok": fmt(sec.get("interlock_ok")),
            f"{tag}_fault": fmt(sec.get("fault")),
            f"{tag}_state": sec.get("state", ""),
            f"{tag}_mode": sec.get("mode", ""),
        })

    # ---------------------------------------------------------- relays
    relays = snapshot.get("relays") or {}
    states = relays.get("states") or {}
    for column, name in (
        ("charge_positive_relay", "charge_positive"),
        ("charge_negative_relay", "charge_negative"),
        ("discharge_positive_relay", "discharge_positive"),
        ("discharge_negative_relay", "discharge_negative"),
    ):
        value = states.get(name)
        row[column] = UNKNOWN if value is None else fmt(value)
    row["relay_state_source"] = relays.get("source", UNKNOWN)

    # ---------------------------------------------------------- interlocks
    interlocks = snapshot.get("interlocks") or {}
    row.update({
        "master_interlock_pass": fmt(interlocks.get("master_pass")),
        "failed_interlocks": ";".join(interlocks.get("failed", [])) or "",
        "interlock_manual_overrides": ";".join(interlocks.get("manual", [])) or "",
    })

    # ---------------------------------------------------------- scopes
    for scope_id in (1, 2, 3):
        sec = snapshot.get(f"rigol{scope_id}") or {}
        row.update({
            f"rigol{scope_id}_armed": fmt(sec.get("armed")),
            f"rigol{scope_id}_capture_ok": fmt(sec.get("capture_ok")),
            f"rigol{scope_id}_file": scope_files.get(scope_id, sec.get("file", "")),
            # Left blank at t0 on purpose. The export has not run yet, so the
            # row cannot honestly claim the file exists; the report fills this
            # in from SCOPE_EXPORT events and a check against the disk.
            f"rigol{scope_id}_file_written": "",
        })

    row["notes"] = "; ".join(p for p in notes_parts if p)
    return row
