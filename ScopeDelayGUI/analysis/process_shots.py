"""Process shots into MATLAB-compatible .mat files, plots and a summary.

Replaces process_shots.m. Same session discovery, same per-shot status,
same shot_NNNN.mat layout, so ltgs_gui3.m still opens the results.

Usage (from the repo folder):
    python -m analysis.process_shots                  all sessions under .\\logs
    python -m analysis.process_shots D:\\data\\logs     all sessions under a folder
    python -m analysis.process_shots --session <dir>  one session folder
    python -m analysis.process_shots --session <dir> --shot 18
    add --force to reprocess shots that are already done
    add --open to open the new plots when finished

Output:
    <logs>/processed_shots/shot_NNNN.mat   one per shot (ltgs_gui3 reads these)
    <logs>/processed_shots/shot_summary.csv
    <logs>/processed_shots/summary.png     peaks and spacing over all shots
    <session>/shot_NNNN_analysis.png       4-panel figure, fired shots
    <session>/shot_NNNN_raw.png            all 12 channels, every shot

Every line printed starts with "[ANALYSIS]" so the GUI can put it in its log.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path

import numpy as np

from . import pipeline as P

# Bump when the pipeline or the plots change: shots processed by an older
# version are redone automatically on the next run.
PIPELINE_VERSION = "py-1"

SUMMARY_COLS = [
    "shot_number", "stamp", "session_shot_index", "datetime", "status",
    "pressure_psi", "wj1_charge_kv", "wj2_charge_kv",
    "spacing_cmd_ns", "spacing_qsw_ns", "spacing_rvm_ns",
    "LTGS1_Ddot_kV", "LTGS2_Ddot_kV", "LTGS1_Bdot_kV", "LTGS2_Bdot_kV",
    "C225_Ddot_kV", "C315_Bdot_kV", "RVM1_kV", "RVM2_kV",
    "t_Qsw1_us", "t_Qsw2_us", "rvm_gain_1", "rvm_gain_2", "G_consistency",
    "master_interlock_pass", "error",
    # added after the MATLAB columns
    "qsw1_rise_from_trigger_us", "qsw2_rise_from_trigger_us",
    "analysis_png", "raw_png", "pipeline_version",
]


def say(msg):
    try:
        print(f"[ANALYSIS] {msg}", flush=True)
    except (BrokenPipeError, OSError):
        pass


# ===================== session discovery =====================
def find_sessions(root: Path):
    if root.name.startswith("experiment_log_"):
        return [root]
    out = []
    for p in sorted(root.iterdir()):
        if not p.is_dir() or p.name == "processed_shots":
            continue
        if p.name.startswith("experiment_log_"):
            out.append(p)
        else:
            out.extend(find_sessions(p))
    return sorted(out)


def default_name(k, stamp, idx):
    return f"rigol{k}_{stamp}_shot{idx:02d}.csv" if idx > 1 else f"rigol{k}_{stamp}.csv"


def matlab_name(h):
    n = re.sub(r"[^A-Za-z0-9_]", "_", h.strip())
    if not n or not n[0].isalpha():
        n = "x" + n
    return n[:63]


def session_shots(sdir: Path, stamp: str):
    log = sdir / f"shot_log_{stamp}.csv"
    shots = []
    if log.exists():
        with open(log, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        if not rows:
            return shots
        hdr = [matlab_name(h) for h in rows[0]]
        for vals in rows[1:]:
            if not any(v.strip() for v in vals):
                continue
            meta = {h: (vals[i] if i < len(vals) else "") for i, h in enumerate(hdr)}
            idx = _num(meta.get("session_shot_index")) or 1
            idx = int(idx) if np.isfinite(idx) else 1
            files = [sdir / (meta.get(f"rigol{k}_file") or default_name(k, stamp, idx))
                     for k in (1, 2, 3)]
            shots.append({"shot_number": _num(meta.get("shot_number")),
                          "session_shot_index": idx, "files": files, "meta": meta})
        return shots
    files = [sdir / default_name(k, stamp, 1) for k in (1, 2, 3)]
    if any(f.exists() for f in files):
        shots.append({"shot_number": np.nan, "session_shot_index": 1,
                      "files": files, "meta": {}})
    return shots


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return np.nan


def settings_from_meta(meta):
    g = lambda f: meta.get(f, "") or ""  # noqa: E731
    st = {
        "datetime": g("datetime"),
        "pressure_psi": _num(g("pressure_psi")),
        "pressure_age_ms": _num(g("pressure_age_ms")),
        "wj1_charge_kv": _num(g("wj1_charge_kv")),
        "wj2_charge_kv": _num(g("wj2_charge_kv")),
        "wj1_program_kv": _num(g("wj1_program_kv")),
        "wj2_program_kv": _num(g("wj2_program_kv")),
        "pulse_spacing_cmd_ns": _num(g("pulse_spacing_ns")),
        "bnc575_A_delay_us": _num(g("bnc575_A_delay_us")),
        "bnc575_B_delay_us": _num(g("bnc575_B_delay_us")),
    }
    for c in "ABCD":
        st[f"dg535_{c}_delay_us"] = _num(g(f"dg535_laser_{c}_delay_us"))
        st[f"dg535_{c}_ref"] = g(f"dg535_laser_{c}_ref")
    st["master_interlock_pass"] = _num(g("master_interlock_pass"))
    st["failed_interlocks"] = g("failed_interlocks")
    st["notes"] = g("notes")
    return st


# ===================== one shot =====================
def process_one(sh, sdir: Path, stamp: str, out_dir: Path, plots=True):
    if np.isfinite(sh["shot_number"]):
        key = f"shot_{int(sh['shot_number']):04d}"
        name = f"#{int(sh['shot_number']):04d}"
    else:
        key = f"shot_{stamp}" + (f"_{sh['session_shot_index']:02d}"
                                 if sh["session_shot_index"] > 1 else "")
        name = stamp
    S = {
        "key": key, "name": name, "stamp": stamp, "session_dir": str(sdir),
        "shot_number": sh["shot_number"],
        "session_shot_index": float(sh["session_shot_index"]),
        "files": [str(f) for f in sh["files"]],
        "meta": sh["meta"], "settings": settings_from_meta(sh["meta"]),
        "status": "ok", "error": "", "peaks": {},
        "qsw_rise_trig_us": np.array([np.nan, np.nan]),
        "pipeline_version": PIPELINE_VERSION,
    }
    have = [f.exists() for f in sh["files"]]
    scopes = {}
    if not all(have):
        S["status"] = "missing_waveforms"
        first = next(f for f, h in zip(sh["files"], have) if not h)
        S["error"] = f"{have.count(False)} of 3 waveform files missing, first: {first.name}"
    for k, (f, h) in enumerate(zip(sh["files"], have), start=1):
        if h:
            try:
                scopes[k] = P.read_rigol(f)
            except Exception as e:  # noqa: BLE001
                S["status"] = "failed"
                S["error"] = f"could not read {f.name}: {e}"

    # Q-switch rise from the scope trigger. Measured on every shot with a
    # rigol3 file, so dry runs still check the laser DG535 timing.
    if 3 in scopes:
        t3 = scopes[3][:, 0]
        for i, col in enumerate((1, 2)):
            _, tr = P.gate_qsw(t3, scopes[3][:, col])
            S["qsw_rise_trig_us"][i] = tr * 1e6

    if S["status"] == "ok":
        try:
            W = P.process_waveforms(scopes[1], scopes[2], scopes[3])
            S.update(W)
        except P.NoPulse as e:
            S["status"] = "no_fire"
            S["error"] = str(e)
        except Exception as e:  # noqa: BLE001
            S["status"] = "failed"
            S["error"] = f"{type(e).__name__}: {e}"
            traceback.print_exc()

    S["spacing_rvm_ns"] = P.spacing_from_rvm(S) if S["status"] == "ok" else np.nan
    if S["status"] == "ok":
        S["spacing_qsw_ns"] = P.spacing_from_qsw(S)
    else:
        q = S["qsw_rise_trig_us"]
        S["spacing_qsw_ns"] = (q[1] - q[0]) * 1e3

    S["analysis_png"] = ""
    S["raw_png"] = ""
    if plots:
        from . import plots as PL
        if S["status"] == "ok":
            p = sdir / f"{key}_analysis.png"
            PL.analysis_figure(S, p)
            S["analysis_png"] = str(p)
        if scopes:
            p = sdir / f"{key}_raw.png"
            PL.raw_figure(S, scopes, p)
            S["raw_png"] = str(p)

    save_mat(out_dir / f"{key}.mat", S)
    return S


# ===================== MATLAB file =====================
def _to_mat(x):
    if isinstance(x, dict):
        return {matlab_name(str(k)): _to_mat(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        if all(isinstance(v, str) for v in x) or any(isinstance(v, np.ndarray) for v in x):
            c = np.empty((1, len(x)), dtype=object)
            for i, v in enumerate(x):
                c[0, i] = _to_mat(v)
            return c
        return np.asarray(x, dtype=float)
    if x is None:
        return np.array([])
    return x


def save_mat(path: Path, S):
    from scipy.io import savemat
    D = {k: _to_mat(v) for k, v in S.items() if k != "name"}
    # The temp name must not match shot_*.mat, or ltgs_gui3 would try to
    # load a half-written file left by a killed run.
    tmp = path.with_name(f"partial_{path.stem}.mat.tmp")
    savemat(tmp, D, appendmat=False, do_compression=True, oned_as="column",
            long_field_names=True)
    os.replace(tmp, path)


# ===================== summary =====================
def summary_row(S):
    st, pk = S["settings"], S.get("peaks", {})
    g = S.get("rvm_gain", [np.nan, np.nan])
    q = S.get("qsw_rise_trig_us", [np.nan, np.nan])
    return {
        "shot_number": S["shot_number"], "stamp": S["stamp"],
        "session_shot_index": S["session_shot_index"], "datetime": st["datetime"],
        "status": S["status"], "pressure_psi": st["pressure_psi"],
        "wj1_charge_kv": st["wj1_charge_kv"], "wj2_charge_kv": st["wj2_charge_kv"],
        "spacing_cmd_ns": st["pulse_spacing_cmd_ns"],
        "spacing_qsw_ns": S["spacing_qsw_ns"], "spacing_rvm_ns": S["spacing_rvm_ns"],
        "LTGS1_Ddot_kV": pk.get("LTGS1_Ddot"), "LTGS2_Ddot_kV": pk.get("LTGS2_Ddot"),
        "LTGS1_Bdot_kV": pk.get("LTGS1_Bdot"), "LTGS2_Bdot_kV": pk.get("LTGS2_Bdot"),
        "C225_Ddot_kV": pk.get("C225_Ddot"), "C315_Bdot_kV": pk.get("C315_Bdot"),
        "RVM1_kV": pk.get("RVM1"), "RVM2_kV": pk.get("RVM2"),
        "t_Qsw1_us": pk.get("t_Qsw1"), "t_Qsw2_us": pk.get("t_Qsw2"),
        "rvm_gain_1": g[0], "rvm_gain_2": g[1],
        "G_consistency": S.get("G_consistency"),
        "master_interlock_pass": st["master_interlock_pass"], "error": S["error"],
        "qsw1_rise_from_trigger_us": q[0], "qsw2_rise_from_trigger_us": q[1],
        "analysis_png": S["analysis_png"], "raw_png": S["raw_png"],
        "pipeline_version": S["pipeline_version"],
        "label": S["name"],
    }


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    return "" if not np.isfinite(v) else f"{v:.6g}"


def write_summary(path: Path, rows):
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(SUMMARY_COLS)
        for r in rows:
            w.writerow([_fmt(r.get(c)) for c in SUMMARY_COLS])
    os.replace(tmp, path)


def _sort_key(r):
    n = _num(r.get("shot_number"))
    return (1, n, "") if np.isfinite(n) else (0, 0, str(r.get("stamp")))


# ===================== driver =====================
def run(root=None, session=None, shot=None, force=False, plots=True, open_plots=False):
    t_all = time.time()
    if session:
        sdir = Path(session).resolve()
        sessions = [sdir]
        root = Path(root).resolve() if root else sdir.parent.parent
    else:
        root = Path(root or "logs").resolve()
        sessions = find_sessions(root)
    out_dir = root / "processed_shots"
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("partial_*.mat.tmp"):   # left by a killed run
        try:
            stale.unlink()
        except OSError:
            pass
    cache_path = out_dir / "summary_cache.json"
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}

    say(f"{len(sessions)} session folder(s) under {root}")
    counts = {"ok": 0, "no_fire": 0, "missing_waveforms": 0, "failed": 0, "cached": 0}
    new_pngs = []
    for sdir in sessions:
        stamp = sdir.name.replace("experiment_log_", "")
        for sh in session_shots(sdir, stamp):
            if shot is not None and sh["shot_number"] != shot:
                continue
            key = (f"shot_{int(sh['shot_number']):04d}" if np.isfinite(sh["shot_number"])
                   else f"shot_{stamp}" + (f"_{sh['session_shot_index']:02d}"
                                           if sh["session_shot_index"] > 1 else ""))
            c = cache.get(key)
            if (not force and c and c["row"].get("pipeline_version") == PIPELINE_VERSION
                    and c["row"]["status"] != "missing_waveforms"
                    and (out_dir / f"{key}.mat").exists()):
                counts["cached"] += 1
                continue
            t0 = time.time()
            S = process_one(sh, sdir, stamp, out_dir, plots=plots)
            row = summary_row(S)
            cache[key] = {"row": {k: _fmt(v) for k, v in row.items()}}
            counts[S["status"]] += 1
            new_pngs += [p for p in (S["analysis_png"], S["raw_png"]) if p]
            dt = time.time() - t0
            if S["status"] == "ok":
                pk = S["peaks"]
                say(f"{S['name']}: OK in {dt:.1f} s  D {_fmt(round(pk['LTGS1_Ddot']))}/"
                    f"{_fmt(round(pk['LTGS2_Ddot']))} kV  RVM {_fmt(round(pk['RVM1']))}/"
                    f"{_fmt(round(pk['RVM2']))} kV  spacing cmd "
                    f"{_fmt(S['settings']['pulse_spacing_cmd_ns'])} / Qsw "
                    f"{_fmt(round(S['spacing_qsw_ns'], 1))} / RVM "
                    f"{_fmt(round(S['spacing_rvm_ns'], 1))} ns")
            else:
                q = S["spacing_qsw_ns"]
                extra = (f"  Q-switch spacing {q:.1f} ns (cmd "
                         f"{_fmt(S['settings']['pulse_spacing_cmd_ns'])})"
                         if np.isfinite(q) else "")
                say(f"{S['name']}: {S['status']} ({S['error']}){extra}")
            say("result " + json.dumps({
                "shot_number": None if not np.isfinite(sh["shot_number"]) else int(sh["shot_number"]),
                "key": key, "status": S["status"],
                "spacing_cmd_ns": _fmt(S["settings"]["pulse_spacing_cmd_ns"]),
                "spacing_qsw_ns": _fmt(S["spacing_qsw_ns"]),
                "spacing_rvm_ns": _fmt(S["spacing_rvm_ns"]),
                "analysis_png": S["analysis_png"], "raw_png": S["raw_png"],
                "error": S["error"]}))
            cache_path.write_text(json.dumps(cache, indent=1), encoding="utf-8")

    rows = sorted((v["row"] for v in cache.values()), key=_sort_key)
    write_summary(out_dir / "shot_summary.csv", rows)
    if plots and rows:
        from . import plots as PL
        PL.summary_figure(rows, out_dir / "summary.png")
    say(f"done in {time.time() - t_all:.1f} s: {counts['ok']} fired, "
        f"{counts['no_fire']} dry, {counts['missing_waveforms']} missing files, "
        f"{counts['failed']} failed, {counts['cached']} already done")
    say(f"summary: {out_dir / 'shot_summary.csv'}")
    for p in new_pngs:
        say(f"plot: {p}")
    if open_plots:
        from . import plots as PL
        for p in new_pngs:
            PL.open_file(p)
    return counts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", default=None, help="logs folder (default .\\logs)")
    ap.add_argument("--session", help="process one session folder")
    ap.add_argument("--shot", type=int, help="only this global shot number")
    ap.add_argument("--force", action="store_true", help="redo shots already processed")
    ap.add_argument("--no-plots", action="store_true", help="skip the PNG figures")
    ap.add_argument("--open", action="store_true", help="open the new plots when done")
    a = ap.parse_args(argv)
    try:
        c = run(a.root, a.session, a.shot, a.force, not a.no_plots, a.open)
    except Exception as e:  # noqa: BLE001
        say(f"ERROR {type(e).__name__}: {e}")
        traceback.print_exc()
        return 2
    return 1 if c["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
