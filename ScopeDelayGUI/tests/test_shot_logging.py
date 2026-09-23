"""
Tests for the per-shot logging system. No hardware, no high voltage.

Safety and hang rules for this file:
  * Every test runs in a temporary working directory, so the real
    logs/shot_counter.json and logs/shot_log_master.csv are never touched.
  * The GUI tests patch out everything that could open a port or a socket:
    the Opta pressure worker, the WJ reader threads and RigolScope. The
    DG535 is live on COM4 and is never opened - a FakeDG is injected instead.
  * Modal dialogs are stubbed. QMessageBox.critical/question/warning/
    information and error_popup all block forever offscreen, because no event
    loop is running to dismiss them.
  * faulthandler watchdogs abort with a stack trace instead of hanging.

Run from the ScopeDelayGUI folder:
    python -m unittest tests.test_shot_logging -v
"""

import csv
import faulthandler
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Global backstop: if the whole module wedges, print every thread's stack and
# exit rather than hanging a terminal.
faulthandler.dump_traceback_later(300, exit=True)

from PyQt6.QtWidgets import QApplication, QMessageBox

from utils.data_logger import DataLogger
from utils.shot_logger import SHOT_COLUMNS, ShotCounter, ShotLogger
from utils.shot_snapshot import build_shot_row, pulse_spacing_ns, resolve_absolute_delays
from utils.connect_memory import save_memory
from utils.system_state import SystemState, SOURCE_READBACK

# The operator's real saved port table, one level above ScopeDelayGUI. Tests
# assert byte-for-byte that they never write to it.
REAL_MEMORY_FILE = Path(__file__).resolve().parent.parent.parent / "connection_memory.json"

_app = QApplication.instance() or QApplication([])


# ----------------------------------------------------------------- fakes
class FakeBNC:
    """Only what on_bnc_fire touches."""

    def __init__(self):
        self.fired = 0

    def fire_internal(self):
        self.fired += 1
        return True


class FakeDG:
    """Laser DG535 stand-in. Records writes; fires nothing.

    Default delays match the real unit: A = T0 + 0, B = A + 180.5 us,
    C = T0 + 0, D = C + 180.7 us, so laser 2's Q-switch is 200 ns after
    laser 1's. Channel ids are the driver's (T0=1, A=2, B=3, C=5, D=6).

    honour_writes=False simulates an instrument that ignores a write, so the
    readback afterwards does not match what was sent.
    """

    def __init__(self, delays=None, honour_writes=True):
        self.delays = dict(delays or {2: (1, 0.0), 3: (2, 180.5e-6),
                                      5: (1, 0.0), 6: (5, 180.7e-6)})
        self.writes = []
        self.honour_writes = honour_writes
        self.calls = []

    def is_connected(self):
        return True

    def get_delay(self, channel):
        self.calls.append(("get_delay", int(channel)))
        return self.delays[int(channel)]

    def set_delay(self, channel, reference, delay_sec):
        self.calls.append(("set_delay", int(channel)))
        self.writes.append((int(channel), int(reference), float(delay_sec)))
        if self.honour_writes:
            self.delays[int(channel)] = (int(reference), float(delay_sec))

    def get_trigger_mode(self):
        self.calls.append(("get_trigger_mode", None))

        class _M:
            name = "EXTERNAL"
        return _M()

    # Anything that would retime or fire the unit is a test failure.
    def set_trigger_mode(self, *a, **k):
        raise AssertionError("the GUI must never send TM to the laser DG535")

    def set_single_shot(self, *a, **k):
        raise AssertionError("the GUI must never set single-shot mode")

    def fire(self, *a, **k):
        raise AssertionError("the GUI must never send SS to the laser DG535")

    def configure_pulse_A(self, *a, **k):
        raise AssertionError("the GUI must never rewrite A/B as a pulse")


class FakeScope:
    """Stands in for RigolScope so no VISA session is ever opened."""

    def __init__(self, resource_name=None):
        self.resource_name = resource_name
        self.calls = []

    def connect(self, *a, **k):
        raise RuntimeError("FakeScope never connects in tests")

    def disconnect(self):
        pass

    def stop(self):
        self.calls.append("stop")

    def single(self):
        self.calls.append("single")


def tmc_block(payload, newline=True, declared=None):
    """Build a TMC block: #<n><length><payload>[\\n].

    declared overrides the length in the header, to simulate a transfer that
    delivers fewer bytes than it promised.
    """
    digits = str(len(payload) if declared is None else declared)
    head = b"#" + str(len(digits)).encode() + digits.encode()
    return head + payload + (b"\n" if newline else b"")


class FakeVisaInstrument:
    """Stands in for a pyvisa session. No VISA library, no socket.

    read_bytes(n) mimics pyvisa: it returns exactly n bytes, gathering across
    however many pieces the transport delivered, and raises when the stream
    runs dry - which is what a timeout looks like to the driver.

    lenient=True instead returns whatever is available, to prove the driver's
    own length check catches a short transfer rather than passing truncated
    samples up as a waveform.
    """

    def __init__(self, pieces, read_termination="\n", timeout=30000,
                 lenient=False):
        self._pieces = [bytes(p) for p in pieces]
        self._buf = b""
        self.read_termination = read_termination
        self.timeout = timeout
        self.lenient = lenient
        self.written = []
        self.reads = []            # byte counts requested, in order
        self.timeouts_seen = []    # timeout in force at each read

    def write(self, cmd):
        self.written.append(cmd)

    def read_bytes(self, n):
        self.reads.append(n)
        self.timeouts_seen.append(self.timeout)
        while len(self._buf) < n and self._pieces:
            self._buf += self._pieces.pop(0)
        if len(self._buf) < n:
            if not self.lenient:
                raise TimeoutError(f"wanted {n} bytes, stream had {len(self._buf)}")
            out, self._buf = self._buf, b""
            return out
        out, self._buf = self._buf[:n], self._buf[n:]
        return out


class TempLogRoot:
    """Run inside a throwaway working directory so logs/ is temporary."""

    def __enter__(self):
        self._prev = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)
        return Path(self._tmp.name)

    def __exit__(self, *exc):
        os.chdir(self._prev)
        try:
            self._tmp.cleanup()
        except (PermissionError, OSError):
            pass       # Windows may still hold a handle; the temp dir is disposable
        return False


def read_rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def event_types(experiment_log):
    return [r["event_type"] for r in read_rows(experiment_log)]


# ----------------------------------------------------------------- units
class TestSystemState(unittest.TestCase):
    def test_snapshot_is_frozen(self):
        state = SystemState()
        state.update("pressure", {"psi": 42.0}, source=SOURCE_READBACK)
        snap = state.snapshot()
        state.update("pressure", {"psi": 99.0})
        self.assertEqual(snap["pressure"]["psi"], 42.0,
                         "snapshot must not see later updates")

    def test_age_and_source(self):
        state = SystemState()
        state.update("wj1", {"measured_kv": 1.0}, source=SOURCE_READBACK)
        section = state.get("wj1")
        self.assertIsNotNone(SystemState.age_ms(section))
        self.assertLess(SystemState.age_ms(section), 1000)
        self.assertEqual(SystemState.source_of(section), SOURCE_READBACK)
        self.assertIsNone(SystemState.age_ms({}))


class TestDelayResolution(unittest.TestCase):
    CHANNELS = {
        "A": {"ref": "T0", "delay_s": 0.0},
        "B": {"ref": "A", "delay_s": 180.5e-6},
        "C": {"ref": "T0", "delay_s": 0.0},
        "D": {"ref": "C", "delay_s": 180.7e-6},
    }

    def test_chained_references_resolve_to_t0(self):
        absolute = resolve_absolute_delays(self.CHANNELS)
        self.assertAlmostEqual(absolute["B"], 180.5e-6)
        self.assertAlmostEqual(absolute["D"], 180.7e-6)

    def test_pulse_spacing_matches_instrument(self):
        self.assertAlmostEqual(pulse_spacing_ns(self.CHANNELS), 200.0, places=3)

    def test_pulse_spacing_with_d_referenced_to_b(self):
        channels = dict(self.CHANNELS)
        channels["D"] = {"ref": "B", "delay_s": 500e-9}
        self.assertAlmostEqual(pulse_spacing_ns(channels), 500.0, places=3)

    def test_circular_reference_gives_blank(self):
        channels = {"B": {"ref": "D", "delay_s": 1e-6},
                    "D": {"ref": "B", "delay_s": 1e-6}}
        self.assertIsNone(pulse_spacing_ns(channels))

    def test_missing_data_does_not_crash(self):
        row = build_shot_row({}, shot_number=1, session_shot_index=1,
                             datetime_str="now", timestamp_sec=0.0,
                             session_dir="d", experiment_log_file="e.csv",
                             gui_version="test")
        self.assertEqual(row["shot_number"], 1)
        self.assertEqual(row["pulse_spacing_ns"], "")
        self.assertIn("no pressure sample", row["notes"])


class TestShotCounter(unittest.TestCase):
    def test_increments_and_persists(self):
        with TempLogRoot() as tmp:
            logs = tmp / "logs"
            c1 = ShotCounter(logs)
            self.assertTrue(c1.acquire_lock())
            self.assertEqual(c1.peek_next(), 1)
            self.assertEqual(c1.claim(), 1)
            self.assertEqual(c1.claim(), 2)
            c1.release()

            # A new process (new GUI) continues from the file.
            c2 = ShotCounter(logs)
            self.assertTrue(c2.acquire_lock())
            self.assertEqual(c2.peek_next(), 3)
            c2.release()

    def test_second_instance_cannot_claim(self):
        with TempLogRoot() as tmp:
            logs = tmp / "logs"
            first = ShotCounter(logs)
            self.assertTrue(first.acquire_lock())
            second = ShotCounter(logs)
            self.assertFalse(second.acquire_lock(),
                             "a second GUI must not own the counter")
            self.assertIn("another GUI", second.lock_message)
            first.release()
            self.assertTrue(ShotCounter(logs).acquire_lock())

    def test_dead_pid_lock_is_taken_over(self):
        with TempLogRoot() as tmp:
            logs = tmp / "logs"
            logs.mkdir(parents=True)
            # A lock left behind by a crashed GUI: the pid no longer exists.
            dead_pid = 999_999_999
            (logs / "shot_counter.lock").write_text(f"pid={dead_pid} started=whenever\n")
            counter = ShotCounter(logs)
            self.assertTrue(counter.acquire_lock(),
                            "an abandoned lock must not block firing forever")
            self.assertEqual(counter.claim(), 1)
            counter.release()

    def test_live_pid_lock_is_not_stolen(self):
        with TempLogRoot() as tmp:
            logs = tmp / "logs"
            logs.mkdir(parents=True)
            # This test process is alive, so its lock must be respected.
            (logs / "shot_counter.lock").write_text(f"pid={os.getpid()} started=now\n")
            counter = ShotCounter(logs)
            self.assertFalse(counter.acquire_lock())
            self.assertIn(str(os.getpid()), counter.lock_message)

    def test_recovers_from_master_when_counter_missing(self):
        with TempLogRoot() as tmp:
            logs = tmp / "logs"
            logs.mkdir(parents=True)
            with open(logs / "shot_log_master.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=SHOT_COLUMNS)
                w.writeheader()
                for n in (40, 41, 42):
                    w.writerow({"shot_number": n})
            counter = ShotCounter(logs)
            self.assertEqual(counter.peek_next(), 43)

    def test_recovers_from_corrupt_counter(self):
        with TempLogRoot() as tmp:
            logs = tmp / "logs"
            logs.mkdir(parents=True)
            (logs / "shot_counter.json").write_text("{not json at all")
            with open(logs / "shot_log_master.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=SHOT_COLUMNS)
                w.writeheader()
                w.writerow({"shot_number": 7})
            counter = ShotCounter(logs)
            self.assertEqual(counter.peek_next(), 8)

    def test_counter_file_is_valid_json_after_claim(self):
        with TempLogRoot() as tmp:
            logs = tmp / "logs"
            counter = ShotCounter(logs)
            counter.acquire_lock()
            counter.claim()
            data = json.loads((logs / "shot_counter.json").read_text())
            self.assertEqual(data["last_shot"], 1)
            counter.release()


class TestShotLoggerFiles(unittest.TestCase):
    def _make(self, tmp, session="20260101_000000"):
        session_dir = tmp / "logs" / "2026.01.01" / f"experiment_log_{session}"
        session_dir.mkdir(parents=True, exist_ok=True)
        return ShotLogger(session_dir=session_dir, session_timestamp=session,
                          logs_root=tmp / "logs",
                          experiment_log_file=f"experiment_log_{session}.csv")

    def test_headers_created(self):
        with TempLogRoot() as tmp:
            logger = self._make(tmp)
            with open(logger.session_file, newline="") as f:
                self.assertEqual(next(csv.reader(f)), SHOT_COLUMNS)
            with open(logger.master_file, newline="") as f:
                self.assertEqual(next(csv.reader(f)), SHOT_COLUMNS)
            logger.close()

    def test_schema_change_retires_old_master(self):
        with TempLogRoot() as tmp:
            logs = tmp / "logs"
            logs.mkdir(parents=True)
            with open(logs / "shot_log_master.csv", "w", newline="") as f:
                csv.writer(f).writerow(["shot_number", "old_column"])
            logger = self._make(tmp)
            self.assertTrue((logs / "shot_log_master_schema_v1.csv").exists(),
                            "the old master must be kept, not corrupted")
            with open(logger.master_file, newline="") as f:
                self.assertEqual(next(csv.reader(f)), SHOT_COLUMNS)
            logger.close()

    def test_consecutive_numbers_across_sessions(self):
        with TempLogRoot() as tmp:
            first = self._make(tmp, "20260101_000000")
            n1 = first.claim_shot_number()
            first.write_row({"shot_number": n1, "session_shot_index": 1})
            first.close()

            second = self._make(tmp, "20260101_010000")
            n2 = second.claim_shot_number()
            second.write_row({"shot_number": n2, "session_shot_index": 1})
            second.close()

            self.assertEqual((n1, n2), (1, 2))
            master = read_rows(tmp / "logs" / "shot_log_master.csv")
            self.assertEqual([r["shot_number"] for r in master], ["1", "2"])
            self.assertEqual(len(read_rows(second.session_file)), 1,
                             "each session file holds only its own shots")

    def test_two_shots_in_one_session(self):
        with TempLogRoot() as tmp:
            logger = self._make(tmp)
            rows = []
            for _ in range(2):
                n = logger.claim_shot_number()
                rows.append((n, logger.session_shot_index))
                logger.write_row({"shot_number": n,
                                  "session_shot_index": logger.session_shot_index})
            logger.close()
            self.assertEqual(rows, [(1, 1), (2, 2)])


# ----------------------------------------------------------------- GUI level
class TestGuiShotLogging(unittest.TestCase):
    """Drives the real main window with every instrument stubbed out."""

    def setUp(self):
        import gui.main_window as mw
        import utils.connect_memory as cm

        # Per-test watchdog: dump every thread's stack and exit rather than
        # hang if a modal dialog or a thread join ever blocks again.
        faulthandler.dump_traceback_later(60, exit=True)
        self.addCleanup(faulthandler.cancel_dump_traceback_later)

        self.root = TempLogRoot()
        self.tmp = self.root.__enter__()
        self.addCleanup(self.root.__exit__, None, None, None)

        # Nothing in these tests may open a port or a socket. The Opta worker
        # (Modbus TCP), the WJ reader threads (serial) and RigolScope (VISA)
        # are patched out before the window is built.
        for target in ("_start_pressure_worker", "start_wj_readers"):
            p = patch.object(mw.ScopeDelayMainWindow, target, lambda self: None)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(mw, "RigolScope", FakeScope)
        p.start()
        self.addCleanup(p.stop)

        # connection_memory.json holds the operator's saved ports. MEM_FILE is
        # a relative path, so the temp cwd already hides the real file, but pin
        # it explicitly: every connect handler ends in save_memory(), and a
        # test that reaches one must not rewrite the real table.
        p = patch.object(cm, "MEM_FILE", str(self.tmp / "connection_memory.json"))
        p.start()
        self.addCleanup(p.stop)

        # load_memory() resolves ports by USB identity, which calls
        # find_supplies() and opens the live WJ supplies. Hand the window the
        # remembered defaults instead so startup opens nothing.
        p = patch.object(mw, "load_memory", lambda *a, **k: dict(cm.default_data))
        p.start()
        self.addCleanup(p.stop)

        # Modal dialogs block forever with no event loop running. Record them
        # instead, so tests can assert that the operator was warned.
        self.popups = []
        # Confirmation dialogs answer No unless a test opts in.
        self.question_answer = QMessageBox.StandardButton.No
        self._stub_dialogs()

        self.win = mw.ScopeDelayMainWindow(
            auto_connect={k: False for k in mw.ScopeDelayMainWindow.DEFAULT_AUTO_CONNECT})
        self.addCleanup(self._close_window)
        self.dl = self.win.data_logger
        # error_popup is the window's own wrapper around QMessageBox.critical.
        self.win.error_popup = lambda title, text: self.popups.append((title, text))

    def _stub_dialogs(self):
        def record(kind, default):
            def _stub(*args, **kwargs):
                # (parent, title, text, ...) for the static helpers
                title = args[1] if len(args) > 1 else kwargs.get("title", "")
                text = args[2] if len(args) > 2 else kwargs.get("text", "")
                self.popups.append((title, text))
                if kind == "question":
                    return self.question_answer
                return default
            return _stub

        for name, default in (
            ("critical", QMessageBox.StandardButton.Ok),
            ("warning", QMessageBox.StandardButton.Ok),
            ("information", QMessageBox.StandardButton.Ok),
            # No: never let a stubbed confirmation proceed with an action.
            ("question", None),      # answered from self.question_answer
        ):
            p = patch.object(QMessageBox, name, staticmethod(record(name, default)))
            p.start()
            self.addCleanup(p.stop)

        p = patch.object(QMessageBox, "exec",
                         lambda self_, *a, **k: QMessageBox.StandardButton.Ok)
        p.start()
        self.addCleanup(p.stop)

    def _close_window(self):
        try:
            self.win.close()
        except Exception:
            pass

    def _arm_fire_path(self):
        """Make on_bnc_fire reach the trigger without hardware."""
        self.win.bnc = FakeBNC()
        self.win.bnc_connected = True
        self.win.ensure_wj_hv_off = lambda *a, **k: True
        return self.win.bnc

    # -------------------------------------------------- existing behavior
    def test_session_folder_and_experiment_log_still_work(self):
        session_dir = Path(self.dl.get_session_dir())
        self.assertTrue(session_dir.is_dir())
        self.assertTrue(Path(self.dl.get_log_file_path()).exists())
        self.assertIn("SESSION_START", event_types(self.dl.get_log_file_path()))

    def test_scope_export_names_unchanged_for_post_test_analysis(self):
        # Post Test Analysis/parse_test_log.py matches rigol\d_\d{8}_\d{6}\.csv
        name = Path(self.dl.scope_export_path(1)).name
        self.assertRegex(name, r"^rigol\d_\d{8}_\d{6}\.csv$")

    def test_gui_log_file_is_written_and_flushed(self):
        self.win.log("[TEST] hello gui log")
        text = Path(self.dl.gui_log_file).read_text(encoding="utf-8")
        self.assertIn("[TEST] hello gui log", text,
                      "each on-screen line must be flushed immediately")

    # -------------------------------------------------- state caches
    def test_pressure_updates_state_with_age(self):
        self.win._opta_link_up = True
        self.win._on_pressure_data({
            "psi": 61.25, "volts": 4.1, "counts": 1234,
            "uptime_s": 10, "under_range": False, "over_range": False,
        })
        section = self.win.system_state.get("pressure")
        self.assertEqual(section["psi"], 61.25)
        self.assertEqual(section["status"], "OK")
        self.assertLess(SystemState.age_ms(section), 2000)

    def test_wj_hv_and_fault_are_not_hardcoded(self):
        self.win.on_wj_packet(0, {"type": "R", "kv": 61.0, "ma": 1.5,
                                  "hv_on": True, "fault": False})
        section = self.win.system_state.get("wj1")
        self.assertTrue(section["hv_on"])
        self.assertEqual(section["charge_kv"], 61.0)

        rows = [r for r in read_rows(self.dl.get_log_file_path())
                if r["event_type"] == "WJ_VOLTAGE"]
        self.assertTrue(rows, "streaming WJ rows must still be logged")
        self.assertEqual(rows[-1]["param3"], "1", "HV state must be the real one")

    def test_startup_readback_populates_dg535_cache(self):
        self.win.dg = FakeDG()
        self.win._dg_read_all_settings()
        section = self.win.system_state.get("dg535_laser")
        self.assertEqual(section["trigger_mode"], "EXTERNAL")
        self.assertAlmostEqual(section["channels"]["B"]["delay_s"], 180.5e-6)
        self.assertIn("DG535_READBACK", event_types(self.dl.get_log_file_path()))

    def test_relay_changes_are_logged(self):
        self.win._record_relay_state(1, True, ok=True)
        types = event_types(self.dl.get_log_file_path())
        self.assertIn("RELAY_COMMAND", types)
        self.assertIn("RELAY_STATE", types)
        states = self.win.system_state.get("relays")["states"]
        self.assertTrue(states["charge_positive"])

    def test_laser_changes_are_logged(self):
        self.win._on_laser_event("Laser1", "ARM",
                                 {"armed": True, "state": "ARMED", "mode": "EXT/EXT"})
        self.assertIn("LASER_ARM", event_types(self.dl.get_log_file_path()))
        self.assertTrue(self.win.system_state.get("laser1")["armed"])

    def test_interlock_changes_are_logged(self):
        self.win._mark_interlock(2, "unit test")
        self.assertIn("INTERLOCK_PASS", event_types(self.dl.get_log_file_path()))
        self.assertTrue(self.win.interlock_passed[2])

    # -------------------------------------------------- shots
    def test_simulated_shot_writes_one_row_to_each_file(self):
        bnc = self._arm_fire_path()
        self.win._opta_link_up = True
        self.win._on_pressure_data({"psi": 55.5, "volts": 3.9, "counts": 1000,
                                    "uptime_s": 5, "under_range": False,
                                    "over_range": False})
        self.win.on_wj_packet(0, {"type": "R", "kv": 61.0, "ma": 1.2,
                                  "hv_on": True, "fault": False})
        self.win.dg = FakeDG()
        self.win._dg_read_all_settings()

        self.win.on_bnc_fire()
        self.assertEqual(bnc.fired, 1, "the trigger must still be sent")

        session_rows = read_rows(self.win.shot_logger.session_file)
        master_rows = read_rows(self.tmp / "logs" / "shot_log_master.csv")
        self.assertEqual(len(session_rows), 1)
        self.assertEqual(len(master_rows), 1)

        row = session_rows[0]
        self.assertEqual(row["shot_number"], "1")
        self.assertEqual(row["session_shot_index"], "1")
        self.assertEqual(row["pressure_psi"], "55.50")
        self.assertNotEqual(row["pressure_age_ms"], "")
        self.assertEqual(row["wj1_charge_kv"], "61.000")
        self.assertEqual(row["dg535_laser_B_delay_us"], "180.500000")
        self.assertEqual(row["dg535_laser_B_ref"], "A")
        self.assertEqual(row["pulse_spacing_ns"], "200.0")
        self.assertEqual(row["session_dir"], self.dl.get_session_dir())
        self.assertEqual(row["experiment_log_file"],
                         Path(self.dl.get_log_file_path()).name)
        self.assertIn("SHOT", event_types(self.dl.get_log_file_path()))

    def test_two_fires_in_one_session(self):
        self._arm_fire_path()
        self.win.on_bnc_fire()
        self.win.on_bnc_fire()
        rows = read_rows(self.win.shot_logger.session_file)
        self.assertEqual([r["shot_number"] for r in rows], ["1", "2"])
        self.assertEqual([r["session_shot_index"] for r in rows], ["1", "2"])

    def test_blocked_fire_consumes_no_shot_number(self):
        self._arm_fire_path()
        self.win.ensure_wj_hv_off = lambda *a, **k: False   # HV not confirmed off
        before = self.win.shot_logger.peek_next_shot_number()
        self.win.on_bnc_fire()
        self.assertEqual(self.win.shot_logger.peek_next_shot_number(), before)
        self.assertEqual(read_rows(self.win.shot_logger.session_file), [])
        self.assertIn("FIRE_BLOCKED", event_types(self.dl.get_log_file_path()))

    def test_interlock_blocked_fire_is_logged_and_consumes_nothing(self):
        before = self.win.shot_logger.peek_next_shot_number()
        self.win.interlock_passed[1] = False
        self.win.on_interlock_fire()
        self.assertEqual(self.win.shot_logger.peek_next_shot_number(), before)
        self.assertIn("FIRE_BLOCKED", event_types(self.dl.get_log_file_path()))
        self.assertTrue(self.popups, "the operator must be told why it was blocked")
        self.assertIn("Interlocks", self.popups[-1][0])

    def test_scope_file_is_tied_to_the_shot(self):
        self._arm_fire_path()
        self.win.rigol1_connected = True
        self.win.on_bnc_fire()
        row = read_rows(self.win.shot_logger.session_file)[0]
        self.assertEqual(row["rigol1_file"], Path(self.dl.scope_export_path(1)).name)

        # A capture that lands after the row is written is tied by shot number.
        self.win.on_four_channel_capture_finished(
            (([0.0], [0.0]), ([], []), ([], []), ([], [])), "Rigol #1", 1)
        capture_rows = [r for r in read_rows(self.dl.get_log_file_path())
                        if r["event_type"] == "SCOPE_CAPTURE"]
        self.assertEqual(capture_rows[-1]["param4"], "1")

    def test_missing_device_data_does_not_crash_the_shot(self):
        self._arm_fire_path()
        self.win.on_bnc_fire()          # nothing cached at all
        row = read_rows(self.win.shot_logger.session_file)[0]
        self.assertEqual(row["shot_number"], "1")
        self.assertNotEqual(row["notes"], "")

    # -------------------------------------------------- DG535 apply
    def _readback(self, dg=None):
        """Attach a fake DG535 and do the readback the Apply button requires."""
        self.win.dg = dg or FakeDG()
        self.win._dg_read_all_settings()
        return self.win.dg

    def test_apply_writes_nothing_when_no_channel_was_edited(self):
        # The instrument reports more precision than the spin box shows.
        dg = self._readback(FakeDG(delays={2: (1, 0.0),
                                           3: (2, 180.5000001234e-6),
                                           5: (1, 0.0),
                                           6: (5, 180.7000004321e-6)}))
        self.question_answer = QMessageBox.StandardButton.Yes
        self.win.on_dg_apply_delays()
        self.assertEqual(dg.writes, [],
                         "extra readback precision must not look like an edit")
        self.assertTrue(any("Nothing to apply" in text for _t, text in self.popups))

    def test_apply_writes_only_the_edited_channel(self):
        dg = self._readback()
        # The operator edits C only (microseconds in the box).
        self.win.dg_panel.delay_widgets["C"]["delay"].setValue(12.5)
        self.assertEqual(self.win.dg_panel.dirty_channels(), ["C"])

        self.question_answer = QMessageBox.StandardButton.Yes
        self.win.on_dg_apply_delays()

        self.assertEqual(len(dg.writes), 1, f"expected one write, got {dg.writes}")
        channel, reference, delay = dg.writes[0]
        self.assertEqual(channel, 5, "channel C is id 5")
        self.assertEqual(reference, 1, "C keeps its T0 reference")
        self.assertAlmostEqual(delay, 12.5e-6)
        self.assertEqual(self.win.dg_panel.dirty_channels(), [],
                         "a verified apply clears the dirty flags")

    def test_apply_is_cancelled_when_the_operator_says_no(self):
        dg = self._readback()
        self.win.dg_panel.delay_widgets["C"]["delay"].setValue(9.0)
        self.question_answer = QMessageBox.StandardButton.No
        self.win.on_dg_apply_delays()
        self.assertEqual(dg.writes, [])

    def test_apply_never_sends_tm_or_ss(self):
        # FakeDG raises if TM/SS/configure_pulse_A is ever called.
        dg = self._readback()
        self.win.dg_panel.delay_widgets["A"]["delay"].setValue(1.0)
        self.question_answer = QMessageBox.StandardButton.Yes
        self.win.on_dg_apply_delays()
        self.assertTrue(dg.writes)
        self.assertEqual([c for c in dg.calls if c[0] not in
                          ("get_delay", "set_delay", "get_trigger_mode")], [])

    def test_apply_reports_a_readback_mismatch(self):
        dg = self._readback(FakeDG(honour_writes=False))   # ignores writes
        self.win.dg_panel.delay_widgets["D"]["delay"].setValue(200.0)
        self.question_answer = QMessageBox.StandardButton.Yes
        self.win.on_dg_apply_delays()
        self.assertTrue(dg.writes, "the write is still attempted")
        self.assertTrue(any("did not take the change" in title
                            for title, _text in self.popups),
                        f"expected a mismatch popup, got {self.popups}")
        errors = [r for r in read_rows(self.dl.get_log_file_path())
                  if r["event_type"] == "ERROR" and "mismatch" in r["notes"]]
        self.assertTrue(errors, "the mismatch must be logged")

    def test_apply_rejects_a_self_reference(self):
        dg = self._readback()
        widgets = self.win.dg_panel.delay_widgets["B"]
        widgets["reference"].setCurrentIndex(widgets["reference"].findText("B"))
        self.question_answer = QMessageBox.StandardButton.Yes
        self.win.on_dg_apply_delays()
        self.assertEqual(dg.writes, [])
        self.assertTrue(any("referenced to itself" in text for _t, text in self.popups))

    # -------------------------------------------------- fire paths
    def test_interlock_fire_records_a_shot(self):
        bnc = self._arm_fire_path()
        for idx in self.win.interlock_passed:
            self.win.interlock_passed[idx] = True
        self.win.on_interlock_fire()
        self.assertEqual(bnc.fired, 1)
        rows = read_rows(self.win.shot_logger.session_file)
        self.assertEqual(len(rows), 1, "step 5 must record a shot")
        self.assertEqual(rows[0]["shot_number"], "1")

    def test_external_trigger_mode_blocks_the_fire(self):
        bnc = self._arm_fire_path()
        self.win.system_state.update("bnc575", {"trigger_mode": "TRIG", "armed": True})
        before = self.win.shot_logger.peek_next_shot_number()
        self.win.on_bnc_fire()
        self.assertEqual(bnc.fired, 0, "no trigger may be sent")
        self.assertEqual(self.win.shot_logger.peek_next_shot_number(), before)
        blocked = [r for r in read_rows(self.dl.get_log_file_path())
                   if r["event_type"] == "FIRE_BLOCKED"]
        self.assertEqual(blocked[-1]["param1"], "bnc575_in_external_trigger_mode")

    def test_unarmed_scope_is_noted_in_the_shot_row(self):
        self._arm_fire_path()
        self.win.rigol2_connected = True          # connected but never armed
        self.win.on_bnc_fire()
        row = read_rows(self.win.shot_logger.session_file)[0]
        self.assertIn("rigol2", row["notes"])
        self.assertIn("not armed", row["notes"])

    def test_capture_all_sends_no_dg535_commands(self):
        dg = FakeDG()
        self.win.dg = dg
        scope = FakeScope()
        self.win.rigol1 = scope
        self.win.rigol1_connected = True
        started = []
        self.win.start_four_channel_capture = (
            lambda sc, nm, sid: started.append((nm, sid)))

        self.win.on_capture_all_scopes()

        self.assertEqual(dg.calls, [], "Capture All must not touch the DG535")
        self.assertEqual(scope.calls, ["stop", "single"], "it only arms the scope")
        self.assertEqual(started, [("Rigol #1", 1)])

    def test_capture_all_does_not_touch_hv(self):
        called = []
        self.win.ensure_wj_hv_off = lambda *a, **k: called.append(True) or True
        self.win.start_four_channel_capture = lambda *a, **k: None
        self.win.on_capture_all_scopes()
        self.assertEqual(called, [], "arming scopes must not change the HV state")

    def test_second_fire_does_not_overwrite_the_first_scope_files(self):
        self._arm_fire_path()
        self.win.rigol1_connected = True
        self.win.on_bnc_fire()
        first = read_rows(self.win.shot_logger.session_file)[0]["rigol1_file"]
        self.win.on_bnc_fire()
        second = read_rows(self.win.shot_logger.session_file)[1]["rigol1_file"]
        self.assertNotEqual(first, second, "the second shot must not reuse the name")
        self.assertRegex(first, r"^rigol1_\d{8}_\d{6}\.csv$")
        self.assertIn("_shot02", second)

    def test_delay_unit_combos_are_locked_to_microseconds(self):
        self._readback()
        for name, widgets in self.win.dg_panel.delay_widgets.items():
            combo = widgets["delay_combo"]
            self.assertFalse(combo.isEnabled(),
                             f"channel {name}: the unit dropdown must be locked")
            self.assertAlmostEqual(
                combo.currentData(), 1e-6,
                msg=f"channel {name}: delays must be in microseconds")
            self.assertEqual(combo.currentText().lower().replace("μ", "u"), "us",
                             f"channel {name}: unit text should read microseconds")

    def test_close_after_shot_leaves_logs_complete(self):
        self._arm_fire_path()
        self.win.on_bnc_fire()
        self.win.close()
        types = event_types(self.dl.get_log_file_path())
        self.assertIn("SESSION_END", types)
        self.assertEqual(len(read_rows(self.win.shot_logger.session_file)), 1)
        counter = json.loads((self.tmp / "logs" / "shot_counter.json").read_text())
        self.assertEqual(counter["last_shot"], 1)
        # The lock is released, so the next GUI can claim numbers.
        self.assertTrue(ShotCounter(self.tmp / "logs").acquire_lock())

    def test_wj_reader_packets_reach_the_handler_through_the_signal(self):
        """The reader threads emit into wj_packet_ready so Qt queues the
        packet onto the GUI thread. Wiring them straight to on_wj_packet ran
        it on the reader thread, where touching a widget is undefined."""
        self.win.wj_packet_ready.emit(0, {"type": "R", "kv": 65.0, "ma": 2.0,
                                          "hv_on": True, "fault": False})
        self.assertIn("65.00 kV", self.win.wj_panel.rows[0].label_status.text())

    def test_window_title_is_the_shot_control_title(self):
        self.assertEqual(self.win.windowTitle(), "MultiPulse Shot Control")

    def test_wj_fault_unlatches_interlock_step3(self):
        """A latch must not outlive its evidence: step 3 latched on both
        supplies reading back healthy, so a later fault drops it to red."""
        good = {"type": "R", "kv": 70.0, "ma": 1.5, "hv_on": True, "fault": False}
        self.win.on_wj_packet(0, good)
        self.win.on_wj_packet(1, good)
        self.assertTrue(self.win.interlock_passed[3], "step 3 should have latched")

        self.win.on_wj_packet(1, dict(good, fault=True))
        self.assertFalse(self.win.interlock_passed[3],
                         "a faulted supply must clear step 3")
        self.assertFalse(self.win.btn_interlock_fire.isEnabled())
        self.assertIn("INTERLOCK_FAIL", event_types(self.dl.get_log_file_path()))

    def test_step3_relatches_once_the_fault_clears(self):
        good = {"type": "R", "kv": 70.0, "ma": 1.5, "hv_on": True, "fault": False}
        self.win.on_wj_packet(0, good)
        self.win.on_wj_packet(1, good)
        self.win.on_wj_packet(1, dict(good, fault=True))
        self.assertFalse(self.win.interlock_passed[3])

        # Healthy again from both supplies re-satisfies the step.
        self.win.on_wj_packet(1, good)
        self.assertTrue(self.win.interlock_passed[3])

    def test_wj_packet_updates_the_per_supply_status_row(self):
        """Deleting the READBACK button left nothing writing these labels."""
        self.win.on_wj_packet(0, {"type": "R", "kv": 70.0, "ma": 1.5,
                                  "hv_on": True, "fault": False})
        text = self.win.wj_panel.rows[0].label_status.text()
        self.assertIn("70.00 kV", text)
        self.assertIn("1.500 mA", text)
        self.assertIn("HV ON", text)
        self.assertNotIn("FAULT", text)

    def test_wj_fault_is_called_out_on_the_row(self):
        self.win.on_wj_packet(1, {"type": "R", "kv": 0.0, "ma": 0.0,
                                  "hv_on": False, "fault": True})
        self.assertIn("FAULT", self.win.wj_panel.rows[1].label_status.text())

    def test_interlock_step3_latches_from_the_reader(self):
        """Step 3 used to latch from the READBACK button, which is gone."""
        self.assertFalse(self.win.interlock_passed.get(3))
        good = {"type": "R", "kv": 70.0, "ma": 1.5, "hv_on": True, "fault": False}
        self.win.on_wj_packet(0, good)
        self.assertFalse(self.win.interlock_passed.get(3),
                         "one supply is not both supplies")
        self.win.on_wj_packet(1, good)
        self.assertTrue(self.win.interlock_passed.get(3))

    def test_faulted_supply_does_not_satisfy_step3(self):
        good = {"type": "R", "kv": 70.0, "ma": 1.5, "hv_on": True, "fault": False}
        bad = dict(good, fault=True)
        self.win.on_wj_packet(0, good)
        self.win.on_wj_packet(1, bad)
        self.assertFalse(self.win.interlock_passed.get(3))

    def test_pressure_value_is_passed_through_unscaled(self):
        """The Opta computes psi from its own calibration registers. Removing
        the calibration UI must not have introduced any GUI-side scaling."""
        self.win._opta_link_up = True
        self.win._on_pressure_data({
            "psi": 42.37, "volts": 4.237, "counts": 1234, "uptime_s": 10,
            "under_range": False, "over_range": False})
        self.assertEqual(self.win.system_state.get("pressure")["psi"], 42.37)
        self.assertEqual(self.win._latest_psi, 42.37)
        self.assertIn("42.37", self.win.sf6_window.sf6_panel.lbl_psi.text())

    def test_connection_memory_writes_go_to_the_temp_copy(self):
        """Connect handlers end in save_memory(). With the path patched, the
        write lands in the temp folder.

        Uses a port key: scope resources are derived from SCOPE_TRANSPORT and
        save_memory refuses them outright.
        """
        save_memory("DG535_COM", "COM41")
        written = json.loads((self.tmp / "connection_memory.json").read_text())
        self.assertEqual(written["DG535_COM"], "COM41")

    def test_real_connection_memory_is_untouched(self):
        """Building the window and saving ports must leave the operator's real
        connection_memory.json byte-for-byte identical."""
        if not REAL_MEMORY_FILE.exists():
            self.skipTest("no real connection_memory.json in this checkout")
        before = REAL_MEMORY_FILE.read_bytes()
        save_memory("DG535_COM", "COM99")
        save_memory("BNC575_COM", "COM98")
        self.assertEqual(REAL_MEMORY_FILE.read_bytes(), before,
                         "a test wrote to the real connection_memory.json")


class TestRigolAddresses(unittest.TestCase):
    """The three scopes are on the instrument network, addressed by number.

    rigol1 -> .51, rigol2 -> .52, rigol3 -> .53, in either transport.
    """

    IPS = {1: "192.168.10.51", 2: "192.168.10.52", 3: "192.168.10.53"}

    def test_defaults_are_the_ethernet_addresses(self):
        from utils.connect_memory import default_data, scope_resource
        for n in (1, 2, 3):
            self.assertEqual(default_data[f"Rigol{n}_VISA"], scope_resource(n),
                             f"Rigol{n}_VISA must come from scope_resource()")
            self.assertIn(self.IPS[n], default_data[f"Rigol{n}_VISA"])

    def test_no_usb_visa_address_remains_in_the_defaults(self):
        from utils.connect_memory import default_data
        leftovers = {k: v for k, v in default_data.items()
                     if isinstance(v, str) and "USB0::" in v}
        self.assertEqual(leftovers, {}, "a saved USB address would override the default")

    def test_each_transport_keeps_the_scope_numbering(self):
        """Switching transport must not renumber or re-address a scope."""
        import utils.connect_memory as cm
        for transport, suffix in (("socket", "::5555::SOCKET"), ("instr", "::INSTR")):
            with patch.object(cm, "SCOPE_TRANSPORT", transport):
                for n in (1, 2, 3):
                    self.assertEqual(cm.scope_resource(n),
                                     f"TCPIP0::{self.IPS[n]}{suffix}",
                                     f"scope {n} wrong in {transport} mode")

    def test_saved_memory_cannot_override_the_transport(self):
        """A Rigol string left in the JSON by an older run must be ignored,
        or flipping SCOPE_TRANSPORT would appear to do nothing."""
        import utils.connect_memory as cm
        with tempfile.TemporaryDirectory() as tmp:
            mem = Path(tmp) / "connection_memory.json"
            mem.write_text(json.dumps({
                "DG535_COM": "COM4",
                "Rigol1_VISA": "TCPIP0::10.0.0.1::INSTR",
                "Rigol2_VISA": "USB0::0x1AB1::0x0514::XYZ::0::INSTR",
                "Rigol3_VISA": "nonsense",
            }))
            with patch.object(cm, "MEM_FILE", str(mem)):
                data = cm.load_memory(resolve=False)
        for n in (1, 2, 3):
            self.assertEqual(data[f"Rigol{n}_VISA"], cm.scope_resource(n))
        # Everything else in the file is still honoured.
        self.assertEqual(data["DG535_COM"], "COM4")

    def test_scope_resources_are_never_written_to_memory(self):
        import utils.connect_memory as cm
        with tempfile.TemporaryDirectory() as tmp:
            mem = Path(tmp) / "connection_memory.json"
            with patch.object(cm, "MEM_FILE", str(mem)):
                cm.save_memory("Rigol1_VISA", "TCPIP0::10.0.0.9::INSTR")
                self.assertFalse(mem.exists(),
                                 "saving a scope resource must write nothing")
                # A real port still saves normally.
                cm.save_memory("DG535_COM", "COM41")
                saved = json.loads(mem.read_text())
        self.assertEqual(saved["DG535_COM"], "COM41")
        # Saving an unrelated port must not write the derived scope keys back
        # into the file either. load_memory() injects them on every read, so
        # without an explicit strip they reappear the first time any other
        # device saves its port.
        for n in (1, 2, 3):
            self.assertNotIn(f"Rigol{n}_VISA", saved,
                             "scope resources must never be persisted")


class TestSimplifiedPanels(unittest.TestCase):
    """Panel behavior after the GUI simplification. No main window, no ports."""

    # ------------------------------------------------------------ WJ supplies
    def test_preset_fills_the_field_and_sends_nothing(self):
        from gui.wj_panel import WJPanel
        panel = WJPanel(num_units=2)
        panel.voltage.setValue(60.0)
        panel.preset_buttons[70.0].click()
        self.assertEqual(panel.voltage.value(), 70.0)
        # A preset is a field edit only: the panel holds no supply handles at
        # all, so there is nothing it could have commanded.
        self.assertFalse(hasattr(panel, "wj_units"))

    def test_every_preset_is_within_the_rating(self):
        from gui.wj_panel import WJPanel
        panel = WJPanel(num_units=2)
        for kv, btn in panel.preset_buttons.items():
            btn.click()
            self.assertLessEqual(kv, WJPanel.MAX_KV)
            self.assertEqual(panel.program_values()[0], kv)

    def test_value_above_the_rating_is_rejected(self):
        from gui.wj_panel import WJPanel
        panel = WJPanel(num_units=2)
        # The spin box clamps at the rating, so defeat it to prove the check
        # is in program_values() and not only in the widget.
        panel.voltage.setRange(0, 500)
        panel.voltage.setValue(150.0)
        with self.assertRaises(ValueError):
            panel.program_values()

        panel.voltage.setValue(75.0)
        panel.current.setRange(0, 50)
        panel.current.setValue(12.0)
        with self.assertRaises(ValueError):
            panel.program_values()

    def test_current_defaults_to_full_scale(self):
        """Behavior is unchanged until the operator edits the field: every
        supply used to be commanded to its maximum current."""
        from gui.wj_panel import WJPanel
        panel = WJPanel(num_units=2)
        self.assertEqual(panel.current.value(), WJPanel.MAX_MA)
        self.assertEqual(panel.program_values(), (60.0, WJPanel.MAX_MA))

    # ---------------------------------------------------------------- lasers
    def test_both_lasers_default_to_ext_ext(self):
        from gui.laser_panel import DualLaserPanel
        panel = DualLaserPanel()
        self.assertEqual(len(panel.lasers), 2)
        for col in panel.lasers:
            self.assertTrue(col.rb_ext.isChecked(), f"{col.title} must default to EXT/EXT")
            self.assertFalse(col.rb_int.isChecked())
            self.assertEqual(col._mode(), "EXT/EXT")

    def test_laser_columns_keep_their_event_tags(self):
        """LASER_* events and the laser1_* / laser2_* shot columns key off these."""
        from gui.laser_panel import DualLaserPanel
        panel = DualLaserPanel()
        self.assertEqual([c._log_tag for c in panel.lasers], ["Laser1", "Laser2"])
        self.assertEqual([c._save_key for c in panel.lasers],
                         ["CFR_LASER_COM", "CFR_LASER2_COM"])

    def test_prep_system_preps_both_lasers(self):
        from gui.laser_panel import DualLaserPanel
        panel = DualLaserPanel()
        started = []

        for col in panel.lasers:
            def start(c=col):
                started.append(c._log_tag)
                return True
            col.start_prep = start

        panel.on_prep_both()
        self.assertEqual(started, ["Laser1", "Laser2"])

    def test_one_laser_failing_prep_does_not_skip_the_other(self):
        from gui.laser_panel import DualLaserPanel
        panel = DualLaserPanel()
        started = []

        def fail_laser1():
            started.append("Laser1")
            panel.laser1.sig_prep_done.emit("Laser1", False, "not connected")
            return False

        def ok_laser2():
            started.append("Laser2")
            return True

        panel.laser1.start_prep = fail_laser1
        panel.laser2.start_prep = ok_laser2

        panel.on_prep_both()
        self.assertEqual(started, ["Laser1", "Laser2"],
                         "laser 2 must still be prepped after laser 1 fails")

        panel.laser2.sig_prep_done.emit("Laser2", True, "ARMED")
        text = panel.prep_result_label.text()
        self.assertIn("CFR Laser 1: FAILED (not connected)", text)
        self.assertIn("CFR Laser 2: OK (ARMED)", text)

    def test_verify_armed_checks_both_lasers(self):
        from gui.laser_panel import DualLaserPanel
        panel = DualLaserPanel()
        checked = []

        for col in panel.lasers:
            def verify(c=col):
                checked.append(c._log_tag)
                return True
            col.start_verify = verify

        panel.on_verify_both()
        self.assertEqual(checked, ["Laser1", "Laser2"])

    def test_verify_reports_each_laser_separately(self):
        from gui.laser_panel import DualLaserPanel
        panel = DualLaserPanel()
        panel.laser1.sig_verify_done.emit("Laser1", True, "ARMED")
        panel.laser2.sig_verify_done.emit("Laser2", False, "NOT ARMED: idle")
        text = panel.result_label.text()
        self.assertIn("CFR Laser 1: ARMED", text)
        self.assertIn("CFR Laser 2: NOT ARMED", text)

    # ------------------------------------------------------- removed controls
    def test_dg535_keeps_only_the_delays(self):
        from gui.dg535_panel import DG535Panel
        panel = DG535Panel()
        # No tab bar left: one page of content, built straight into the panel.
        self.assertFalse(hasattr(panel, "tabs"))
        self.assertEqual(sorted(panel.delay_widgets), ["A", "B", "C", "D"])
        for gone in ("btn_apply_trigger", "btn_apply_outputs", "btn_store",
                     "btn_recall", "btn_recall_defaults", "btn_read_status",
                     "btn_clear", "btn_apply_all", "btn_fire"):
            self.assertFalse(hasattr(panel, gone), f"{gone} should be gone")
        for kept in ("btn_connect", "btn_disconnect", "btn_read_all",
                     "btn_apply_delays", "trigger_mode_label"):
            self.assertTrue(hasattr(panel, kept), f"{kept} must remain")

    def test_dg535_delay_units_stay_microseconds(self):
        from gui.dg535_panel import DG535Panel
        panel = DG535Panel()
        for name, w in panel.delay_widgets.items():
            self.assertFalse(w["delay_combo"].isEnabled(), f"{name} unit must be locked")
            self.assertEqual(w["delay_combo"].currentData(), 1e-6)

    def test_bnc575_keeps_timing_and_drops_arming(self):
        from gui.bnc575_panel import BNC575Panel
        panel = BNC575Panel()
        self.assertFalse(hasattr(panel, "tabs"))
        for gone in ("btn_arm", "btn_en_a", "btn_en_trig", "btn_apply_trigger",
                     "btn_apply_system", "btn_store", "btn_recall", "btn_factory",
                     "system_mode", "frequency", "clock_source"):
            self.assertFalse(hasattr(panel, gone), f"{gone} should be gone")
        for kept in ("btn_connect", "btn_fire", "btn_apply", "btn_read",
                     "period", "trigger_mode_label"):
            self.assertTrue(hasattr(panel, kept), f"{kept} must remain")
        # The enable state is still readable for the shot row, read-only.
        panel.set_channel_enabled("A", True)
        self.assertTrue(panel.is_channel_enabled("A"))
        self.assertEqual(panel.enable_labels["A"].text(), "ON")

    def test_bnc575_delays_are_locked_to_microseconds(self):
        from gui.bnc575_panel import BNC575Panel
        panel = BNC575Panel()
        for ch in ("A", "B", "C", "D"):
            unit = getattr(panel, f"delay{ch}_unit")
            self.assertEqual(unit.get_multiplier(), 1e-6, f"delay {ch} must be µs")
            for btn in unit.btn_group.buttons():
                self.assertFalse(btn.isEnabled(), f"delay {ch} unit must be locked")
        # A delay typed as 200 is 200 µs, whatever else is on the panel.
        panel.delayA.setValue(200.0)
        self.assertAlmostEqual(panel.get_delayA(), 200e-6)

    def test_the_three_action_buttons_are_colour_coded(self):
        """Fire, Prep System and Capture All are what the operator reaches for
        during a shot. They must not look like every other button, and they
        must not look like each other."""
        from gui.bnc575_panel import BNC575Panel
        from gui.laser_panel import DualLaserPanel
        from gui.rigol_panel import RigolPanel
        from utils.accent_button import FIRE_RED, PREP_BLUE, CAPTURE_GREEN

        # Hold the panels in locals: a temporary panel is garbage collected
        # and Qt deletes its children with it, leaving a dead button.
        bnc, lasers, rigol = BNC575Panel(), DualLaserPanel(), RigolPanel()
        checks = [("Fire", bnc.btn_fire, FIRE_RED),
                  ("Prep System", lasers.btn_prep, PREP_BLUE),
                  ("Capture All", rigol.btn_capture, CAPTURE_GREEN)]
        for name, btn, colour in checks:
            style = btn.styleSheet()
            self.assertIn(colour, style, f"{name} must carry its accent colour")
            self.assertIn("color: white", style, f"{name} must not be default-coloured")
        self.assertEqual(len({c for _, _, c in checks}), 3,
                         "the three actions must be three different colours")

    def test_instrument_panels_fit_without_scrolling(self):
        """The grid is the lasers across the top, then BNC575 | DG535, then
        Rigol | WJ. Their minimum sizes are what force a scrollbar, so they
        have to stay inside what a 1920x1080 desktop leaves for the window."""
        from gui.bnc575_panel import BNC575Panel
        from gui.dg535_panel import DG535Panel
        from gui.laser_panel import DualLaserPanel
        from gui.rigol_panel import RigolPanel
        from gui.wj_panel import WJPanel

        m = {name: w.minimumSizeHint() for name, w in (
            ("lasers", DualLaserPanel()), ("bnc", BNC575Panel()),
            ("dg", DG535Panel()), ("rigol", RigolPanel()), ("wj", WJPanel()))}
        rows = [
            (m["lasers"].height(), m["lasers"].width()),
            (max(m["bnc"].height(), m["dg"].height()), m["bnc"].width() + m["dg"].width()),
            (max(m["rigol"].height(), m["wj"].height()), m["rigol"].width() + m["wj"].width()),
        ]
        total_h = sum(r[0] for r in rows)
        widest = max(r[1] for r in rows)
        # Budget: about 160 px of status strips and margins vertically, and
        # 380 px for the relay/log column horizontally.
        self.assertLessEqual(total_h + 160, 1010,
                             f"instrument grid would scroll vertically ({total_h} px of panels)")
        self.assertLessEqual(widest + 380, 1900,
                             f"instrument grid would scroll horizontally ({widest} px widest row)")

    def test_pressure_panel_has_no_calibration_controls(self):
        from gui.sf6_panel import MarxPressurePanel
        panel = MarxPressurePanel()
        self.assertEqual(panel.title(), "Marx Pressure")
        for gone in ("spin_full_scale", "btn_set_full_scale", "btn_zero_here",
                     "lbl_cal_full_scale", "lbl_cal_zero", "lbl_cal_avg"):
            self.assertFalse(hasattr(panel, gone), f"{gone} should be gone")


class TestOptaCalibration(unittest.TestCase):
    """The calibration lives on the Opta; the GUI writes and verifies it."""

    class FakeOpta:
        def __init__(self, reports):
            self.reports = reports
            self.writes = []

        def set_full_scale_psi(self, psi):
            self.writes.append(("full_scale_psi", psi))

        def set_zero_offset_mv(self, mv):
            self.writes.append(("zero_offset_mv", mv))

        def read_calibration(self):
            return dict(self.reports)

    def _worker(self, reports):
        from utils.pressure_worker import PressureWorker
        w = PressureWorker("192.0.2.1")      # never connected
        w.io = self.FakeOpta(reports)
        return w

    def test_constants_match_the_transducer(self):
        from instruments.opta_pressure import (
            OPTA_FULL_SCALE_PSI, OPTA_ZERO_OFFSET_MV, OPTA_AVG_SAMPLES)
        # 0-10 V / 0-100 psi transducer.
        self.assertEqual(OPTA_FULL_SCALE_PSI, 100.0)
        self.assertEqual(OPTA_ZERO_OFFSET_MV, 0)
        self.assertEqual(OPTA_AVG_SAMPLES, 32)

    def test_connect_writes_then_verifies(self):
        from instruments.opta_pressure import OPTA_FULL_SCALE_PSI, OPTA_ZERO_OFFSET_MV
        w = self._worker({"full_scale_psi": 100.0, "zero_offset_mv": 0,
                          "avg_samples": 32})
        cal = w._apply_calibration()
        self.assertEqual(w.io.writes, [("full_scale_psi", OPTA_FULL_SCALE_PSI),
                                       ("zero_offset_mv", OPTA_ZERO_OFFSET_MV)])
        self.assertTrue(cal["verified"])
        self.assertEqual(cal["mismatch"], "")

    def test_readback_that_disagrees_is_flagged(self):
        w = self._worker({"full_scale_psi": 159.4, "zero_offset_mv": 0,
                          "avg_samples": 32})
        seen = []
        w.calibration_mismatch.connect(seen.append)
        cal = w._apply_calibration()
        self.assertFalse(cal["verified"])
        self.assertIn("full scale", cal["mismatch"])
        self.assertEqual(len(seen), 1, "a mismatch must be reported once")


class TestTmcBlockReads(unittest.TestCase):
    """_query_binary reads a TMC block by its declared length.

    It used to call read_raw() once. A raw TCP socket is an undelimited byte
    stream, so read_raw() had no stop condition and every waveform read
    blocked until the 30 s timeout: VI_ERROR_TMO on every channel.
    """

    PAYLOAD = bytes(range(256)) * 4      # 1024 bytes, every byte value

    def _scope(self, instr):
        """A RigolScope with no VISA session. __new__ skips __init__, which
        would build a pyvisa ResourceManager."""
        from instruments.rigol import RigolScope
        scope = RigolScope.__new__(RigolScope)
        scope.instr = instr
        return scope

    def test_normal_block_instr_style(self):
        """VXI-11 hands over one complete message."""
        instr = FakeVisaInstrument([tmc_block(self.PAYLOAD)])
        scope = self._scope(instr)
        self.assertEqual(scope._query_binary(":WAVeform:DATA?"), self.PAYLOAD)
        self.assertEqual(instr.written, [":WAVeform:DATA?"])

    def test_normal_block_socket_style(self):
        """A socket delivers the same block in whatever pieces arrive."""
        blob = tmc_block(self.PAYLOAD)
        pieces = [blob[i:i + 7] for i in range(0, len(blob), 7)]
        scope = self._scope(FakeVisaInstrument(pieces))
        self.assertEqual(scope._query_binary(":WAVeform:DATA?"), self.PAYLOAD)

    def test_block_delivered_in_several_short_pieces(self):
        """Reassembly must not depend on how the stream was chopped up."""
        blob = tmc_block(self.PAYLOAD)
        pieces = [blob[:1], blob[1:2], blob[2:3], blob[3:9], blob[9:500],
                  blob[500:501], blob[501:]]
        instr = FakeVisaInstrument(pieces)
        scope = self._scope(instr)
        self.assertEqual(scope._query_binary(":WAVeform:DATA?"), self.PAYLOAD)
        # Header byte pair, the length digits, the payload, then the newline.
        self.assertEqual(instr.reads[:3], [2, 4, len(self.PAYLOAD)])

    def test_short_block_raises_rather_than_truncating(self):
        """The header promises 64 bytes and only 3 arrive."""
        instr = FakeVisaInstrument([tmc_block(b"\x01\x02\x03", declared=64)])
        scope = self._scope(instr)
        with self.assertRaises(Exception):
            scope._query_binary(":WAVeform:DATA?")

    def test_lenient_transport_short_read_is_caught_by_the_length_check(self):
        """A transport that returns short instead of raising must still not
        yield a truncated waveform."""
        instr = FakeVisaInstrument([tmc_block(b"\x01\x02\x03", declared=64)],
                                   lenient=True)
        scope = self._scope(instr)
        with self.assertRaises(IOError) as cm:
            scope._query_binary(":WAVeform:DATA?")
        self.assertIn("declared 64", str(cm.exception))

    def test_missing_trailing_newline_does_not_stall(self):
        """A block with no trailing newline must return, and must not spend
        the 30 s driver timeout waiting for a byte that is not coming."""
        payload = b"\xde\xad\xbe\xef"
        instr = FakeVisaInstrument([tmc_block(payload, newline=False)])
        scope = self._scope(instr)
        self.assertEqual(scope._query_binary(":WAVeform:DATA?"), payload)
        self.assertIn(200, instr.timeouts_seen, "newline read must use a short timeout")
        self.assertEqual(instr.timeout, 30000, "driver timeout must be restored")

    def test_read_termination_is_restored(self):
        instr = FakeVisaInstrument([tmc_block(b"\x00\x01")], read_termination="\n")
        scope = self._scope(instr)
        scope._query_binary(":WAVeform:DATA?")
        self.assertEqual(instr.read_termination, "\n")

    def test_read_termination_is_restored_even_on_failure(self):
        instr = FakeVisaInstrument([b"XX"], read_termination="\n")
        scope = self._scope(instr)
        with self.assertRaises(ValueError):
            scope._query_binary(":WAVeform:DATA?")
        self.assertEqual(instr.read_termination, "\n")

    def test_bad_header_raises(self):
        instr = FakeVisaInstrument([b"XX1234"])
        scope = self._scope(instr)
        with self.assertRaises(ValueError):
            scope._query_binary(":WAVeform:DATA?")

    def test_driver_has_no_read_raw_call_left(self):
        """read_raw() is what stalled on a socket; nothing may reintroduce it.

        Matches the call, not the name: the replacement docstring mentions
        read_raw() in prose to say why it must not be used here.
        """
        import inspect
        from instruments import rigol
        self.assertNotIn("self.instr.read_raw(", inspect.getsource(rigol))


if __name__ == "__main__":
    unittest.main(verbosity=2)
