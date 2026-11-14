"""Export one shot's raw Rigol data to a small .npz file for analysis in chat.

Usage (from any folder):
    python export_shot.py --root "C:\\Users\\ESpurbeck\\Desktop\\LANL Project\\Double Pulse" --shot 43
    python export_shot.py --files rigol1.csv rigol2.csv rigol3.csv --name shot0043

What it saves (raw volts, no processing):
    r1_t, r2_t, r3_t     time of each scope, seconds (float64)
    r1_v, r2_v, r3_v     CH1..CH4 of each scope, volts (float32, n x 4)
    meta                 JSON text: source files, detected pulse times,
                         crop window, channel map, calibration constants

Each scope is cropped to tPulse - pre .. tEnd + post (default 12 us each
side) on its own time axis. Use --full to keep the whole record.
Pulse detection is the same as process_shots.m (10 x noise envelope on
rigol2 CH3, rigol2 CH4 and rigol3 CH4). It is only used for cropping.
"""
import argparse
import csv
import glob
import json
import os
import sys

import numpy as np


CHANNEL_MAP = {
    "rigol1": {"CH1": "RVM 1", "CH2": "RVM 2", "CH3": "?", "CH4": "?"},
    "rigol2": {"CH1": "LTGS2-232 D-dot (FC011)", "CH2": "LTGS2-007 B-dot (FC013)",
               "CH3": "LTGS1-232 D-dot (FC017)", "CH4": "LTGS1-007 B-dot (FC016)"},
    "rigol3": {"CH1": "Laser1 Q-switch", "CH2": "Laser2 Q-switch",
               "CH3": "C315 B-dot (FC027)", "CH4": "C225 D-dot (FC032)"},
}
CONSTANTS = {
    "CF_rigol2_CH1": 1.85e11, "CF_rigol2_CH2": -6.51e8,
    "CF_rigol2_CH3": 1.83e11, "CF_rigol2_CH4": -6.70e8,
    "CF_rigol3_CH3": -6.96e8, "CF_rigol3_CH4": 1.56e11,
    "geom": 2 * np.pi * 7.5, "bScale": -4.5,
    "DIV_rigol1_CH1": 19588.6 / 20000, "DIV_rigol1_CH2": 19970.7 / 20000,
}


def read_rigol(path):
    """Time plus four channels. Skips the one header line."""
    try:
        import pandas as pd
        df = pd.read_csv(path, header=0, usecols=range(5))
        M = df.apply(pd.to_numeric, errors="coerce").to_numpy(dtype=np.float64)
    except ImportError:
        M = np.genfromtxt(path, delimiter=",", skip_header=1, usecols=range(5))
    M = M[np.isfinite(M[:, 0])]
    if M.shape[1] < 5:
        sys.exit(f"{path} has {M.shape[1]} columns, expected time plus 4 channels")
    return M


def detect_activity(t, v, k=10, env_s=200e-9, noise_s=500e-9):
    """Same idea as detect_activity in process_shots.m. Returns (tS, tE) or (None, None)."""
    v0 = v - np.median(v)
    dt = t[1] - t[0]
    wn = max(8, int(round(noise_s / dt)))
    nb = len(v0) // wn
    s = np.sort(v0[: nb * wn].reshape(nb, wn).std(axis=1, ddof=1))
    sig = s[max(0, int(round(0.25 * nb)) - 1)]
    idx = np.flatnonzero(np.abs(v0) > k * sig)
    if idx.size == 0:
        return None, None
    half = max(3, int(round(env_s / dt))) // 2
    i0 = max(0, idx[0] - half)
    i1 = min(len(t) - 1, idx[-1] + half)
    return t[i0], t[i1]


def locate(path, root):
    """Use the path if it exists. Otherwise search under root by file name."""
    if os.path.isfile(path):
        return path
    hits = glob.glob(os.path.join(root, "**", os.path.basename(path)), recursive=True)
    if hits:
        hits.sort(key=lambda p: ("experiment_log_" not in p, len(p)))
        return hits[0]
    return path


def files_from_shot_log(root, shot):
    """Find the three rigol files for a global shot number via the shot logs.
    Logs inside experiment_log_* folders are checked first."""
    logs = glob.glob(os.path.join(root, "**", "shot_log_*.csv"), recursive=True)
    logs.sort(key=lambda p: "experiment_log_" not in os.path.basename(os.path.dirname(p)))
    for log in logs:
        with open(log, newline="", encoding="utf-8", errors="replace") as fh:
            for row in csv.DictReader(fh):
                try:
                    n = int(float(row.get("shot_number", "") or "nan"))
                except ValueError:
                    continue
                if n != shot:
                    continue
                sdir = os.path.dirname(log)
                stamp = os.path.basename(sdir).replace("experiment_log_", "")
                idx = int(float(row.get("session_shot_index", "") or 1))
                out = []
                for k in (1, 2, 3):
                    nm = (row.get(f"rigol{k}_file") or "").strip()
                    if not nm:
                        nm = (f"rigol{k}_{stamp}_shot{idx:02d}.csv" if idx > 1
                              else f"rigol{k}_{stamp}.csv")
                    out.append(locate(os.path.join(sdir, nm), root))
                print(f"shot {shot} found in {log}")
                return out, dict(row)
    sys.exit(f"shot {shot} not found in any shot_log_*.csv under {root}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="Double Pulse folder (searched for shot logs)")
    ap.add_argument("--shot", type=int, help="global shot number, e.g. 43")
    ap.add_argument("--files", nargs=3, metavar=("RIGOL1", "RIGOL2", "RIGOL3"),
                    help="the three rigol CSVs, in order")
    ap.add_argument("--name", help="output name (default shotNNNN)")
    ap.add_argument("--pre", type=float, default=12.0, help="us kept before tPulse")
    ap.add_argument("--post", type=float, default=12.0, help="us kept after tEnd")
    ap.add_argument("--full", action="store_true", help="keep the whole record")
    ap.add_argument("--out", default=".", help="output folder")
    a = ap.parse_args()

    log_row = {}
    if a.files:
        files = a.files
    elif a.root and a.shot is not None:
        files, log_row = files_from_shot_log(a.root, a.shot)
    else:
        ap.error("give --root and --shot, or --files")
    missing = [f for f in files if not os.path.isfile(f)]
    if missing:
        sys.exit("missing file(s), not found anywhere under the root either:\n  "
                 + "\n  ".join(missing))

    name = a.name or (f"shot{a.shot:04d}" if a.shot is not None else "shot")
    print("reading:")
    M = []
    for f in files:
        print("  ", f)
        M.append(read_rigol(f))

    anchors = [(M[1], 3), (M[1], 4), (M[2], 4)]   # rigol2 CH3, rigol2 CH4, rigol3 CH4
    starts, ends = [], []
    for Mx, col in anchors:
        s, e = detect_activity(Mx[:, 0], Mx[:, col])
        if s is not None:
            starts.append(s)
            ends.append(e)
    if starts:
        tPulse, tEnd = float(np.median(starts)), float(max(ends))
        print(f"pulse detected: tPulse {tPulse*1e6:.3f} us, tEnd {tEnd*1e6:.3f} us")
    else:
        tPulse = tEnd = None
        print("no pulse detected, keeping the full record")

    arrays = {}
    crop = {}
    for k, Mx in enumerate(M, start=1):
        t = Mx[:, 0]
        if a.full or tPulse is None:
            keep = np.ones(len(t), bool)
        else:
            keep = (t >= tPulse - a.pre * 1e-6) & (t <= tEnd + a.post * 1e-6)
        arrays[f"r{k}_t"] = t[keep].astype(np.float64)
        arrays[f"r{k}_v"] = Mx[keep, 1:5].astype(np.float32)
        crop[f"rigol{k}"] = {"n_total": int(len(t)), "n_kept": int(keep.sum()),
                             "dt_s": float(np.median(np.diff(t[:1000]))),
                             "t_first_s": float(t[keep][0]), "t_last_s": float(t[keep][-1])}

    meta = {
        "shot": a.shot, "files": [os.path.abspath(f) for f in files],
        "tPulse_s": tPulse, "tEnd_s": tEnd,
        "crop_pre_us": None if a.full else a.pre,
        "crop_post_us": None if a.full else a.post,
        "crop": crop, "channel_map": CHANNEL_MAP, "constants": CONSTANTS,
        "shot_log_row": log_row,
    }
    arrays["meta"] = np.array(json.dumps(meta))

    os.makedirs(a.out, exist_ok=True)
    out = os.path.join(a.out, f"{name}_raw.npz")
    np.savez_compressed(out, **arrays)
    print(f"saved {out}  ({os.path.getsize(out)/1e6:.1f} MB)")
    for k, c in crop.items():
        print(f"  {k}: kept {c['n_kept']} of {c['n_total']} samples, dt {c['dt_s']*1e9:.3f} ns")


if __name__ == "__main__":
    main()