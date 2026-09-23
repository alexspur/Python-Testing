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
from utils.system_state import SystemState, SOURCE_READBACK

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
