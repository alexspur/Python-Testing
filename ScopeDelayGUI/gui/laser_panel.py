"""
CFR laser control for the main PyQt6 GUI.

Both lasers live in one panel, one column each:

  INT/INT - laser fires from its own SINGLE SHOT button (OP command).
            For alignment / energy checks.
  EXT/EXT - a DG535 drives Lamp In + Q-Switch In; the laser stays armed and
            fires on each external pulse pair. This is the default, because
            it is how the lasers run during a shot.

One Prep System button preps both lasers, each on its own thread, and one
Stop Both shuts both down. A laser that fails prep does not stop the other:
each column reports its own result.

Each column owns a CFRLaserController, runs the long prep / fire sequences on
daemon threads, and marshals all UI updates back to the GUI thread through Qt
signals. Optional callbacks let the main window share its log and persist the
COM port.
"""

import threading
import time

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QGroupBox, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QRadioButton, QButtonGroup, QPlainTextEdit, QMessageBox,
)

from instruments.cfr_laser import CFRLaserController, parse_interlock_response, IQ_BITS
from utils.accent_button import accent_button, PREP_BLUE
from utils.status_lamp import StatusLamp


class LaserColumn(QWidget):
    """One CFR laser: its own serial controller, threads and widgets."""

    # Signals so worker threads never touch widgets directly
    sig_log = pyqtSignal(str)
    sig_state = pyqtSignal(str)
    sig_interlock = pyqtSignal(str, str)        # text, color
    sig_lamp = pyqtSignal(str, str)             # color, text
    sig_fire_btn = pyqtSignal(bool, str)          # enabled, label
    sig_prep_done = pyqtSignal(str, bool, str)    # log_tag, ok, detail
    sig_verify_done = pyqtSignal(str, bool, str)  # log_tag, armed, detail

    def __init__(self, log_func=None, save_func=None, default_port="COM16",
                 title="CFR Laser", save_key="CFR_LASER_COM",
                 log_tag="Laser", event_func=None, parent=None):
        super().__init__(parent)
        self._external_log = log_func
        # Called on arm / disarm / fire / interlock / error so the main window
        # can persist laser state. Runs on this column's worker threads, so the
        # handler must not touch widgets.
        self._event = event_func
        self._save_func = save_func
        self._save_key = save_key
        self._log_tag = log_tag
        self.title = title

        self.laser = CFRLaserController()
        self.prep_thread = None
        self.prep_cancel = threading.Event()

        self._build_ui(title, default_port)

        self.sig_log.connect(self._append_log)
        self.sig_state.connect(self.state_label.setText)
        self.sig_interlock.connect(self._set_interlock)
        self.sig_lamp.connect(self.lamp.set_status)
        self.sig_fire_btn.connect(self._set_fire_btn)

    # ==================================================================
    # UI
    # ==================================================================
    def _build_ui(self, title, default_port):
        root = QVBoxLayout()
        root.setContentsMargins(4, 4, 4, 4)
        self.setLayout(root)

        heading = QLabel(f"<b>{title}</b>")
        root.addWidget(heading)

        # --- Connection row ---
        conn = QHBoxLayout()
        self.lamp = StatusLamp(size=14)
        conn.addWidget(self.lamp)
        conn.addWidget(QLabel("Port:"))
        self.port_edit = QLineEdit(default_port)
        self.port_edit.setMaximumWidth(90)
        conn.addWidget(self.port_edit)
        self.btn_connect = QPushButton("Connect")
        self.btn_disconnect = QPushButton("Disconnect")
        self.btn_connect.clicked.connect(self.on_connect)
        self.btn_disconnect.clicked.connect(self.on_disconnect)
        conn.addWidget(self.btn_connect)
        conn.addWidget(self.btn_disconnect)
        conn.addStretch()
        root.addLayout(conn)

        # --- Interlocks ---
        self.btn_check = QPushButton("Check Interlocks")
        self.btn_check.clicked.connect(self.on_check_interlocks)
        root.addWidget(self.btn_check)
        self.interlock_label = QLabel("(not checked)")
        self.interlock_label.setWordWrap(True)
        self.interlock_label.setStyleSheet("color: #444;")
        root.addWidget(self.interlock_label)

        # --- Trigger mode ---
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("<b>Trigger:</b>"))
        self.mode_group = QButtonGroup(self)
        self.rb_int = QRadioButton("INT/INT (fire here)")
        self.rb_ext = QRadioButton("EXT/EXT (DG535 fires)")
        # EXT/EXT is how the lasers run during a shot, so it is the default.
        self.rb_ext.setChecked(True)
        self.mode_group.addButton(self.rb_int)
        self.mode_group.addButton(self.rb_ext)
        self.rb_int.toggled.connect(self._on_mode_change)
        mode_row.addWidget(self.rb_int)
        mode_row.addWidget(self.rb_ext)
        mode_row.addStretch()
        root.addLayout(mode_row)

        # --- Fire (INT/INT only) ---
        # In EXT/EXT the laser fires from the DG535 and is checked with the
        # panel's shared Verify ARMED, so this button is hidden there.
        self.btn_fire = QPushButton("SINGLE SHOT (OP)")
        self.btn_fire.setEnabled(False)
        self.btn_fire.setVisible(False)
        self.btn_fire.setStyleSheet(
            "background-color:#c0392b;color:white;font-weight:bold;padding:6px;")
        self.btn_fire.clicked.connect(self.on_fire)
        root.addWidget(self.btn_fire)

        # --- State + log ---
        st_row = QHBoxLayout()
        st_row.addWidget(QLabel("State:"))
        self.state_label = QLabel("Idle")
        self.state_label.setStyleSheet("font-weight:bold;")
        st_row.addWidget(self.state_label)
        st_row.addStretch()
        root.addLayout(st_row)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(70)
        self.log_view.setStyleSheet("font-family:Consolas,monospace;font-size:11px;")
        root.addWidget(self.log_view)

    # ==================================================================
    # Slots (GUI thread)
    # ==================================================================
    def _append_log(self, msg):
        self.log_view.appendPlainText(f"[{time.strftime('%H:%M:%S')}] {msg}")
        if self._external_log:
            self._external_log(f"[{self._log_tag}] {msg}")

    def _set_interlock(self, text, color):
        self.interlock_label.setText(text)
        self.interlock_label.setStyleSheet(f"color:{color};")

    def _set_fire_btn(self, enabled, label):
        self.btn_fire.setEnabled(enabled)
        self.btn_fire.setText(label)

    def _on_mode_change(self):
        # Only INT/INT fires from this panel. EXT/EXT is checked with the
        # shared Verify ARMED button instead.
        int_mode = self.rb_int.isChecked()
        self.btn_fire.setText("SINGLE SHOT (OP)")
        self.btn_fire.setVisible(int_mode)
        self.btn_fire.setEnabled(False)
        self.sig_state.emit("Idle (mode changed, re-run Prep)")

    def _mode(self):
        return "INT/INT" if self.rb_int.isChecked() else "EXT/EXT"

    def _emit_event(self, event, **payload):
        """Hand a laser event to the main window (logging + state cache)."""
        if self._event is None:
            return
        payload.setdefault("mode", self._mode())
        try:
            self._event(self._log_tag, event, payload)
        except Exception:
            pass

    def is_armed(self):
        """True only when this laser is in EXT/EXT mode AND reports an ARMED
        state (i.e. prep completed and the Q-switch is armed for external
        firing). Used by the main window's pre-fire interlock checklist."""
        return (self.laser.is_open
                and self.rb_ext.isChecked()
                and self.state_label.text().strip().upper().startswith("ARMED"))

    # ==================================================================
    # Connection
    # ==================================================================
    def on_connect(self):
        port = self.port_edit.text().strip()
        if not port:
            QMessageBox.information(self, "No port", "Enter the laser COM port.")
            return
        self.connect_to(port)

    def connect_to(self, port):
        """Connect (also used by the main window for auto-connect). Returns bool."""
        if self.laser.is_open:
            return True
        try:
            self.laser.connect(port)
            self.sig_lamp.emit("green", f"Connected ({port})")
            self.sig_log.emit(f"CONNECTED on {port} @ 9600 8N1")
            if self._save_func:
                try:
                    self._save_func(self._save_key, port)
                except Exception:
                    pass
            return True
        except Exception as e:
            self.sig_lamp.emit("red", "Not Connected")
            self.sig_log.emit(f"CONNECT FAILED: {e}")
            return False

    def on_disconnect(self):
        self.prep_cancel.set()
        try:
            self.laser.close()
            self.sig_log.emit("DISCONNECTED")
        except Exception as e:
            self.sig_log.emit(f"Disconnect error: {e}")
        self.sig_lamp.emit("red", "Disconnected")
        self.sig_state.emit("Idle")
        self.sig_fire_btn.emit(False, self.btn_fire.text())
        self._emit_event("DISARM", armed=False, state="Disconnected")

    # ==================================================================
    # Interlocks
    # ==================================================================
    def on_check_interlocks(self):
        if not self.laser.is_open:
            self.sig_interlock.emit("Not connected", "red")
            return
        threading.Thread(target=self._check_worker, daemon=True).start()

    def _check_worker(self):
        self.sig_log.emit("--- Interlock check ---")
        clear, summary, color = self.laser.check_interlocks()
        self.sig_interlock.emit(summary, color)
        self.sig_log.emit(summary.replace("\n  ", " | "))
        self._emit_event("INTERLOCK", interlock_ok=bool(clear),
                         detail=summary.replace("\n", " | "))

    # ==================================================================
    # Prep sequence (threaded, with 8 s IQ poll)
    # ==================================================================
    def start_prep(self):
        """Begin the prep sequence. Returns False if it could not start.

        Used by the panel's shared Prep System button. A column that cannot
        start reports through sig_prep_done like any other failure, so one
        laser being unavailable never holds up the other.
        """
        if not self.laser.is_open:
            self.sig_prep_done.emit(self._log_tag, False, "not connected")
            return False
        if self.prep_thread and self.prep_thread.is_alive():
            self.sig_prep_done.emit(self._log_tag, False, "prep already running")
            return False
        self.prep_cancel.clear()
        self.sig_fire_btn.emit(False, self.btn_fire.text())
        self.prep_thread = threading.Thread(target=self._prep_worker, daemon=True)
        self.prep_thread.start()
        return True

    def _prep_worker(self):
        ok, detail = False, "prep did not complete"
        try:
            ok, detail = self._run_prep()
        except Exception as e:
            self.sig_log.emit(f"PREP EXCEPTION: {e}")
            self.sig_state.emit(f"Prep error: {e}")
            self._emit_event("ERROR", fault=True, state="Prep error", detail=str(e))
            ok, detail = False, str(e)
        finally:
            self.sig_prep_done.emit(self._log_tag, ok, detail)

    def _run_prep(self):
        """The prep sequence itself. Returns (ok, detail).

        The command order here is the laser's documented start-up sequence.
        Do not reorder it.
        """
        mode = self._mode()
        self.sig_log.emit(f"--- PREP SEQUENCE START ({mode}) ---")
        self.sig_state.emit(f"Prep starting ({mode})...")

        # 1. Interlock pre-check
        self.sig_state.emit("Checking interlocks...")
        wor = self.laser.send_cmd("WOR")
        if not wor:
            self.sig_state.emit("Prep ABORTED (no WOR response)")
            return False, "no WOR response"
        if self.laser._extract_wor_field(wor, "I") == "1":
            self.sig_log.emit("WOR shows interlocks present - aborting prep.")
            self.sig_state.emit("Prep ABORTED (interlocks present)")
            return False, "interlocks present"
        if self.prep_cancel.is_set():
            self.sig_state.emit("Prep cancelled")
            return False, "cancelled"

        # 2. Mode-specific sync setup
        if mode == "INT/INT":
            self.sig_state.emit("Setting Q-Switch INT (QI)...")
            self.laser.send_cmd("QI")
            self.sig_state.emit("Starting flashlamp INT (A)...")
            if not self.laser.send_cmd("A"):
                self.sig_state.emit("Prep ABORTED (A command failed)")
                return False, "A command failed"
        else:  # EXT/EXT
            self.sig_state.emit("Setting Q-Switch EXT (QE)...")
            self.laser.send_cmd("QE")
            # BYPASS1 before flashlamp Stop->Fire: 0.5 us lamp delay vs 500 us
            self.sig_state.emit("Setting BYPASS1 (0.5 us lamp delay)...")
            self.laser.send_cmd("BYPASS1")
            self.sig_state.emit("Starting flashlamp EXT (E)...")
            if not self.laser.send_cmd("E"):
                self.sig_state.emit("Prep ABORTED (E command failed)")
                return False, "E command failed"

        # 3. Open shutter
        self.sig_state.emit("Opening shutter (SHC1)...")
        self.laser.send_cmd("SHC1")

        # 4. Poll the 8 s safety delay (IQ bit 'a')
        self.sig_log.emit("Polling IQ for 8-s safety delay clearance...")
        t0 = time.time()
        cleared = False
        while time.time() - t0 < 15.0:
            if self.prep_cancel.is_set():
                self.sig_state.emit("Prep cancelled")
                return False, "cancelled"
            self.sig_state.emit(f"Waiting for safety delay... {time.time()-t0:.1f} s")
            resp = self.laser.send_cmd("IQ")
            if resp:
                faults = parse_interlock_response(resp, IQ_BITS, "IQS")
                delay_active = any("8-second" in f for f in faults)
                critical = [f for f in faults
                            if "8-second" not in f and "(unused)" not in f
                            and "Shutter" not in f]
                if critical:
                    self.sig_state.emit(f"Prep ABORTED (Q-Sw fault: {critical})")
                    self.sig_log.emit(f"Q-Switch interlocks during prep: {critical}")
                    return False, f"Q-switch fault: {critical}"
                if not delay_active:
                    cleared = True
                    break
            time.sleep(0.4)

        if not cleared:
            self.sig_state.emit("Prep ABORTED (timeout waiting for safety delay)")
            return False, "timeout waiting for safety delay"

        # 5. Mode-specific finish
        if mode == "INT/INT":
            st = self.laser.send_cmd("ST")
            self.sig_log.emit(f"Final state string: {st!r}")
            self.sig_state.emit("READY TO FIRE")
            self.sig_fire_btn.emit(True, "SINGLE SHOT (OP)")
            self._emit_event("ARM", armed=False, state="READY TO FIRE",
                             fault=False, detail="INT/INT prep complete")
            self.sig_log.emit("--- PREP COMPLETE (INT/INT) --- click SINGLE SHOT.")
            return True, "READY TO FIRE"

        # EXT/EXT
        self.sig_state.emit("Arming Q-switch (CC)...")
        self.laser.send_cmd("CC")
        st = self.laser.send_cmd("ST")
        self.sig_log.emit(f"Final state string: {st!r}")
        if st and "ext" in st.lower() and "qs" in st.lower():
            self.sig_state.emit("ARMED - waiting for DG535 trigger")
            self.sig_fire_btn.emit(True, "Verify ARMED")
            self._emit_event("ARM", armed=True, state="ARMED",
                             fault=False, detail="EXT/EXT prep complete")
            self.sig_log.emit("--- PREP COMPLETE (EXT/EXT) --- DG535 fires each shot.")
            return True, "ARMED"

        self.sig_state.emit(f"Prep WARNING: state unexpected: {st}")
        return False, f"unexpected state: {st}"

    # ==================================================================
    # Fire / status
    # ==================================================================
    def on_fire(self):
        if self._mode() == "INT/INT":
            if self.state_label.text() != "READY TO FIRE":
                QMessageBox.warning(self, "Not ready", "Run Prep System first.")
                return
            ok = QMessageBox.question(
                self, "Confirm fire",
                "Eyewear on? Beam path clear? Interlocks closed?\n\nFire single shot now?")
            if ok != QMessageBox.StandardButton.Yes:
                return
            self.sig_state.emit("FIRING (OP)")
            self.sig_fire_btn.emit(False, "SINGLE SHOT (OP)")
            threading.Thread(target=self._fire_int_worker, daemon=True).start()
        else:
            self.start_verify()

    def _fire_int_worker(self):
        resp = self.laser.send_cmd("OP")
        self.sig_log.emit(f"FIRE (OP) sent. Response: {resp!r}")
        self.sig_state.emit("SHOT FIRED - re-prep for another shot")
        self._emit_event("FIRE", state="SHOT FIRED", detail=f"OP response {resp!r}")

    def start_verify(self):
        """Check whether this laser is armed for external firing.

        Read-only: ST and WOR are queries. Reports through sig_verify_done so
        the panel can show both lasers' answers side by side. Returns False if
        it could not even be attempted.
        """
        if not self.laser.is_open:
            self.sig_verify_done.emit(self._log_tag, False, "not connected")
            return False
        threading.Thread(target=self._fire_ext_status_worker, daemon=True).start()
        return True

    def _fire_ext_status_worker(self):
        armed, detail = False, "no response"
        try:
            st = self.laser.send_cmd("ST")
            wor = self.laser.send_cmd("WOR")
            self.sig_log.emit(f"Status check: ST={st!r}  WOR={wor!r}")
            if st and "ext" in st.lower() and "qs" in st.lower():
                self.sig_state.emit("ARMED - DG535 controls firing")
                self._emit_event("ARM", armed=True, state="ARMED", detail=f"ST={st!r}")
                armed, detail = True, "ARMED"
            else:
                self.sig_state.emit(f"NOT ARMED: {st}")
                self._emit_event("DISARM", armed=False, state=f"NOT ARMED: {st}",
                                 detail=f"ST={st!r}")
                armed, detail = False, f"NOT ARMED: {st}"
        except Exception as e:
            self.sig_log.emit(f"VERIFY EXCEPTION: {e}")
            armed, detail = False, str(e)
        finally:
            self.sig_verify_done.emit(self._log_tag, armed, detail)

    # ==================================================================
    # Stop
    # ==================================================================
    def start_stop(self):
        """Safe shutdown, on its own thread. Used by the shared Stop Both."""
        self.prep_cancel.set()
        threading.Thread(target=self._stop_worker, daemon=True).start()

    def _stop_worker(self):
        self.sig_log.emit("--- SAFE STOP ---")
        self.laser.send_cmd("CS")    # stop Q-switch
        self.laser.send_cmd("S")     # stop flashlamp
        self.laser.send_cmd("SHC0")  # close shutter
        self.sig_state.emit("Stopped")
        self.sig_fire_btn.emit(False, self.btn_fire.text())
        self._emit_event("DISARM", armed=False, state="Stopped",
                         detail="safe stop: CS, S, SHC0")

    def shutdown(self):
        """Called on app close."""
        self.prep_cancel.set()
        try:
            self.laser.close()
        except Exception:
            pass


class DualLaserPanel(QGroupBox):
    """Both CFR lasers, one column each, with shared Prep and Stop."""

    def __init__(self, log_func=None, save_func=None, event_func=None,
                 laser1_port="COM6", laser2_port="COM8"):
        super().__init__("CFR Lasers")

        root = QVBoxLayout()
        self.setLayout(root)

        # The log tags are what the data logger and the shot row key off:
        # Laser1 -> laser1_* columns, Laser2 -> laser2_*.
        self.laser1 = LaserColumn(
            log_func=log_func, save_func=save_func, default_port=laser1_port,
            title="CFR Laser 1", save_key="CFR_LASER_COM", log_tag="Laser1",
            event_func=event_func)
        self.laser2 = LaserColumn(
            log_func=log_func, save_func=save_func, default_port=laser2_port,
            title="CFR Laser 2", save_key="CFR_LASER2_COM", log_tag="Laser2",
            event_func=event_func)
        self.lasers = [self.laser1, self.laser2]

        columns = QHBoxLayout()
        columns.addWidget(self.laser1)
        columns.addWidget(self.laser2)
        root.addLayout(columns)

        # --- Shared Prep / Verify / Stop ---
        action_row = QHBoxLayout()
        self.btn_prep = QPushButton("Prep System")
        accent_button(self.btn_prep, PREP_BLUE,
                      "Prep both lasers. One failing does not stop the other.")
        self.btn_verify = QPushButton("Verify ARMED")
        self.btn_verify.setToolTip(
            "Ask both lasers whether they are armed for external firing. "
            "Read-only: ST and WOR are queries.")
        self.btn_stop = QPushButton("Stop Both")
        self.btn_stop.setToolTip("Safe shutdown of both lasers: CS, S, SHC0.")
        self.btn_prep.clicked.connect(self.on_prep_both)
        self.btn_verify.clicked.connect(self.on_verify_both)
        self.btn_stop.clicked.connect(self.on_stop_both)
        action_row.addWidget(self.btn_prep)
        action_row.addWidget(self.btn_verify)
        action_row.addWidget(self.btn_stop)
        action_row.addStretch()
        root.addLayout(action_row)

        # One line reports whichever action ran last, per laser.
        self.result_label = QLabel("Prep: not run")
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet("color:#444;")
        root.addWidget(self.result_label)
        # Kept under its old name for callers that report prep results.
        self.prep_result_label = self.result_label

        self._prep_results = {}
        self._verify_results = {}
        for col in self.lasers:
            col.sig_prep_done.connect(self._on_prep_done)
            col.sig_verify_done.connect(self._on_verify_done)

    # ------------------------------------------------------------------
    def on_prep_both(self):
        """Prep both lasers. Each runs on its own thread and reports its own
        result, so one laser failing never skips the other."""
        self._prep_results = {}
        self.prep_result_label.setText("Prep: running on both lasers...")
        self.prep_result_label.setStyleSheet("color:#444;")
        for col in self.lasers:
            col.start_prep()

    def on_verify_both(self):
        """Ask both lasers whether they are armed. Read-only on both."""
        self._verify_results = {}
        self.result_label.setText("Verify: checking both lasers...")
        self.result_label.setStyleSheet("color:#444;")
        for col in self.lasers:
            col.start_verify()

    def on_stop_both(self):
        for col in self.lasers:
            col.start_stop()

    def _on_prep_done(self, tag, ok, detail):
        self._prep_results[tag] = (ok, detail)
        self._report("Prep", self._prep_results, "OK", "FAILED", "running...")

    def _on_verify_done(self, tag, armed, detail):
        self._verify_results[tag] = (armed, detail)
        self._report("Verify", self._verify_results, "ARMED", "NOT ARMED", "checking...")

    def _report(self, action, results, ok_word, bad_word, pending):
        """One line showing each laser's own result for the last action."""
        parts = []
        for col in self.lasers:
            result = results.get(col._log_tag)
            if result is None:
                parts.append(f"{col.title}: {pending}")
            else:
                col_ok, col_detail = result
                word = ok_word if col_ok else bad_word
                parts.append(f"{col.title}: {word} ({col_detail})")
        self.result_label.setText(f"{action} — " + "   |   ".join(parts))

        done = [results.get(c._log_tag) for c in self.lasers]
        if all(r is not None for r in done):
            all_ok = all(r[0] for r in done)
            self.result_label.setStyleSheet(
                "color:#2E7D32; font-weight:bold;" if all_ok
                else "color:#C62828; font-weight:bold;")

    def shutdown(self):
        for col in self.lasers:
            col.shutdown()
