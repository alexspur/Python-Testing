"""Automatic shot analysis from the GUI.

QProcess is replaced by FakeQProcess in the shared fixture, so no test here
(or anywhere in the GUI suite) can start a real child process. The fake
records the command and is fed output by the test.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PyQt6.QtGui import QImage

from tests.test_shot_logging import FakeQProcess, GuiWindowTestCase, read_rows

RESULT = {"shot_number": 1, "key": "shot_0001", "status": "ok",
          "spacing_cmd_ns": "200", "spacing_qsw_ns": "201.3", "spacing_rvm_ns": "199.8",
          "analysis_png": "", "raw_png": "", "error": ""}


def png(path):
    img = QImage(40, 30, QImage.Format.Format_RGB32)
    img.fill(0xFF00A0B0)
    assert img.save(str(path))
    return str(path)


class TestAutoAnalysis(GuiWindowTestCase):

    def _complete_export(self, scope_ids=(1,)):
        """Drive the export completion the way the last worker does."""
        self.win.export_workers = []
        self.win.captured_scopes = {sid: "d" for sid in scope_ids}
        self.win._export_scope_ids = set(scope_ids)
        self.win._export_pending = 1
        self.win._export_done_paths = []
        self.win._export_failed = {}
        self.win._export_silent = True
        self.win._captures_dirty = True
        self.win._on_one_export_finished(str(self.tmp / f"rigol{max(scope_ids)}_x.csv"))

    def _fire(self):
        self._arm_fire_path()
        self.win.on_bnc_fire()
        self._reprep()

    def _gui_log(self):
        return self.dl.gui_log_file.read_text(encoding="utf-8")

    def _proc(self):
        self.assertTrue(FakeQProcess.instances, "no analysis process was started")
        return FakeQProcess.instances[-1]

    # ------------------------------------------------------- the command
    def test_analysis_starts_after_the_last_export_with_command_and_cwd(self):
        self._fire()
        self._complete_export()
        p = self._proc()
        session = str(Path(self.dl.get_session_dir()).resolve())
        self.assertEqual(p.program, sys.executable)
        self.assertEqual(p.arguments, ["-m", "analysis", "--session", session, "--shot", "1"])
        repo = Path(__file__).resolve().parent.parent
        self.assertEqual(Path(p.working_dir), repo)
        self.assertEqual(p.env.value("PYTHONIOENCODING"), "utf-8")
        self.assertTrue(p.started)
        self.assertIn("[ANALYSIS] starting shot 1:", self._gui_log())

    def test_no_run_without_a_shot_number(self):
        self._complete_export()                     # nothing was fired
        self.assertEqual(FakeQProcess.instances, [])
        self.assertIn("[ANALYSIS] not started: this export has no shot number", self._gui_log())

    def test_failed_export_does_not_start_an_analysis(self):
        self._fire()
        self.win.export_workers = []
        self.win.captured_scopes = {1: "d1", 2: "d2"}
        self.win._export_scope_ids = {1}
        self.win._export_failed = {2: "rigol2_x.csv"}
        self.win._export_pending = 1
        self.win._export_done_paths = []
        self.win._export_silent = True
        self.win._on_one_export_finished("rigol1_x.csv")
        self.assertEqual(FakeQProcess.instances, [])

    # ------------------------------------------------------------ queue
    def test_second_shot_queues_while_the_first_runs(self):
        self._fire()
        self._complete_export()
        first = self._proc()
        self._fire()                                # shot 2
        self._complete_export()
        self.assertEqual(len(FakeQProcess.instances), 1, "one analysis at a time")
        self.assertEqual(self.win.analysis.pending(), 1)
        self.assertIn("[ANALYSIS] queued shot 2 (1 run(s) ahead)", self._gui_log())

        first.finish(0)
        self.assertEqual(len(FakeQProcess.instances), 2)
        self.assertEqual(FakeQProcess.instances[-1].arguments[-2:], ["--shot", "2"])
        self.assertEqual(self.win.analysis.pending(), 0)

    # --------------------------------------------------------- checkbox
    def test_no_run_when_analyze_after_each_shot_is_off(self):
        import utils.connect_memory as cm
        self.win.chk_analyze.setChecked(False)
        self._fire()
        self._complete_export()
        self.assertEqual(FakeQProcess.instances, [])
        self.assertIn("[ANALYSIS] skipped: 'Analyze after each shot' is off", self._gui_log())
        # Remembered the same way the ports are: in connection_memory.json.
        saved = json.loads(Path(cm.MEM_FILE).read_text())
        self.assertIs(saved["ANALYZE_AFTER_SHOT"], False)
        self.assertEqual(Path(cm.MEM_FILE).resolve().parent, self.tmp.resolve(),
                         "the test must be writing the temp copy")

    def test_checkboxes_default_on_and_come_from_memory(self):
        self.assertTrue(self.win.chk_analyze.isChecked())
        self.assertTrue(self.win.chk_show_plots.isChecked())
        import utils.connect_memory as cm
        self.assertIs(cm.default_data["ANALYZE_AFTER_SHOT"], True)
        self.assertIs(cm.default_data["SHOW_ANALYSIS_PLOTS"], True)

    # ------------------------------------------------------ log + event
    def test_stdout_goes_to_the_log_verbatim_and_result_lines_make_events(self):
        self._fire()
        self._complete_export()
        p = self._proc()
        p.feed_stdout("[ANALYSIS] 1 session folder(s) under X\n")
        p.feed_stdout("[ANALYSIS] #0001: OK in 3.1 s  D 512/508 kV\n")
        p.feed_stdout("[ANALYSIS] result " + json.dumps(RESULT) + "\n")
        p.feed_stderr("Traceback (most recent call last):\n  boom\n")
        log = self._gui_log()
        self.assertIn("[ANALYSIS] #0001: OK in 3.1 s  D 512/508 kV", log)
        self.assertIn("[ANALYSIS] stderr: Traceback (most recent call last):", log)
        self.assertIn("[ANALYSIS] stderr:   boom", log)
        rows = [r for r in read_rows(self.dl.get_log_file_path()) if r["event_type"] == "ANALYSIS"]
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["source"], r["param1"], r["param2"], r["param3"], r["param4"]),
                         ("Analysis", "ok", "200", "201.3", "1"))
        self.assertEqual(r["notes"], "spacing_rvm_ns=199.8; error=")

    def test_partial_lines_are_held_until_their_newline(self):
        self._fire()
        self._complete_export()
        p = self._proc()
        p.feed_stdout("[ANALYSIS] first ha")
        self.assertNotIn("first ha", self._gui_log())
        p.feed_stdout("lf, then whole\n[ANALYSIS] tail without newline")
        self.assertIn("[ANALYSIS] first half, then whole", self._gui_log())
        self.assertNotIn("tail without newline", self._gui_log())
        p.finish(0)
        self.assertIn("[ANALYSIS] tail without newline", self._gui_log())
        self.assertIn("[ANALYSIS] shot 1 finished, exit code 0", self._gui_log())

    def test_dry_shot_result_records_its_status_and_error(self):
        self._fire()
        self._complete_export()
        dry = dict(RESULT, status="no_fire", spacing_rvm_ns="",
                   error="no pulse detected on any anchor channel")
        self._proc().feed_stdout("[ANALYSIS] result " + json.dumps(dry) + "\n")
        r = [x for x in read_rows(self.dl.get_log_file_path()) if x["event_type"] == "ANALYSIS"][-1]
        self.assertEqual(r["param1"], "no_fire")
        self.assertEqual(r["notes"], "spacing_rvm_ns=; error=no pulse detected on any anchor channel")

    # ------------------------------------------------------------ plots
    def test_fired_shot_shows_analysis_png_and_dry_shot_shows_raw_png(self):
        a_png = png(self.tmp / "shot_0001_analysis.png")
        r_png = png(self.tmp / "shot_0001_raw.png")
        self._fire()
        self._complete_export()
        p = self._proc()
        p.feed_stdout("[ANALYSIS] result " + json.dumps(dict(RESULT, analysis_png=a_png, raw_png=r_png)) + "\n")
        p.finish(0)
        w = self.win.analysis_window
        self.assertIsNotNone(w, "a finished run must show its figure")
        self.assertEqual(w.path, a_png)
        self.assertTrue(w.isVisible())
        self.assertIsNotNone(w.image.pixmap())
        self.assertIn("Shot 1: ok", w.caption.text())

        # A dry shot has no analysis figure; the raw figure stands in.
        self._fire()
        self._complete_export()
        p = self._proc()
        dry = dict(RESULT, shot_number=2, status="no_fire", analysis_png="", raw_png=r_png)
        p.feed_stdout("[ANALYSIS] result " + json.dumps(dry) + "\n")
        p.finish(0)
        self.assertIs(self.win.analysis_window, w, "one window, reused")
        self.assertEqual(w.path, r_png)
        self.assertIn("Shot 2: no_fire", w.caption.text())

    def test_no_plot_window_when_show_plots_is_off(self):
        a_png = png(self.tmp / "shot_0001_analysis.png")
        self.win.chk_show_plots.setChecked(False)
        self._fire()
        self._complete_export()
        p = self._proc()
        p.feed_stdout("[ANALYSIS] result " + json.dumps(dict(RESULT, analysis_png=a_png)) + "\n")
        p.finish(0)
        self.assertIsNone(self.win.analysis_window)

    def test_missing_png_is_logged_not_shown(self):
        self._fire()
        self._complete_export()
        p = self._proc()
        gone = str(self.tmp / "nope.png")
        p.feed_stdout("[ANALYSIS] result " + json.dumps(dict(RESULT, analysis_png=gone)) + "\n")
        p.finish(0)
        self.assertIsNone(self.win.analysis_window)
        self.assertIn("[ANALYSIS] plot not found: " + gone, self._gui_log())

    def test_plot_window_scales_to_fit_and_keeps_aspect(self):
        from PyQt6.QtWidgets import QApplication
        from gui.analysis_window import AnalysisPlotWindow
        w = AnalysisPlotWindow()
        self.addCleanup(w.close)
        w.show()                                    # the layout only sizes a shown window
        w.resize(600, 300)                          # 2:1, so a 4:3 image cannot fill it
        QApplication.processEvents()
        w.show_image(png(self.tmp / "p.png"), "caption")
        pm = w.image.pixmap()
        self.assertFalse(pm.isNull())
        label = w.image.size()
        self.assertNotAlmostEqual(label.width() / label.height(), 40 / 30, places=1,
                                  msg="the label must not share the image's aspect")
        self.assertLessEqual(pm.width(), label.width())
        self.assertLessEqual(pm.height(), label.height())
        self.assertEqual(pm.height(), label.height(), "scaled up to fit the short side")
        self.assertAlmostEqual(pm.width() / pm.height(), 40 / 30, places=1)
        with patch("gui.analysis_window.open_with_system") as opened:
            w.btn_full.click()
            w.btn_folder.click()
        self.assertEqual([c.args[0] for c in opened.call_args_list],
                         [w.path, Path(w.path).parent])

    # ---------------------------------------------------------- buttons
    def test_analyze_all_shots_runs_the_logs_root(self):
        self.win.btn_analyze_all.click()
        p = self._proc()
        root = str(Path(self.dl.get_logs_root()).resolve())
        self.assertEqual(p.arguments, ["-m", "analysis", root])
        self.assertIn("[ANALYSIS] starting all shots:", self._gui_log())

    def test_open_analysis_folder_creates_processed_shots_and_opens_it(self):
        with patch("gui.analysis_window.open_with_system") as opened:
            self.win.btn_open_analysis.click()
        folder = Path(self.dl.get_logs_root()).resolve() / "processed_shots"
        self.assertTrue(folder.is_dir())
        self.assertEqual(opened.call_args.args[0], folder)

    # ------------------------------------------------------------ close
    def test_close_kills_a_run_that_does_not_finish_in_time_and_logs_it(self):
        self._fire()
        self._complete_export()
        p = self._proc()
        self._fire()
        self._complete_export()                     # queued behind it
        self.win.close()
        self.assertTrue(p.killed)
        log = self._gui_log()
        self.assertIn("[ANALYSIS] killed after 15 s at close: shot 1", log)
        self.assertIn("partial file is cleaned up", log)
        self.assertIn("[ANALYSIS] 1 queued run(s) dropped at close: shot 2", log)
        types = [(r["event_type"], r["source"]) for r in read_rows(self.dl.get_log_file_path())]
        self.assertIn(("ERROR", "Analysis"), types)
        self.assertLess(types.index(("ERROR", "Analysis")), types.index(("SESSION_END", "SYSTEM")),
                        "the kill is logged before SESSION_END")

    def test_close_lets_a_run_finish_within_the_wait(self):
        self._fire()
        self._complete_export()
        p = self._proc()
        p.finish_on_wait = True
        self.win.close()
        self.assertFalse(p.killed)
        self.assertIn("[ANALYSIS] finished during close: shot 1", self._gui_log())
        self.assertNotIn("killed", self._gui_log())

    def test_close_order_is_save_analysis_session_end_logger_close_report(self):
        order = []
        self.win.captured_scopes = {1: "d"}
        self.win._captures_dirty = True
        self.win._save_captures_sync = lambda: (order.append("save"), ([], []))[1]
        self.win._shutdown_analysis = lambda *a, **k: order.append("analysis")
        self.win.data_logger.log_session_end = lambda *a, **k: order.append("session_end")
        self.win.data_logger.close = lambda: order.append("logger_close")
        self.win._build_session_report = lambda reason=None: order.append("report")
        self.win.close()
        self.assertEqual(order, ["save", "analysis", "session_end", "logger_close", "report"])

    def test_nothing_runs_while_idle_at_close(self):
        self.win.close()
        self.assertNotIn("[ANALYSIS]", self._gui_log())

    def test_analysis_starts_only_when_the_last_of_three_exports_lands(self):
        self._fire()
        self.win.export_workers = []
        self.win.captured_scopes = {1: "d", 2: "d", 3: "d"}
        self.win._export_scope_ids = {1, 2, 3}
        self.win._export_pending = 3
        self.win._export_done_paths = []
        self.win._export_failed = {}
        self.win._export_skipped = set()
        self.win._export_silent = True
        for sid in (1, 2):
            self.win._on_one_export_finished(str(self.tmp / f"rigol{sid}_x.csv"))
            self.assertEqual(FakeQProcess.instances, [], f"file {sid} of 3 is not the last")
        self.win._on_one_export_finished(str(self.tmp / "rigol3_x.csv"))
        self.assertEqual(len(FakeQProcess.instances), 1)

    def test_zero_sample_scope_neither_blocks_the_analysis_nor_loops_the_export(self):
        """A scope with no samples is logged FAILED and skipped. It used to
        count as a capture that landed mid-export: the auto-save re-armed
        every 2 s for ever and the analysis never started."""
        from PyQt6.QtWidgets import QApplication
        self._fire()
        good = ((np.arange(4.0), np.zeros(4)),) * 4
        empty = ((np.array([]), np.array([])),) * 4
        self.win.captured_scopes = {1: good, 2: good, 3: empty}
        self.win._captures_dirty = True
        self.win.auto_save_delay_sec = 2.0
        self.win._start_async_export(silent=True)
        for w in list(self.win.export_workers):
            self.assertTrue(w.wait(5000))
        QApplication.processEvents()                # the workers' finished signals
        self.assertEqual(self.win._export_pending, 0)
        self.assertFalse(self.win._captures_dirty, "nothing left to write")
        self.assertFalse(self.win._auto_save_timer.isActive(), "no re-export loop")
        self.assertNotIn("saving again", self._gui_log())
        self.assertEqual(len(FakeQProcess.instances), 1, "the shot is analysed")
        failed = [r for r in read_rows(self.dl.get_log_file_path())
                  if r["event_type"] == "SCOPE_EXPORT" and r["notes"].startswith("FAILED")]
        self.assertEqual([r["source"] for r in failed], ["Rigol3"])

    def test_close_closes_the_plot_window_and_opens_none_during_the_wait(self):
        a_png = png(self.tmp / "shot_0001_analysis.png")
        self._fire()
        self._complete_export()
        p = self._proc()
        p.feed_stdout("[ANALYSIS] result " + json.dumps(dict(RESULT, analysis_png=a_png)) + "\n")
        p.finish(0)
        w = self.win.analysis_window
        self.assertTrue(w.isVisible())
        # A second run ends inside the close wait with a figure of its own.
        self._fire()
        self._complete_export()
        p2 = self._proc()
        p2.feed_stdout("[ANALYSIS] result " + json.dumps(dict(RESULT, shot_number=2, analysis_png=a_png)) + "\n")
        p2.finish_on_wait = True
        shown = []
        self.win._show_analysis_plot = lambda png_, r: shown.append(png_)
        self.win.close()
        self.assertEqual(shown, [], "no figure window may open during the close")
        self.assertFalse(w.isVisible(), "the figure window closes with the main window")
        self.assertIn("[ANALYSIS] finished during close: shot 2", self._gui_log())

    def test_pending_finish_at_close_does_not_start_the_queued_run(self):
        """The run in flight has already exited when close begins, but its
        finished() is still pending. Pumping events at close must not start
        the queued run, which would then be waited on for 15 s and killed."""
        from PyQt6.QtWidgets import QApplication
        self._fire()
        self._complete_export()
        first = self._proc()
        self.win.btn_analyze_all.click()             # queued behind shot 1
        self.assertEqual(self.win.analysis.pending(), 1)
        with patch.object(QApplication, "processEvents",
                          staticmethod(lambda *a, **k: first.finish(0))):
            self.win.close()
        self.assertEqual(len(FakeQProcess.instances), 1, "'all shots' must not start at close")
        log = self._gui_log()
        self.assertIn("[ANALYSIS] finished during close: shot 1", log)
        self.assertIn("[ANALYSIS] 1 queued run(s) dropped at close: all shots", log)
        self.assertNotIn("killed", log)

    def test_kill_wording_for_an_all_shots_run(self):
        self.win.btn_analyze_all.click()
        self.win.close()
        log = self._gui_log()
        self.assertIn("[ANALYSIS] killed after 15 s at close: all shots. Shots it had "
                      "finished are kept", log)
        self.assertIn("partial file is cleaned up", log)

    def test_close_save_says_the_shot_is_not_analysed(self):
        self._fire()
        good = ((np.arange(4.0), np.zeros(4)),) * 4
        self.win.captured_scopes = {1: good}
        self.win._captures_dirty = True
        self.win.close()                             # the close-save writes the file
        log = self._gui_log()
        self.assertIn("[AUTO-SAVE] Saved on close", log)
        self.assertIn("[ANALYSIS] shot 1 was saved on close and is not analysed now", log)
        self.assertEqual(FakeQProcess.instances, [])


class TestRunnerAlone(GuiWindowTestCase):
    """The runner's own edge cases, driven without a shot."""

    def test_not_started_is_reported_and_the_queue_moves_on(self):
        from PyQt6.QtCore import QProcess
        from utils.analysis_runner import AnalysisRun
        lines = []
        self.win.analysis.line.connect(lines.append)
        self.win.analysis.enqueue(AnalysisRun("one", ["--x"]))
        self.win.analysis.enqueue(AnalysisRun("two", ["--y"]))
        p = FakeQProcess.instances[-1]
        p.errorOccurred.emit(QProcess.ProcessError.FailedToStart)
        self.assertTrue(any("could not start one" in l for l in lines))
        self.assertEqual(FakeQProcess.instances[-1].arguments, ["-m", "analysis", "--y"])

    def test_invalid_result_json_is_logged_and_makes_no_event(self):
        from utils.analysis_runner import AnalysisRun
        self.win.analysis.enqueue(AnalysisRun("one", ["--x"]))
        FakeQProcess.instances[-1].feed_stdout("[ANALYSIS] result {not json\n")
        self.assertIn("not valid JSON", self.dl.gui_log_file.read_text(encoding="utf-8"))
        self.assertEqual([r for r in read_rows(self.dl.get_log_file_path())
                          if r["event_type"] == "ANALYSIS"], [])
