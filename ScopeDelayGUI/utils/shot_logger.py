# utils/shot_logger.py
"""
Per-shot snapshot logging, layered on top of the existing DataLogger event log.

A shot writes one row to two files with the identical schema:

    <session dir>/shot_log_<session ts>.csv   this launch's shot(s)
    logs/shot_log_master.csv                  every shot, every session, ever

The master file is the one to open months later: each row carries the session
directory and the experiment log filename, so any shot can be traced back to
its full event history and its waveform files.

SHOT NUMBER
    Global and monotonic across GUI launches (a new GUI is started for every
    shot), stored in logs/shot_counter.json. It is claimed - incremented,
    written with flush + os.fsync, atomically via a temp file and os.replace -
    immediately after the trigger command returns. A number is never reused,
    even if the row that follows fails to write.

    A missing or corrupt counter is rebuilt by scanning the master CSV (and
    any per-session shot logs) for the highest shot number.

    logs/shot_counter.lock keeps two accidentally-opened GUIs from claiming
    the same number. The lock records the owning pid: a lock held by a live
    process is never stolen, while one left behind by a crashed GUI (its pid
    is gone) is taken over on startup. A second live instance still runs and
    still fires, but its shot row is written with a blank shot number and a
    note rather than claiming a number that another GUI owns.
"""

import csv
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from utils.shot_snapshot import rigol_setting_columns

COUNTER_FILENAME = "shot_counter.json"
LOCK_FILENAME = "shot_counter.lock"
MASTER_FILENAME = "shot_log_master.csv"


def _pid_alive(pid):
    """True if a process with this pid is still running.

    os.kill(pid, 0) is NOT safe on Windows: anything other than
    CTRL_C_EVENT/CTRL_BREAK_EVENT calls TerminateProcess, which would kill the
    other GUI. psutil is used when available, otherwise OpenProcess on
    Windows and signal 0 on POSIX.
    """
    if pid is None or pid <= 0:
        return False
    try:
        import psutil
        return psutil.pid_exists(pid)
    except ImportError:
        pass
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return code.value == STILL_ACTIVE
            return True     # exists but we cannot read its exit code
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True         # exists, owned by another user


def _pid_from_lock(path):
    try:
        for token in path.read_text(errors="ignore").split():
            if token.startswith("pid="):
                return int(token.split("=", 1)[1])
    except (OSError, ValueError):
        pass
    return None


def _wj_columns(unit):
    return [
        f"{unit}_program_kv",
        f"{unit}_measured_kv",
        f"{unit}_current_ma",
        f"{unit}_hv_on",
        f"{unit}_fault",
        f"{unit}_connected",
        f"{unit}_age_ms",
        # Last readback taken while HV was still on. The master sequence turns
        # HV off before the trigger (the WJs charge the Marx), so the measured
        # values at t0 are post-dump; these are the charge values.
        f"{unit}_charge_kv",
        f"{unit}_charge_ma",
        f"{unit}_charge_age_ms",
    ]


def _bnc_channel_columns():
    cols = []
    for ch in ("A", "B", "C", "D"):
        cols += [
            f"bnc575_{ch}_delay_us",
            f"bnc575_{ch}_width_us",
            f"bnc575_{ch}_enabled",
            f"bnc575_{ch}_polarity",
        ]
    return cols


def _dg535_laser_columns():
    cols = []
    for ch in ("A", "B", "C", "D"):
        cols += [f"dg535_laser_{ch}_delay_us", f"dg535_laser_{ch}_ref"]
    return cols


# Fixed schema. Append new columns at the end only; changing the header makes
# the master file roll over to a new file (see _prepare_master).
SHOT_COLUMNS = (
    [
        "shot_number",
        "session_shot_index",
        "datetime",
        "timestamp_sec",
        "session_dir",
        "experiment_log_file",
        # --- pressure (Opta, continuously polled; never queried at t0) ---
        "pressure_psi",
        "pressure_volts",
        "pressure_counts",
        "pressure_status",
        "pressure_sample_time",
        "pressure_age_ms",
    ]
    + _wj_columns("wj1")
    + _wj_columns("wj2")
    + [
        # --- BNC575: the unit the PC actually fires ---
        "bnc575_trigger_mode",
        "bnc575_system_mode",
        "bnc575_period_s",
        "bnc575_armed",
    ]
    + _bnc_channel_columns()
    + ["bnc575_config_source"]
    # --- laser DG535 (A/B = laser 1 lamp/Q-switch, C/D = laser 2) ---
    + _dg535_laser_columns()
    + [
        "dg535_laser_trigger_mode",
        "dg535_laser_config_source",
        "pulse_spacing_ns",
        # --- lasers ---
        "laser1_armed",
        "laser1_interlock_ok",
        "laser1_fault",
        "laser1_state",
        "laser1_mode",
        "laser2_armed",
        "laser2_interlock_ok",
        "laser2_fault",
        "laser2_state",
        "laser2_mode",
        # --- relays (commanded state; the driver has no hardware readback) ---
        # The two relays the GUI drives and the three-state mode they were
        # last commanded to (GROUND / FLOAT / CHARGE, else UNKNOWN).
        "charge_relay",
        "discharge_relay",
        "relay_mode",
        "relay_state_source",
        # --- interlocks ---
        "master_interlock_pass",
        "failed_interlocks",
        "interlock_manual_overrides",
        # --- scopes (filenames stay rigol<N>_<session ts>.csv so the existing
        #     post-test analysis keeps working; they are named here instead) ---
        # rigol<N>_file is the filename this shot EXPECTS. The row is frozen
        # at t0, before any capture or export, so whether the capture was
        # good and whether the file was written are not columns: the
        # SCOPE_CAPTURE and SCOPE_EXPORT events hold that, keyed by shot
        # number, and the session report reads them.
        "rigol1_armed",
        "rigol1_file",
        "rigol2_armed",
        "rigol2_file",
        "rigol3_armed",
        "rigol3_file",
    ]
    # --- Rigol settings read back at arm time (query-only, per channel) ---
    + rigol_setting_columns(1)
    + rigol_setting_columns(2)
    + rigol_setting_columns(3)
    + [
        "gui_version",
        "notes",
    ]
)


def gui_version(repo_dir=None):
    """Short git commit of the running code, or 'unversioned' outside git.

    Each shot runs a fresh GUI and the code may change between shots, so the
    row records which code fired it.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(repo_dir) if repo_dir else None,
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            dirty = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(repo_dir) if repo_dir else None,
                capture_output=True, text=True, timeout=5,
            )
            suffix = "+dirty" if dirty.returncode == 0 and dirty.stdout.strip() else ""
            return out.stdout.strip() + suffix
    except Exception:
        pass
    return "unversioned"


class ShotCounter:
    """The global shot number, shared by every GUI launch on this machine."""

    def __init__(self, logs_root, log_func=None):
        self.logs_root = Path(logs_root)
        self.counter_file = self.logs_root / COUNTER_FILENAME
        self.lock_file = self.logs_root / LOCK_FILENAME
        self.master_file = self.logs_root / MASTER_FILENAME
        self._log = log_func or (lambda msg: None)
        self._lock_fd = None
        self.locked = False
        self.lock_message = ""

    # ------------------------------------------------------------ locking

    def acquire_lock(self):
        """True if this process owns the counter. False means another GUI does."""
        self.logs_root.mkdir(parents=True, exist_ok=True)
        try:
            self._lock_fd = os.open(self.lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            # The lock records the owning pid. If that process is gone the
            # lock is a crash leftover and is taken over; a lock held by a
            # live process is never stolen.
            holder_pid = _pid_from_lock(self.lock_file)
            if _pid_alive(holder_pid):
                self.lock_message = (
                    f"another GUI instance (pid {holder_pid}) holds the shot counter")
                return False
            self._log(f"[ShotCounter] Taking over a lock left by dead pid {holder_pid}")
            try:
                self.lock_file.unlink()
                self._lock_fd = os.open(self.lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except OSError as e:
                self.lock_message = f"could not take over the abandoned lock: {e}"
                return False
        except OSError as e:
            self.lock_message = f"could not create lock file: {e}"
            return False

        os.write(self._lock_fd, f"pid={os.getpid()} started={datetime.now().isoformat()}\n".encode())
        os.fsync(self._lock_fd)
        self.locked = True
        return True

    def release(self):
        if self._lock_fd is not None:
            try:
                os.close(self._lock_fd)
            except OSError:
                pass
            self._lock_fd = None
        if self.locked:
            try:
                self.lock_file.unlink()
            except OSError:
                pass
            self.locked = False

    # ------------------------------------------------------------ counter

    def peek_next(self):
        """The number the next shot will get. Does not consume it."""
        return self._read_last() + 1

    def claim(self):
        """Consume and return the next shot number, persisted immediately.

        Called right after the trigger command returns. The number is spent
        even if the row that follows fails to write; numbers are never reused.
        """
        nxt = self._read_last() + 1
        self._write_last(nxt)
        return nxt

    def _read_last(self):
        try:
            with open(self.counter_file, "r") as f:
                data = json.load(f)
            last = int(data["last_shot"])
            if last < 0:
                raise ValueError(f"negative shot number {last}")
            return last
        except FileNotFoundError:
            recovered = self._recover_from_logs()
            if recovered:
                self._log(f"[ShotCounter] No counter file; recovered last shot {recovered} from the logs")
            return recovered
        except Exception as e:
            recovered = self._recover_from_logs()
            self._log(f"[ShotCounter] Counter file unusable ({e}); recovered last shot {recovered} from the logs")
            return recovered

    def _recover_from_logs(self):
        """Highest shot number in the master CSV, else in any session shot log."""
        highest = 0
        for path in self._candidate_logs():
            try:
                with open(path, "r", newline="") as f:
                    for row in csv.DictReader(f):
                        try:
                            highest = max(highest, int(row.get("shot_number", 0) or 0))
                        except (TypeError, ValueError):
                            continue
            except OSError:
                continue
        return highest

    def _candidate_logs(self):
        if self.master_file.exists():
            yield self.master_file
        # Masters retired by a schema change. The current master starts empty
        # after a rollover, so without these every shot fired before the
        # schema changed is invisible to recovery and its number would be
        # handed out a second time.
        yield from sorted(self.logs_root.glob("shot_log_master_schema_v*.csv"))
        # Per-session shot logs, in case the master was lost as well.
        yield from sorted(self.logs_root.glob("*/*/shot_log_*.csv"))

    def _write_last(self, value):
        """Atomic: temp file in the same folder, fsync, then os.replace."""
        self.logs_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "last_shot": int(value),
            "updated": datetime.now().isoformat(timespec="seconds"),
            "pid": os.getpid(),
        }
        tmp = self.counter_file.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(payload, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.counter_file)


class ShotLogger:
    """Writes the per-session and master shot rows."""

    def __init__(self, session_dir, session_timestamp, logs_root,
                 experiment_log_file, log_func=None, repo_dir=None):
        self.session_dir = Path(session_dir)
        self.logs_root = Path(logs_root)
        self.experiment_log_file = experiment_log_file
        self._log = log_func or (lambda msg: None)
        self.session_file = self.session_dir / f"shot_log_{session_timestamp}.csv"
        self.master_file = self.logs_root / MASTER_FILENAME
        self.gui_version = gui_version(repo_dir)
        self.session_shot_index = 0

        self.counter = ShotCounter(self.logs_root, log_func=log_func)
        self.counter_available = self.counter.acquire_lock()

        self._prepare_session()
        self._prepare_master()

    # ------------------------------------------------------------ files

    def _prepare_session(self):
        try:
            self.session_dir.mkdir(parents=True, exist_ok=True)
            if not self.session_file.exists():
                self._write_header(self.session_file)
        except OSError as e:
            self._log(f"[ShotLog ERROR] could not create {self.session_file}: {e}")

    def _prepare_master(self):
        """Create the master file, or roll it over if its header differs.

        An old master with a different schema is never appended to with
        mismatched columns; it is renamed to shot_log_master_schema_vN.csv.
        """
        try:
            self.logs_root.mkdir(parents=True, exist_ok=True)
            if not self.master_file.exists():
                self._write_header(self.master_file)
                return
            with open(self.master_file, "r", newline="") as f:
                existing = next(csv.reader(f), [])
            if existing == SHOT_COLUMNS:
                return
            n = 1
            while (self.logs_root / f"shot_log_master_schema_v{n}.csv").exists():
                n += 1
            retired = self.logs_root / f"shot_log_master_schema_v{n}.csv"
            os.replace(self.master_file, retired)
            self._write_header(self.master_file)
            self._log(f"[ShotLog] Master schema changed: previous file kept as {retired.name}")
        except OSError as e:
            self._log(f"[ShotLog ERROR] could not prepare {self.master_file}: {e}")

    @staticmethod
    def _write_header(path):
        with open(path, "w", newline="") as f:
            csv.writer(f).writerow(SHOT_COLUMNS)
            f.flush()
            os.fsync(f.fileno())

    # ------------------------------------------------------------ shots

    def peek_next_shot_number(self):
        return self.counter.peek_next()

    def claim_shot_number(self):
        """Consume the next global shot number (call right after the trigger)."""
        self.session_shot_index += 1
        return self.counter.claim()

    def next_session_index(self):
        """Advance only the per-session index.

        Used when the global counter is unavailable: the shot still happened
        and still gets a row, just without a global number.
        """
        self.session_shot_index += 1
        return self.session_shot_index

    def write_row(self, row):
        """Append one shot row to both files. Never raises.

        Returns True only if both writes succeeded.
        """
        ordered = {col: row.get(col, "") for col in SHOT_COLUMNS}
        ok = True
        for path in (self.session_file, self.master_file):
            try:
                with open(path, "a", newline="") as f:
                    csv.DictWriter(f, fieldnames=SHOT_COLUMNS).writerow(ordered)
                    f.flush()
                    os.fsync(f.fileno())
            except Exception as e:
                ok = False
                self._log(f"[ShotLog ERROR] could not append to {path}: {e}")
        return ok

    def close(self):
        self.counter.release()
