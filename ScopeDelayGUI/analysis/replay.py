"""Offline replay of recorded shots, for working on the post-shot analysis.

No instruments, no Qt. The replay GUI (gui/replay_window.py) is built on this.

    index_shots(root)          every shot under a logs folder, the way the
                               pipeline finds them (process_shots.session_shots)
    find_shot(index, 46)       one shot by its global shot number
    scope_settings(meta, k)    rigol<k>'s arm-time settings, rebuilt from the
                               shot row into the dict the live GUI keeps
    run_shot(ref, ...)         reload the analysis code, then run the same
                               process_one the production CLI runs, with every
                               output written to a sandbox folder

The sandbox is the point: a replay never writes into the session folder or
<logs>/processed_shots, so the production .mat files, PNGs and summary stay
as the lab GUI left them and can be compared against.
"""

from __future__ import annotations

import contextlib
import csv
import importlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import pipeline as P
from . import process_shots as PS

SANDBOX_DIRNAME = "replay_output"
SANDBOX_BASE = Path(__file__).resolve().parent.parent / SANDBOX_DIRNAME

# Summary columns worth comparing between the stored result and a replay.
COMPARE_COLS = [
    "status", "spacing_cmd_ns", "spacing_qsw_ns", "spacing_rvm_ns",
    "LTGS1_Ddot_kV", "LTGS2_Ddot_kV", "LTGS1_Bdot_kV", "LTGS2_Bdot_kV",
    "C225_Ddot_kV", "C315_Bdot_kV", "RVM1_kV", "RVM2_kV",
    "t_Qsw1_us", "t_Qsw2_us", "rvm_gain_1", "rvm_gain_2", "G_consistency",
    "error", "pipeline_version",
]


# ===================== finding shots =====================
@dataclass
class ShotRef:
    """One shot: where it lives and the pipeline's own shot dict for it."""
    sdir: Path
    stamp: str
    shot: dict                       # as returned by PS.session_shots
    key: str = ""
    name: str = ""

    @property
    def number(self):
        n = self.shot["shot_number"]
        return int(n) if np.isfinite(n) else None

    @property
    def meta(self):
        return self.shot["meta"]

    @property
    def files(self):
        return self.shot["files"]

    def label(self):
        dt = (self.meta.get("datetime") or "")[:19]
        return f"{self.name}   {dt}".rstrip()


def _default_roots():
    here = Path(__file__).resolve().parent.parent       # ScopeDelayGUI
    return [Path.cwd() / "logs", here / "logs", here.parent / "logs"]


def guess_logs_root():
    """The logs folder that holds the most sessions, or None."""
    best, best_n = None, -1
    for r in _default_roots():
        if r.is_dir():
            n = sum(1 for _ in r.glob("*/experiment_log_*")) + sum(
                1 for _ in r.glob("experiment_log_*"))
            if n > best_n:
                best, best_n = r.resolve(), n
    return best


def index_shots(root):
    """Every shot under root, numbered shots first in shot order, then the
    unnumbered scope-file sets by stamp. Same discovery as the CLI."""
    root = Path(root)
    out = []
    for sdir in PS.find_sessions(root):
        stamp = sdir.name.replace("experiment_log_", "")
        try:
            shots = PS.session_shots(sdir, stamp)
        except (OSError, csv.Error, UnicodeDecodeError):
            continue
        for sh in shots:
            key, name = PS.shot_key(sh, stamp)
            out.append(ShotRef(sdir=sdir, stamp=stamp, shot=sh, key=key, name=name))
    out.sort(key=lambda r: (0, r.number, "") if r.number is not None else (1, 0, r.key))
    return out


def find_shot(index, number):
    """The ShotRef with this global shot number. When a number appears more
    than once (a counter rebuilt by hand), the last one is returned."""
    hits = [r for r in index if r.number == int(number)]
    return hits[-1] if hits else None


# ===================== stored (production) results =====================
def stored_results(root):
    """key -> summary row the production pipeline last wrote, from
    <root>/processed_shots/summary_cache.json. {} when there is none."""
    p = Path(root) / "processed_shots" / "summary_cache.json"
    try:
        cache = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v.get("row", {}) for k, v in cache.items()}


# ===================== scope settings from the shot row =====================
def scope_settings(meta, k):
    """rigol<k>'s arm-time settings rebuilt from the shot row, in the shape
    the live GUI keeps in system_state["rigol<k>"]["settings"] (and hands to
    ScopeScreen): {"scope": {...}, "channels": {1: {...}, ...}}.

    {} when the row has no readback for that scope, which is what the live
    GUI has in the same case."""
    from utils.shot_snapshot import RIGOL_CHANNEL_SETTING_KEYS, RIGOL_SCOPE_SETTING_KEYS
    if (meta.get(f"rigol{k}_settings_source") or "").strip().lower() != "readback":
        return {}
    scope = {key: meta.get(f"rigol{k}_{key}", "") for key in RIGOL_SCOPE_SETTING_KEYS}
    chans = {ch: {key: meta.get(f"rigol{k}_ch{ch}_{key}", "")
                  for key in RIGOL_CHANNEL_SETTING_KEYS} for ch in (1, 2, 3, 4)}
    return {"scope": scope, "channels": chans}


# ===================== waveform cache =====================
class WaveformCache:
    """read_rigol with memory. A 1,000,000-point record takes seconds to
    parse, and a rerun after a one-line code change should not pay that
    again. Keyed on path, size and mtime, so a rewritten file is re-read."""

    def __init__(self, max_files=6):
        self.max_files = max_files
        self._d = {}

    @staticmethod
    def _key(path):
        st = Path(path).stat()
        return (str(Path(path).resolve()), st.st_size, st.st_mtime_ns)

    def read(self, path, reader=None):
        k = self._key(path)
        if k in self._d:
            M = self._d.pop(k)
            self._d[k] = M                   # most recent last
            return M
        M = (reader or P.read_rigol)(path)
        self._d[k] = M
        while len(self._d) > self.max_files:
            self._d.pop(next(iter(self._d)))
        return M

    def clear(self):
        self._d.clear()


# ===================== running =====================
def reload_analysis():
    """Re-import the analysis code so edits to pipeline.py, plots.py or
    process_shots.py take effect without restarting the GUI. Returns the
    PIPELINE_VERSION now in force. A syntax error propagates to the caller
    and leaves the previous code in place. reload() re-runs each module in
    its existing module object, so the P and PS names here stay valid."""
    from . import plots as PL
    importlib.reload(P)
    importlib.reload(PL)
    importlib.reload(PS)
    return PS.PIPELINE_VERSION


@contextlib.contextmanager
def _patched(cache, cal_overrides):
    """For one run: read_rigol through the cache, and CAL values replaced.
    CAL is changed in place because process_waveforms binds it as a default
    argument; both are put back afterwards whatever happens."""
    real_read = P.read_rigol
    saved = dict(P.CAL)
    try:
        if cache is not None:
            P.read_rigol = lambda path: cache.read(path, real_read)
        for k, v in (cal_overrides or {}).items():
            if k in P.CAL:
                P.CAL[k] = float(v)
        yield
    finally:
        P.read_rigol = real_read
        P.CAL.clear()
        P.CAL.update(saved)


def sandbox_dir(ref, base=None):
    base = Path(base) if base else SANDBOX_BASE
    d = base / ref.key
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class RunResult:
    S: dict
    row: dict
    seconds: float
    out_dir: Path
    scopes: dict = field(default_factory=dict)   # k -> array, the raw records


def run_shot(ref, cache=None, cal_overrides=None, plots=True, out_base=None):
    """process_one on a recorded shot, exactly as the CLI runs it, with the
    .mat and PNGs written to the sandbox instead of the session folder."""
    out = sandbox_dir(ref, out_base)
    t0 = time.time()
    with _patched(cache, cal_overrides):
        # PNGs go to process_one's sdir argument; the waveform paths in the
        # shot dict are absolute, so they still come from the real session.
        S = PS.process_one(ref.shot, out, ref.stamp, out, plots=plots)
        scopes = {}
        for k, f in enumerate(ref.files, start=1):
            if Path(f).exists():
                try:
                    scopes[k] = P.read_rigol(f)
                except Exception:  # noqa: BLE001
                    pass
    row = {k: PS._fmt(v) for k, v in PS.summary_row(S).items()}
    return RunResult(S=S, row=row, seconds=time.time() - t0, out_dir=out, scopes=scopes)


def load_scopes(ref, cache=None):
    """The raw records of one shot, k -> (N, 5) array. Missing or unreadable
    files are left out and reported in the second return value."""
    scopes, problems = {}, []
    for k, f in enumerate(ref.files, start=1):
        f = Path(f)
        if not f.exists():
            problems.append(f"rigol{k}: file missing ({f.name})")
            continue
        try:
            scopes[k] = cache.read(f) if cache is not None else P.read_rigol(f)
        except Exception as e:  # noqa: BLE001
            problems.append(f"rigol{k}: could not read {f.name}: {e}")
    return scopes, problems


# ===================== comparing =====================
def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return np.nan


def compare_rows(a, b, cols=COMPARE_COLS):
    """[(col, a, b, delta)] for two summary rows; delta is b - a for numbers,
    '' otherwise. Either row may be empty."""
    out = []
    for c in cols:
        va, vb = (a or {}).get(c, ""), (b or {}).get(c, "")
        fa, fb = _f(va), _f(vb)
        d = PS._fmt(fb - fa) if np.isfinite(fa) and np.isfinite(fb) else ""
        out.append((c, va, vb, d))
    return out


def parse_shot_range(text):
    """'40-46, 50, 52-53' -> [40, 41, ..., 46, 50, 52, 53]."""
    nums = []
    for part in text.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = (int(x) for x in part.split("-", 1))
            nums.extend(range(min(a, b), max(a, b) + 1))
        else:
            nums.append(int(part))
    return sorted(set(nums))


# ===================== multi-shot views (the ltgs_gui3 side) =====================
# One entry per trace a figure can show: key, label, t field, y field, index
# into a two-element field (None for single arrays), unit, default colour
# name, line style. Colours and styles follow plots.py / ltgs_gui3.
TRACES = [
    ("D1", "LTGS1-232 D-dot", "Dt", "Dv", 0, "kV", "blue", "solid"),
    ("D2", "LTGS2-232 D-dot", "Dt", "Dv", 1, "kV", "red", "solid"),
    ("B1", "LTGS1-007 B-dot Z*I", "Bt", "Bv", 0, "kV", "green", "dash"),
    ("B2", "LTGS2-007 B-dot Z*I", "Bt", "Bv", 1, "kV", "teal", "dash"),
    ("C225", "C225 D-dot", "C225_t", "C225", None, "kV", "magenta", "dashdot"),
    ("C315", "C315 B-dot Z*I", "C315_t", "C315", None, "kV", "brown", "dot"),
    ("R1", "RVM 1", "Rt", "Rv", 0, "kV", "dark gray", "solid"),
    ("R2", "RVM 2", "Rt", "Rv", 1, "kV", "light gray", "dash"),
    ("Q1", "Laser1 Q-switch", "Qt", "Qv", 0, "V", "orange", "solid"),
    ("Q2", "Laser2 Q-switch", "Qt", "Qv", 1, "V", "purple", "solid"),
]
TRACE_KEYS = [t[0] for t in TRACES]
TRACE = {t[0]: t for t in TRACES}

COLORS = {
    "blue": "#0000ff", "red": "#ff0000", "green": "#009900", "teal": "#00b3b3",
    "magenta": "#ff00ff", "brown": "#8c4512", "dark gray": "#666666",
    "light gray": "#b3b3b3", "orange": "#d9541a", "purple": "#7d2e8f",
    "black": "#000000", "cyan": "#00bfff", "gold": "#c9a200", "navy": "#000080",
}


def trace_xy(S, key):
    """(t_us, y) of one trace of a result, or None when the shot has none."""
    _, _, tf, yf, i, _, _, _ = TRACE[key]
    t, y = S.get(tf), S.get(yf)
    if t is None or y is None:
        return None
    if i is not None:
        try:
            t, y = t[i], y[i]
        except (IndexError, KeyError, TypeError):
            return None
    t, y = np.atleast_1d(np.asarray(t, float)), np.atleast_1d(np.asarray(y, float))
    if t.size < 2 or t.size != y.size:
        return None
    return t, y


def load_mat_result(path, trim_us=(-12.0, 12.0)):
    """A shot_NNNN.mat back into the dict process_one returned, with every
    trace cut to trim_us so dozens of shots fit in memory."""
    from scipy.io import loadmat
    S = loadmat(str(path), squeeze_me=True, simplify_cells=True)
    S = {k: v for k, v in S.items() if not k.startswith("__")}
    S.setdefault("name", PS.shot_key({"shot_number": _f(S.get("shot_number")),
                                      "tag": str(S.get("key", ""))[5:]},
                                     str(S.get("stamp", "")))[1])
    for key in TRACE_KEYS:
        _, _, tf, yf, i, _, _, _ = TRACE[key]
        xy = trace_xy(S, key)
        if xy is None:
            continue
        m = (xy[0] >= trim_us[0]) & (xy[0] <= trim_us[1])
        if i is None:
            S[tf], S[yf] = xy[0][m], xy[1][m]
        else:
            S[tf] = list(S[tf]) if isinstance(S[tf], (list, np.ndarray)) else [None, None]
            S[yf] = list(S[yf]) if isinstance(S[yf], (list, np.ndarray)) else [None, None]
            S[tf][i], S[yf][i] = xy[0][m], xy[1][m]
    return S


def is_healthy(row):
    """Fired, analysed without a warning, and both RVM gains within limits."""
    return bool(row.get("status") == "ok" and not row.get("error")
            and np.isfinite(_f(row.get("rvm_gain_1"))) and np.isfinite(_f(row.get("rvm_gain_2"))))


def spacing_of(row):
    v = _f(row.get("spacing_cmd_ns"))
    return int(round(v)) if np.isfinite(v) else None


def charge_kv(row):
    v = [_f(row.get("wj1_charge_kv")), _f(row.get("wj2_charge_kv"))]
    v = [x for x in v if np.isfinite(x)]
    return float(np.mean(v)) if v else np.nan


STAT_COLS = ["spacing_qsw_ns", "spacing_rvm_ns", "LTGS1_Ddot_kV", "LTGS2_Ddot_kV",
             "LTGS1_Bdot_kV", "LTGS2_Bdot_kV", "C225_Ddot_kV", "RVM1_kV", "RVM2_kV"]


def group_stats(rows, cols=STAT_COLS):
    """Per commanded spacing: n, and mean / std / min / max of each column.
    Spacing columns are reported as measured minus commanded."""
    groups = {}
    for r in rows:
        groups.setdefault(spacing_of(r), []).append(r)
    out = []
    for sp in sorted(groups, key=lambda s: (s is None, s or 0)):
        g = groups[sp]
        rec = {"spacing_cmd_ns": "" if sp is None else sp, "n": len(g),
               "n_ok": sum(1 for r in g if r.get("status") == "ok")}
        for c in cols:
            v = np.array([_f(r.get(c)) for r in g])
            if c.startswith("spacing_") and sp is not None:
                v = v - sp
            v = v[np.isfinite(v)]
            rec[c] = (v.mean(), v.std(ddof=1) if v.size > 1 else 0.0,
                      v.min(), v.max()) if v.size else None
        out.append(rec)
    return out
