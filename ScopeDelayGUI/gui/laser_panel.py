"""
CFR Laser control panel for the main PyQt6 GUI.

Minimal but complete safety workflow ported from the standalone Tkinter
gui/cfr_laser_gui.py:

  INT/INT - laser fires from this panel's SINGLE SHOT button (OP command).
            For alignment / energy checks.
  EXT/EXT - a DG535 (or other delay generator) drives Lamp In + Q-Switch In;
            the laser stays armed and fires on each external pulse pair.

The panel is self-contained: it owns a CFRLaserController, runs the long prep /
fire sequences on daemon threads, and marshals all UI updates back to the GUI
thread through Qt signals. Optional callbacks let the main window share its log
and persist the COM port:

    LaserPanel(log_func=main.log, save_func=save_memory)
"""

import threading
import time

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton,
    QLabel, QLineEdit, QRadioButton, QButtonGroup, QPlainTextEdit, QMessageBox,
)

from instruments.cfr_laser import CFRLaserController, parse_interlock_response, IQ_BITS
from utils.status_lamp import StatusLamp


class LaserPanel(QGroupBox):
    # Signals so worker threads never touch widgets directly
    sig_log = pyqtSignal(str)
    sig_state = pyqtSignal(str)
    sig_interlock = pyqtSignal(str, str)        # text, color
    sig_lamp = pyqtSignal(str, str)             # color, text
    sig_fire_btn = pyqtSignal(bool, str)        # enabled, label

    def __init__(self, log_func=None, save_func=None, default_port="COM16",
                 title="CFR Laser Control", save_key="CFR_LASER_COM",
                 log_tag="Laser"):
        super().__init__(title)
        self._external_log = log_func
        self._save_func = save_func
        self._save_key = save_key
        self._log_tag = log_tag

        self.laser = CFRLaserController()
        self.prep_thread = None
        self.prep_cancel = threading.Event()

        self._build_ui(default_port)

        self.sig_log.connect(self._append_log)
        self.sig_state.connect(self.state_label.setText)
        self.sig_interlock.connect(self._set_interlock)
        self.sig_lamp.connect(self.lamp.set_status)
        self.sig_fire_btn.connect(self._set_fire_btn)

    # ==================================================================
    # UI
    # ==================================================================
    def _build_ui(self, default_port):
        root = QVBoxLayout()
        self.setLayout(root)

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
        self.rb_int.setChecked(True)
        self.mode_group.addButton(self.rb_int)
        self.mode_group.addButton(self.rb_ext)
        self.rb_int.toggled.connect(self._on_mode_change)
        mode_row.addWidget(self.rb_int)
        mode_row.addWidget(self.rb_ext)
        mode_row.addStretch()
        root.addLayout(mode_row)

        # --- Prep / Stop ---
        prep_row = QHBoxLayout()
        self.btn_prep = QPushButton("Prep System")
        self.btn_stop = QPushButton("Stop (safe shutdown)")
        self.btn_prep.clicked.connect(self.on_prep)
        self.btn_stop.clicked.connect(self.on_stop)
        prep_row.addWidget(self.btn_prep)
        prep_row.addWidget(self.btn_stop)
        root.addLayout(prep_row)

        # --- Fire ---
        self.btn_fire = QPushButton("SINGLE SHOT (OP)")
        self.btn_fire.setEnabled(False)
        self.btn_fire.setStyleSheet(
            "background-color:#c0392b;color:white;font-weight:bold;padding:8px;")
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
        self.log_view.setMaximumHeight(110)
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
        label = "SINGLE SHOT (OP)" if self.rb_int.isChecked() else "Verify ARMED"
        self.btn_fire.setText(label)
        self.btn_fire.setEnabled(False)
        self.sig_state.emit("Idle (mode changed, re-run Prep)")

    def _mode(self):
        return "INT/INT" if self.rb_int.isChecked() else "EXT/EXT"

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

    # ==================================================================
    # Prep sequence (threaded, with 8 s IQ poll)
    # ==================================================================
    def on_prep(self):
        if not self.laser.is_open:
            QMessageBox.critical(self, "Not connected", "Connect to the laser first.")
            return
        if self.prep_thread and self.prep_thread.is_alive():
            QMessageBox.information(self, "Busy", "Prep already running.")
            return
        self.prep_cancel.clear()
        self.sig_fire_btn.emit(False, self.btn_fire.text())
        self.prep_thread = threading.Thread(target=self._prep_worker, daemon=True)
        self.prep_thread.start()

    def _prep_worker(self):
        try:
            mode = self._mode()
            self.sig_log.emit(f"--- PREP SEQUENCE START ({mode}) ---")
            self.sig_state.emit(f"Prep starting ({mode})...")

            # 1. Interlock pre-check
            self.sig_state.emit("Checking interlocks...")
            wor = self.laser.send_cmd("WOR")
            if not wor:
                self.sig_state.emit("Prep ABORTED (no WOR response)")
                return
            if self.laser._extract_wor_field(wor, "I") == "1":
                self.sig_log.emit("WOR shows interlocks present - aborting prep.")
                self.sig_state.emit("Prep ABORTED (interlocks present)")
                return
            if self.prep_cancel.is_set():
                self.sig_state.emit("Prep cancelled")
                return

            # 2. Mode-specific sync setup
            if mode == "INT/INT":
                self.sig_state.emit("Setting Q-Switch INT (QI)...")
                self.laser.send_cmd("QI")
                self.sig_state.emit("Starting flashlamp INT (A)...")
                if not self.laser.send_cmd("A"):
                    self.sig_state.emit("Prep ABORTED (A command failed)")
                    return
            else:  # EXT/EXT
                self.sig_state.emit("Setting Q-Switch EXT (QE)...")
                self.laser.send_cmd("QE")
                # BYPASS1 before flashlamp Stop->Fire: 0.5 us lamp delay vs 500 us
                self.sig_state.emit("Setting BYPASS1 (0.5 us lamp delay)...")
                self.laser.send_cmd("BYPASS1")
                self.sig_state.emit("Starting flashlamp EXT (E)...")
                if not self.laser.send_cmd("E"):
                    self.sig_state.emit("Prep ABORTED (E command failed)")
                    return

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
                    return
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
                        return
                    if not delay_active:
                        cleared = True
                        break
                time.sleep(0.4)

            if not cleared:
                self.sig_state.emit("Prep ABORTED (timeout waiting for safety delay)")
                return

            # 5. Mode-specific finish
            if mode == "INT/INT":
                st = self.laser.send_cmd("ST")
                self.sig_log.emit(f"Final state string: {st!r}")
                self.sig_state.emit("READY TO FIRE")
                self.sig_fire_btn.emit(True, "SINGLE SHOT (OP)")
                self.sig_log.emit("--- PREP COMPLETE (INT/INT) --- click SINGLE SHOT.")
            else:  # EXT/EXT
                self.sig_state.emit("Arming Q-switch (CC)...")
                self.laser.send_cmd("CC")
                st = self.laser.send_cmd("ST")
                self.sig_log.emit(f"Final state string: {st!r}")
                if st and "ext" in st.lower() and "qs" in st.lower():
                    self.sig_state.emit("ARMED - waiting for DG535 trigger")
                    self.sig_fire_btn.emit(True, "Verify ARMED")
                    self.sig_log.emit("--- PREP COMPLETE (EXT/EXT) --- DG535 fires each shot.")
                else:
                    self.sig_state.emit(f"Prep WARNING: state unexpected: {st}")
        except Exception as e:
            self.sig_log.emit(f"PREP EXCEPTION: {e}")
            self.sig_state.emit(f"Prep error: {e}")

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
            threading.Thread(target=self._fire_ext_status_worker, daemon=True).start()

    def _fire_int_worker(self):
        resp = self.laser.send_cmd("OP")
        self.sig_log.emit(f"FIRE (OP) sent. Response: {resp!r}")
        self.sig_state.emit("SHOT FIRED - re-prep for another shot")

    def _fire_ext_status_worker(self):
        st = self.laser.send_cmd("ST")
        wor = self.laser.send_cmd("WOR")
        self.sig_log.emit(f"Status check: ST={st!r}  WOR={wor!r}")
        if st and "ext" in st.lower() and "qs" in st.lower():
            self.sig_state.emit("ARMED - DG535 controls firing")
        else:
            self.sig_state.emit(f"NOT ARMED: {st}")

    # ==================================================================
    # Stop
    # ==================================================================
    def on_stop(self):
        self.prep_cancel.set()
        threading.Thread(target=self._stop_worker, daemon=True).start()

    def _stop_worker(self):
        self.sig_log.emit("--- SAFE STOP ---")
        self.laser.send_cmd("CS")    # stop Q-switch
        self.laser.send_cmd("S")     # stop flashlamp
        self.laser.send_cmd("SHC0")  # close shutter
        self.sig_state.emit("Stopped")
        self.sig_fire_btn.emit(False, self.btn_fire.text())

    def shutdown(self):
        """Called on app close."""
        self.prep_cancel.set()
        try:
            self.laser.close()
        except Exception:
            pass
