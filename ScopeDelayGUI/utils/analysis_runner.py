# utils/analysis_runner.py
"""Run the shot analysis (python -m analysis ...) in a child process.

One run at a time; the rest queue in order. Nothing here blocks the GUI
thread except shutdown(), which closeEvent calls with a bounded wait.

Every stdout line goes to the GUI log as is; the analysis prefixes its own
lines with "[ANALYSIS]". stderr lines are prefixed "[ANALYSIS] stderr:".
Each "[ANALYSIS] result {json}" line is parsed and reported on its own
signal, so the experiment log gets one ANALYSIS event per shot.
"""

import codecs
import json
import sys
from collections import deque

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, pyqtSignal

# Bound here, at import, so a test that replaces QProcess with a fake does
# not take the enums away from the code that compares against them.
CRASH_EXIT = QProcess.ExitStatus.CrashExit
NORMAL_EXIT = QProcess.ExitStatus.NormalExit
FAILED_TO_START = QProcess.ProcessError.FailedToStart

RESULT_PREFIX = "[ANALYSIS] result "
STDERR_PREFIX = "[ANALYSIS] stderr: "


class AnalysisRun:
    """One invocation: a label for the log and the arguments after
    `-m analysis`. Results (parsed result lines) accumulate as it runs."""

    def __init__(self, label, args, shot_number=None):
        self.label = label
        self.args = [str(a) for a in args]
        self.shot_number = shot_number
        self.results = []
        self.exit_code = None

    def command(self):
        return [sys.executable, "-m", "analysis", *self.args]

    def command_text(self):
        return " ".join(f'"{a}"' if " " in a else a for a in self.command())


class AnalysisRunner(QObject):
    """Queue of AnalysisRun, executed one at a time in a QProcess."""

    line = pyqtSignal(str)             # one log line, already prefixed
    result = pyqtSignal(object, dict)  # (run, parsed result line)
    finished = pyqtSignal(object, int)  # (run, exit code; -1 killed/crashed, -2 not started)

    def __init__(self, repo_dir, parent=None):
        super().__init__(parent)
        self.repo_dir = str(repo_dir)
        self._queue = deque()
        self._proc = None
        self._current = None
        self._out = ""
        self._err = ""
        # Incremental decoders: a pipe read can end in the middle of a
        # multi-byte character, which a per-chunk decode would turn into U+FFFD.
        self._dec_out = codecs.getincrementaldecoder("utf-8")("replace")
        self._dec_err = codecs.getincrementaldecoder("utf-8")("replace")
        self._closing = False

    # ------------------------------------------------------------- state
    def is_running(self):
        return self._current is not None

    def current(self):
        return self._current

    def pending(self):
        return len(self._queue)

    # ------------------------------------------------------------ queue
    def enqueue(self, run):
        """Queue a run. Returns how many runs are ahead of it, 0 when it
        starts now, or -1 when refused because the GUI is closing."""
        if self._closing:
            self.line.emit(f"[ANALYSIS] not queued, the GUI is closing: {run.label}")
            return -1
        self._queue.append(run)
        ahead = len(self._queue) - 1 + (1 if self._current is not None else 0)
        if self._current is None:
            self._start_next()
        else:
            self.line.emit(f"[ANALYSIS] queued {run.label} ({ahead} run(s) ahead)")
        return ahead

    def close_queue(self):
        """Refuse new runs and drop the queued ones; the run in flight is
        left alone. Returns the dropped labels. Called at close before any
        events are pumped, so a finished() already pending for the run in
        flight cannot start the next queued run."""
        self._closing = True
        dropped = [r.label for r in self._queue]
        self._queue.clear()
        return dropped

    def _start_next(self):
        if self._current is not None or not self._queue:
            return
        run = self._queue.popleft()
        self._dec_out.reset()
        self._dec_err.reset()
        proc = QProcess(self)
        proc.setWorkingDirectory(self.repo_dir)
        env = QProcessEnvironment.systemEnvironment()
        # The child prints paths and prose; a cp1252 console pipe would
        # mangle them. Agg keeps matplotlib away from any GUI backend.
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONUTF8", "1")
        env.insert("MPLBACKEND", "Agg")
        proc.setProcessEnvironment(env)
        cmd = run.command()
        proc.setProgram(cmd[0])
        proc.setArguments(cmd[1:])
        proc.readyReadStandardOutput.connect(self._on_stdout)
        proc.readyReadStandardError.connect(self._on_stderr)
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(self._on_error)
        self._proc, self._current, self._out, self._err = proc, run, "", ""
        self.line.emit(f"[ANALYSIS] starting {run.label}: {run.command_text()} "
                       f"(cwd {self.repo_dir})")
        proc.start()

    # ----------------------------------------------------------- output
    def _on_stdout(self):
        if self._proc is not None:
            self._out = self._drain(self._out, bytes(self._proc.readAllStandardOutput()), "")

    def _on_stderr(self):
        if self._proc is not None:
            self._err = self._drain(self._err, bytes(self._proc.readAllStandardError()),
                                    STDERR_PREFIX)

    def _drain(self, buf, data, prefix, final=False):
        """Append data to buf, emit every complete line, return the rest.
        A line split across two reads is held until its newline arrives;
        so are the bytes of a character split across two reads."""
        decoder = self._dec_err if prefix else self._dec_out
        buf += decoder.decode(data, final)
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            self._emit_line(line.rstrip("\r"), prefix)
        return buf

    def _emit_line(self, line, prefix):
        if not line.strip():
            return
        self.line.emit(prefix + line)
        if prefix or not line.startswith(RESULT_PREFIX):
            return
        try:
            parsed = json.loads(line[len(RESULT_PREFIX):])
        except ValueError:
            self.line.emit("[ANALYSIS] result line is not valid JSON; no ANALYSIS event")
            return
        if not isinstance(parsed, dict):
            return
        if self._current is not None:
            self._current.results.append(parsed)
        self.result.emit(self._current, parsed)

    # ------------------------------------------------------------- end
    def _on_finished(self, code, status):
        proc, run = self._proc, self._current
        if proc is None or run is None:
            return
        # Whatever arrived after the last readyRead, plus any partial line.
        self._out = self._drain(self._out, bytes(proc.readAllStandardOutput()), "", final=True)
        self._err = self._drain(self._err, bytes(proc.readAllStandardError()), STDERR_PREFIX,
                                final=True)
        for buf, prefix in ((self._out, ""), (self._err, STDERR_PREFIX)):
            if buf.strip():
                self._emit_line(buf.rstrip("\r"), prefix)
        self._out = self._err = ""

        crashed = status == CRASH_EXIT
        run.exit_code = -1 if crashed else int(code)
        self.line.emit(f"[ANALYSIS] {run.label} "
                       + ("ended abnormally (killed or crashed)" if crashed
                          else f"finished, exit code {code}"))
        self._proc, self._current = None, None
        proc.deleteLater()
        self.finished.emit(run, run.exit_code)
        if not self._closing:
            self._start_next()

    def _on_error(self, error):
        if error != FAILED_TO_START or self._current is None:
            return
        proc, run = self._proc, self._current
        detail = proc.errorString() if hasattr(proc, "errorString") else ""
        self.line.emit(f"[ANALYSIS] could not start {run.label}: {detail}")
        run.exit_code = -2
        self._proc, self._current = None, None
        proc.deleteLater()
        self.finished.emit(run, -2)
        if not self._closing:
            self._start_next()

    # ---------------------------------------------------------- close
    def shutdown(self, timeout_ms=15000):
        """At close: drop the queue, give the run in flight up to timeout_ms
        to finish, then kill it. Blocks the caller for at most that long.

        Returns (state, label, dropped): state is 'idle', 'finished' or
        'killed'; label names the run in flight; dropped lists the labels of
        the queued runs that will not happen.
        """
        dropped = self.close_queue()
        if self._current is None:
            return "idle", "", dropped
        proc, label = self._proc, self._current.label
        # finished() is delivered from inside waitForFinished, so
        # _on_finished has normally run by the time it returns; the checks
        # below cover a process object that did not deliver it.
        if proc.waitForFinished(timeout_ms):
            if self._current is not None:
                self._on_finished(proc.exitCode(), NORMAL_EXIT)
            return "finished", label, dropped
        proc.kill()
        proc.waitForFinished(3000)
        if self._current is not None:
            self._on_finished(-1, CRASH_EXIT)
        return "killed", label, dropped
