# gui/main_window.py
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QMessageBox, QPushButton, QSizePolicy, QGridLayout,
    QScrollArea, QFrame, QLabel, QCheckBox,
)
from PyQt6.QtCore import QThread, Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import QFileDialog, QProgressDialog, QMessageBox
from PyQt6.QtCore import Qt
import atexit
import time
from datetime import datetime
from pathlib import Path

from gui.dg535_panel import DG535Panel
from gui.bnc575_panel import BNC575Panel
from gui.rigol_panel import RigolPanel
from gui.sf6_window import SF6Window
from gui.wj_panel import WJPanel
from gui.scope_plot_window import ScopePlotWindow
from gui.numato_relay_panel import NumatoRelayPanel
from gui.laser_panel import LaserPanel

from utils.logger import LogPanel
from utils.status_lamp import StatusLamp
from utils.serial_tools import list_serial_ports
from utils.capture_single_worker import CaptureSingleWorker, CaptureFourChannelWorker
from utils.connect_memory import load_memory, save_memory
from utils.data_logger import DataLogger
from utils.csv_export_worker import CSVExportWorker
from utils.pressure_worker import PressureWorker
from utils.system_state import (
    SystemState, SOURCE_READBACK, SOURCE_COMMANDED, UNKNOWN,
)
from utils.shot_logger import ShotLogger
from utils.shot_snapshot import (
    build_shot_row, channel_name, resolve_absolute_delays,
)

from serial.tools import list_ports

from instruments.dg535 import DG535Controller
from instruments.glassman_id import (
    SUPPLIES as WJ_SUPPLIES,
    matches as wj_matches,
    read_version as wj_read_version,
)
from instruments.bnc575 import BNC575Controller, SystemMode, TriggerMode, TriggerEdge
from instruments.rigol import RigolScope
from instruments.wj import WJPowerSupply
from instruments.numato_relay import NumatoRelayController


class ScopeDelayMainWindow(QMainWindow):
    _relay_update_signal = pyqtSignal(int, bool)  # (channel, state) — safe cross-thread UI update
    _relay_log_signal = pyqtSignal(str)            # log messages from poll thread

    # Which instruments auto_connect_all() will try on startup. Any value is
    # coerced with bool(), so 1/0 and True/False both work. main.py can pass
    # an overriding dict to ScopeDelayMainWindow(auto_connect={...}).
    DEFAULT_AUTO_CONNECT = {
        "dg535":  True,
        "bnc575": True,
        "opta":   True,   # Opta pressure monitor (Modbus TCP)
        "relay":  True,   # Numato relay module
        "wj1":    True,   # negative WJ supply
        "wj2":    True,   # positive WJ supply
        "rigol1": True,
        "rigol2": True,
        "rigol3": True,
        "laser":  True,   # Quantel CFR laser (RS-232 over USB)
    }

    def __init__(self, auto_connect=None, auto_save_delay_sec=10.0,
                 pressure_gauge_min=0.0, pressure_gauge_max=100.0,
                 startup_charge_kv=60.0, opta_host="192.168.10.20",
                 opta_port=502, opta_poll_ms=200):
        super().__init__()

        # Startup "Set Voltage" (kV) preloaded into both supplies' voltage boxes
        # (main WJ panel + SF6 window). HV ON sends this kV to the WJ supplies.
        # Configurable from main.py.
        self.startup_charge_kv = startup_charge_kv

        # Dome pressure gauge range (PSI), configurable from main.py.
        self.pressure_gauge_min = pressure_gauge_min
        self.pressure_gauge_max = pressure_gauge_max

        # Merge any caller overrides over the defaults, coercing to bool so
        # 1/0/"on" style values behave.
        self.auto_connect_flags = dict(self.DEFAULT_AUTO_CONNECT)
        if auto_connect:
            for k, v in auto_connect.items():
                self.auto_connect_flags[k] = bool(v)

        self.setWindowTitle("Scope + Delay + SF6 Control")
        self.setGeometry(100, 100, 1700, 900)
        self.setMinimumSize(800, 600)
        self.conn = load_memory()

        # Initialize data logger
        self.data_logger = DataLogger()

        # One central record of what every device is doing, frozen into a row
        # at each shot, plus the per-shot logger that owns the global shot
        # counter. Both are created before the UI strips so the next shot
        # number can be shown. _deferred_log buffers until log_panel exists.
        self._early_log_buffer = []
        self.system_state = SystemState()
        self.shot_logger = ShotLogger(
            session_dir=self.data_logger.get_session_dir(),
            session_timestamp=self.data_logger.session_timestamp,
            logs_root=self.data_logger.get_logs_root(),
            experiment_log_file=Path(self.data_logger.get_log_file_path()).name,
            log_func=self._deferred_log,
            repo_dir=Path(__file__).resolve().parent.parent,
        )
        self._current_shot_number = None
        atexit.register(self._atexit_cleanup)

        # --- instruments ---
        self.dg = DG535Controller()
        self.bnc = BNC575Controller()
        self.bnc_connected = False
        self.bnc_trigger_armed = False

        # Rigol oscilloscopes (using resource_name parameter for new API)
        self.rigol2 = RigolScope(resource_name="USB0::0x1AB1::0x0514::DS7A230800035::0::INSTR")  # Physical scope 1
        self.rigol3 = RigolScope(resource_name="USB0::0x1AB1::0x0514::DS7A233300256::0::INSTR")  # Physical scope 2
        self.rigol1 = RigolScope(resource_name="USB0::0x1AB1::0x0514::DS7A232900210::0::INSTR")  # Physical scope 3
    
        # Multiple WJ supplies
        self.wj_units = [
            WJPowerSupply(vmax_kv=100.0, imax_ma=6.0),
            WJPowerSupply(vmax_kv=100.0, imax_ma=6.0)
        ]

        # Panel now supports 2 units
        self.wj_panel = WJPanel(num_units=2)
        # Preload the configured startup charge voltage.
        self.wj_panel.voltage.setValue(self.startup_charge_kv)

        self.wj_panel.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed
        )

        self.numato_relay = NumatoRelayController()

        # SF6 dome pressure comes from the Opta over Modbus TCP. All Modbus
        # calls run on PressureWorker's QThread (see _start_pressure_worker).
        self.opta_host = opta_host
        self.opta_port = opta_port
        self.opta_poll_ms = opta_poll_ms
        self.pressure_thread: QThread | None = None
        self.pressure_worker: PressureWorker | None = None
        self._opta_link_up = False
        self._opta_fault = None   # None = no reading yet, "" = sensor in range
        self._latest_psi = None   # last in-range psi; None when not trustworthy

        # Relay polling state
        self.relay_polling = False
        self.relay_poll_thread = None
        self._relay_update_signal.connect(self._relay_pushbutton_ui_update)
        self._relay_log_signal.connect(self.log)

        self.rigol1_connected = False
        self.rigol2_connected = False
        self.rigol3_connected = False

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout()
        central.setLayout(main_layout)

        # Always-visible strip showing each Rigol's capture state.
        self._build_capture_status_strip(main_layout)

        # Pre-fire interlock checklist (auto-monitored, latching).
        self._build_interlock_strip(main_layout)

        # Remove tabs - just use main layout for Scope + Delay controls
        self.build_scope_controls(main_layout)

        # The log panel exists now: flush anything logged during startup.
        for _msg in self._early_log_buffer:
            self.log(_msg)
        self._early_log_buffer.clear()

        # Create SF6 window as separate top-level window (now includes WJ plots)
        self.sf6_window = SF6Window(
            pressure_gauge_min=self.pressure_gauge_min,
            pressure_gauge_max=self.pressure_gauge_max,
        )
        # Keep the SF6 window's voltage box in sync with the configured default.
        self.sf6_window.program_voltage.setValue(self.startup_charge_kv)

        # Populate WJ COM ports (after sf6_window is created so it gets populated too)
        self.refresh_wj_ports()

        # Attempt auto-connect. Run it AFTER the window is shown (deferred via
        # the event loop) instead of inline in __init__. The instrument connects
        # are blocking calls; if one sits on a long serial/VISA timeout it would
        # otherwise stall the constructor so window.show() never runs and the GUI
        # never appears. Deferring lets the window paint first, then connects run.
        QTimer.singleShot(200, self.auto_connect_all)

        # Connect SF6 window controls
        self.connect_sf6_window()

        # Create scope plot window (now with 4-channel support)
        self.scope_window = ScopePlotWindow(parent=self)

        # Start WJ reader threads and connect to SF6 window plot
        self.start_wj_readers()

        # Opta pressure worker thread (idles until auto-connect or Connect)
        self._start_pressure_worker()

        # Position and show all windows on startup
        self.position_and_show_windows()

        # Log the data file location
        self.log(f"[DATA LOGGER] Saving to: {self.data_logger.get_log_file_path()}")

        # Write a test log entry to verify logging is working
        self.data_logger.log_info("SYSTEM", "GUI started successfully")

        # SESSION_START carries the shot number this launch would fire next
        # and the code version that would fire it.
        self.data_logger.log_session_start(
            self.shot_logger.peek_next_shot_number(),
            self.shot_logger.gui_version,
            notes="" if self.shot_logger.counter_available
                  else f"shot counter NOT owned: {self.shot_logger.counter.lock_message}",
        )
        self.log(f"[SHOT] Next shot number: {self.shot_logger.peek_next_shot_number()} "
                 f"(gui {self.shot_logger.gui_version})")
        if not self.shot_logger.counter_available:
            # Two GUIs open at once would otherwise claim the same number.
            self.log(f"[SHOT] WARNING: {self.shot_logger.counter.lock_message}")
            self.set_status("red", "Shot counter locked by another GUI")
            QTimer.singleShot(400, lambda: self.error_popup(
                "Shot counter locked",
                f"{self.shot_logger.counter.lock_message}.\n\n"
                "This GUI will not claim shot numbers. Close the other instance "
                "and restart this one before firing."))
        self.current_data = None
        # Captured waveform data per scope id (1/2/3). Each capture stores its
        # data here so export can write rigol<N>_<timestamp>.csv for every scope,
        # not just the most recently captured one.
        self.captured_scopes = {}
        self.export_workers = []
        self.export_worker = None
        self.export_progress = None

        # Auto-save: every capture marks the data "dirty" and (re)starts a
        # single-shot timer. When it fires the captures are written silently to
        # the session folder. closeEvent also flushes anything still dirty so a
        # capture is never lost on exit. _export_silent suppresses the popup for
        # auto/close saves.
        self.auto_save_delay_sec = auto_save_delay_sec
        self._captures_dirty = False
        self._export_silent = False
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.setSingleShot(True)
        self._auto_save_timer.timeout.connect(self._auto_save_fire)

        
    def refresh_wj_ports(self):
        """Populate COM lists for each WJ unit, selecting last used port."""
        ports = list_serial_ports()
        if not ports:
            ports = ["No COM ports"]

        for i, row in enumerate(self.wj_panel.rows):
            row.port_combo.clear()
            row.port_combo.addItems(ports)

            # Load last used
            last_port = self.conn.get(f"WJ{i+1}_COM", None)
            if last_port and last_port in ports:
                row.port_combo.setCurrentText(last_port)

        # Mirror ports into SF6 window duplicates
        if hasattr(self, "sf6_window") and hasattr(self.sf6_window, "wj_port_combos"):
            for i, combo in enumerate(self.sf6_window.wj_port_combos):
                combo.blockSignals(True)
                combo.clear()
                combo.addItems(ports)

                last_port = self.conn.get(f"WJ{i+1}_COM", None)
                if last_port and last_port in ports:
                    combo.setCurrentText(last_port)
                combo.blockSignals(False)

    # ------------------------------------------------------------------
    #  Opta pressure monitor (Modbus TCP, polled on its own QThread)
    # ------------------------------------------------------------------
    def _start_pressure_worker(self):
        """Create the Opta worker and park it on its own QThread. The thread
        idles until request_connect; every Modbus call runs there."""
        self.pressure_thread = QThread(self)
        self.pressure_worker = PressureWorker(
            self.opta_host, port=self.opta_port, poll_ms=self.opta_poll_ms)
        self.pressure_worker.moveToThread(self.pressure_thread)

        w = self.pressure_worker
        w.data_ready.connect(self._on_pressure_data)
        w.link_up.connect(self._on_pressure_link_up)
        w.link_lost.connect(self._on_pressure_link_lost)
        w.calibration_ready.connect(self._on_pressure_calibration)
        w.command_done.connect(self._on_pressure_command_done)
        w.command_failed.connect(self._on_pressure_command_failed)
        self.pressure_thread.finished.connect(w.deleteLater)
        self.pressure_thread.start()

        panel = self.sf6_window.sf6_panel
        panel.set_host(f"{self.opta_host}:{self.opta_port}")
        panel.btn_connect.clicked.connect(self.on_pressure_connect)
        panel.btn_disconnect.clicked.connect(self.on_pressure_disconnect)
        panel.btn_set_full_scale.clicked.connect(self.on_pressure_set_full_scale)
        panel.btn_zero_here.clicked.connect(self.on_pressure_zero_here)

    def on_pressure_connect(self):
        # Also serves as Reconnect: the worker closes any old socket first.
        self._opta_link_up = False
        self._invalidate_pressure()
        self.sf6_window.sf6_panel.set_link_state("connecting")
        self.log(f"[Opta] Connecting to {self.opta_host}:{self.opta_port}...")
        self.pressure_worker.request_connect.emit()

    def on_pressure_disconnect(self):
        self._opta_link_up = False
        self._invalidate_pressure()
        self.pressure_worker.request_disconnect.emit()
        self.sf6_window.sf6_panel.set_link_state("down")
        self.log("[Opta] Disconnected")

    def _invalidate_pressure(self):
        """Forget the last reading so nothing (interlock, logs) trusts it."""
        self._latest_psi = None
        self._opta_fault = None
        self.system_state.clear("pressure")

    def _on_pressure_link_up(self, where):
        self._opta_link_up = True
        self.sf6_window.sf6_panel.set_link_state("up")
        self.set_status("green", "Opta pressure connected")
        self.log(f"[Opta] Connected to {where}")
        self.data_logger.log_info("Opta", f"connected to {where}")

    def _on_pressure_link_lost(self, reason):
        self._opta_link_up = False
        self._invalidate_pressure()
        self.sf6_window.sf6_panel.set_link_state("lost", reason)
        self.set_status("red", "Opta pressure link lost")
        self.log(f"[Opta] LINK LOST: {reason}")
        self.data_logger.log_error("Opta", f"link lost: {reason}")

    def _on_pressure_data(self, d: dict):
        # Drop a snapshot that was already queued when the link went down.
        if not self._opta_link_up:
            return
        self.sf6_window.sf6_panel.show_snapshot(d)

        if d["under_range"]:
            fault = "under range"
        elif d["over_range"]:
            fault = "over range"
        else:
            fault = ""
        if fault != self._opta_fault:
            if fault:
                self.log(f"[Opta] SENSOR FAULT: input {fault} (I1 = {d['volts']:.3f} V)")
                self.data_logger.log_error("Opta", f"sensor {fault} at {d['volts']:.3f} V")
            elif self._opta_fault:
                self.log(f"[Opta] Sensor back in range ({d['psi']:.2f} psi)")
            self._opta_fault = fault

        # A dead or over-range sensor must not pass for a real pressure.
        self._latest_psi = None if fault else d["psi"]

        # Cache for the shot snapshot. The Opta is polled continuously and is
        # never queried inside the fire path; the row records how old this
        # sample was at t0 instead.
        self.system_state.update("pressure", {
            "psi": d["psi"],
            "volts": d["volts"],
            "counts": d["counts"],
            "status": ("UNDER_RANGE" if d["under_range"]
                       else "OVER_RANGE" if d["over_range"] else "OK"),
            "sample_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        }, source=SOURCE_READBACK)
        self.data_logger.log_opta_pressure(
            d["psi"], d["volts"], d["counts"], d["under_range"], d["over_range"])

    def _on_pressure_calibration(self, cal: dict):
        self.sf6_window.sf6_panel.show_calibration(cal)
        self.log(f"[Opta] Calibration loaded: full scale {cal['full_scale_psi']:.1f} psi, "
                 f"zero offset {cal['zero_offset_mv']} mV, averaging {cal['avg_samples']}")

    def _on_pressure_command_done(self, msg):
        self.log(f"[Opta] {msg}")
        self.data_logger.log_info("Opta", msg)

    def _on_pressure_command_failed(self, msg):
        self.log(f"[Opta ERROR] {msg}")
        self.data_logger.log_error("Opta", msg)
        self.error_popup("Opta Calibration Error", msg)

    def on_pressure_set_full_scale(self):
        if not self._opta_link_up:
            self.error_popup("Opta", "Not connected.")
            return
        psi = self.sf6_window.sf6_panel.spin_full_scale.value()
        self.log(f"[Opta] Setting full scale to {psi:.1f} psi...")
        self.pressure_worker.request_full_scale.emit(psi)

    def on_pressure_zero_here(self):
        if not self._opta_link_up:
            self.error_popup("Opta", "Not connected.")
            return
        if self._opta_fault is None:
            self.error_popup("Opta Zero", "No pressure reading yet.")
            return
        if self._opta_fault:
            self.error_popup("Opta Zero",
                             f"Sensor input is {self._opta_fault}. Fix the sensor before zeroing.")
            return
        reply = QMessageBox.question(
            self, "Zero Pressure",
            "Take the present transducer output as 0 psi?\n\n"
            "Vent the line to atmosphere first.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.log("[Opta] Zeroing at present input...")
        self.pressure_worker.request_zero_here.emit()


    def start_wj_readers(self):
        """Start WJ reader threads and connect to SF6 window plot"""
        from gui.wj_plot_window import WJReaderThread
        import time

        self.wj_workers = []
        self.wj_start_time = time.time()
        self.wj_t_buf = []
        self.wj_kv1_buf = []
        self.wj_ma1_buf = []
        self.wj_kv2_buf = []
        self.wj_ma2_buf = []
        self.wj_max_points = 3000  # Store ~5 minutes of history at ~10 Hz

        for idx, wj in enumerate(self.wj_units):
            worker = WJReaderThread(wj)
            worker.new_data.connect(lambda t, kv, ma, i=idx: self.handle_wj_plot_data(i, t, kv, ma))
            # Full Q reply (kV, mA, HV state, fault) for the state cache + log.
            worker.new_packet.connect(lambda pkt, i=idx: self.on_wj_packet(i, pkt))
            worker.start()
            self.wj_workers.append(worker)

    def handle_wj_plot_data(self, unit_index, t, kv, ma):
        """Handle incoming WJ data for plotting in SF6 window"""
        import time

        # Normalize time to shared reference
        t = time.time() - self.wj_start_time

        # Update live gauge displays in SF6 window
        if hasattr(self, "sf6_window"):
            try:
                if unit_index == 0:
                    self.sf6_window.kv1_gauge.update_value(kv)
                    self.sf6_window.ma1_gauge.update_value(ma)
                elif unit_index == 1:
                    self.sf6_window.kv2_gauge.update_value(kv)
                    self.sf6_window.ma2_gauge.update_value(ma)
            except Exception:
                pass

        # WJ_VOLTAGE rows are written by on_wj_packet, which has the supply's
        # real HV and fault bits. This path only plots; it used to log
        # hv_on=False/fault=False as constants.

        # Store data with separate time arrays for each unit
        # Unit 1
        if unit_index == 0:
            if not hasattr(self, 'wj_t1_buf'):
                self.wj_t1_buf = []
            self.wj_t1_buf.append(t)
            self.wj_kv1_buf.append(kv)
            self.wj_ma1_buf.append(ma)

            # Rolling window for unit 1 (keep more points for history)
            if len(self.wj_t1_buf) > self.wj_max_points:
                self.wj_t1_buf = self.wj_t1_buf[-self.wj_max_points:]
                self.wj_kv1_buf = self.wj_kv1_buf[-self.wj_max_points:]
                self.wj_ma1_buf = self.wj_ma1_buf[-self.wj_max_points:]

            # Update curves for unit 1
            self.sf6_window.kv1_curve.setData(self.wj_t1_buf, self.wj_kv1_buf)
            self.sf6_window.ma1_curve.setData(self.wj_t1_buf, self.wj_ma1_buf)

        # Unit 2
        elif unit_index == 1:
            if not hasattr(self, 'wj_t2_buf'):
                self.wj_t2_buf = []
            self.wj_t2_buf.append(t)
            self.wj_kv2_buf.append(kv)
            self.wj_ma2_buf.append(ma)

            # Rolling window for unit 2 (keep more points for history)
            if len(self.wj_t2_buf) > self.wj_max_points:
                self.wj_t2_buf = self.wj_t2_buf[-self.wj_max_points:]
                self.wj_kv2_buf = self.wj_kv2_buf[-self.wj_max_points:]
                self.wj_ma2_buf = self.wj_ma2_buf[-self.wj_max_points:]

            # Update curves for unit 2
            self.sf6_window.kv2_curve.setData(self.wj_t2_buf, self.wj_kv2_buf)
            self.sf6_window.ma2_curve.setData(self.wj_t2_buf, self.wj_ma2_buf)

        # Auto-scroll the plot to show the last 60 seconds
        self.sf6_window.update_wj_scroll(t)

    def position_and_show_windows(self):
        """Position windows on appropriate monitors and show them"""
        from PyQt6.QtGui import QGuiApplication

        screens = QGuiApplication.screens()
        if not screens:
            # Fallback: just show windows normally
            self.scope_window.showMaximized()
            self.sf6_window.showMaximized()
            return

        # Sort screens left-to-right by x coordinate
        screens_sorted = sorted(screens, key=lambda s: s.geometry().x())

        # Assign based on physical layout: left (vertical) -> SF6, middle -> main window, right -> scope
        if len(screens_sorted) >= 3:
            left_screen, middle_screen, right_screen = screens_sorted[:3]
        elif len(screens_sorted) == 2:
            left_screen, right_screen = screens_sorted
            middle_screen = left_screen  # fallback: place main on left if only two
        else:
            left_screen = middle_screen = right_screen = screens_sorted[0]

        # Main window on middle screen
        self.setScreen(middle_screen)
        self.move(middle_screen.availableGeometry().topLeft())
        self.showMaximized()

        # SF6 window on left screen
        self.sf6_window.setScreen(left_screen)
        self.sf6_window.move(left_screen.availableGeometry().topLeft())
        self.sf6_window.showMaximized()

        # Scope window on right screen
        self.scope_window.setScreen(right_screen)
        self.scope_window.move(right_screen.availableGeometry().topLeft())
        self.scope_window.showMaximized()

    def build_scope_controls(self, main_layout):
        layout = QHBoxLayout()

        # --------------------------------
        # Create instrument panels
        # --------------------------------
        self.dg_panel = DG535Panel()
        self.dg_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self.bnc_panel = BNC575Panel()
        self.bnc_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self.rigol_panel = RigolPanel()
        self.rigol_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self.wj_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        # CFR laser control panels (each owns its own serial controller + threads)
        self.laser_panel = LaserPanel(
            log_func=self.log, save_func=save_memory,
            default_port="COM16", title="CFR Laser 1",
            save_key="CFR_LASER_COM", log_tag="Laser1",
            event_func=self._on_laser_event)
        self.laser_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self.laser_panel2 = LaserPanel(
            log_func=self.log, save_func=save_memory,
            default_port="COM11", title="CFR Laser 2",
            save_key="CFR_LASER2_COM", log_tag="Laser2",
            event_func=self._on_laser_event)
        self.laser_panel2.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        # --------------------------------
        # GRID LAYOUT (2x2 + laser row)
        # --------------------------------
        grid = QGridLayout()
        # Right column stacks Rigol on top with the WJ power supplies directly
        # beneath it, top-aligned so Rigol hugs the top (no centering gap next
        # to the tall BNC panel).
        scope_ps_col = QVBoxLayout()
        scope_ps_col.setContentsMargins(0, 0, 0, 0)
        scope_ps_col.addWidget(self.rigol_panel)
        scope_ps_col.addWidget(self.wj_panel)
        scope_ps_col.addStretch()
        scope_ps_container = QWidget()
        scope_ps_container.setLayout(scope_ps_col)

        grid.addWidget(self.laser_panel, 0, 0)   # CFR Laser 1
        grid.addWidget(self.laser_panel2, 0, 1)  # CFR Laser 2 (side by side)
        grid.addWidget(self.bnc_panel, 1, 0, Qt.AlignmentFlag.AlignTop)
        grid.addWidget(scope_ps_container, 1, 1, Qt.AlignmentFlag.AlignTop)  # Rigol + WJ
        grid.addWidget(self.dg_panel, 2, 0, 1, 2)  # span both columns

        # --------------------------------
        # Left column: instrument grid inside a vertical scroll area. The panels
        # are Fixed-height; when their combined height exceeds the window the
        # whole grid scrolls instead of the panels overlapping each other.
        # --------------------------------
        grid_container = QWidget()
        grid_container.setLayout(grid)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        left_scroll.setWidget(grid_container)
        layout.addWidget(left_scroll, 3)

        # --------------------------------
        # Right column: relay + status lamp + log + scope button. Moving the
        # log here frees vertical space on the left and lets the log grow tall.
        # --------------------------------
        self.relay_panel = NumatoRelayPanel()
        self.relay_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self.status_lamp = StatusLamp()
        self.log_panel = LogPanel()
        self.log_panel.setMinimumWidth(340)
        self.log_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        self.btn_open_scope = QPushButton("Open Scope Display Window")
        self.btn_open_scope.clicked.connect(self.on_open_scope_window)

        right_column = QVBoxLayout()
        right_column.addWidget(self.relay_panel)
        right_column.addWidget(self.status_lamp)
        right_column.addWidget(self.log_panel, 1)  # log expands to fill height
        right_column.addWidget(self.btn_open_scope)
        layout.addLayout(right_column, 1)

        # Add the layout to the main window
        main_layout.addLayout(layout)

        # --------------------------------
        # Connect buttons
        # --------------------------------
        self.dg_panel.btn_connect.clicked.connect(self.on_dg_connect)
        # The laser DG535 is read back and (deliberately) written only through
        # these two buttons. The GUI never changes its trigger mode and never
        # sends SS: it stays externally triggered by BNC575 channel B.
        self.dg_panel.btn_fire.setText("Read Back DG535")
        self.dg_panel.btn_fire.setToolTip(
            "Read the laser DG535's four delays, their reference channels and "
            "the trigger mode, and fill the panel with them.")
        self.dg_panel.btn_fire.clicked.connect(self.on_dg_readback)
        self.dg_panel.btn_apply_delays.clicked.connect(self.on_dg_apply_delays)
        self.dg_panel.btn_read_all.clicked.connect(self.on_dg_readback)

        # BNC575 connections
        self.bnc_panel.btn_connect.clicked.connect(self.on_bnc_connect)
        self.bnc_panel.btn_disconnect.clicked.connect(self.on_bnc_disconnect)
        self.bnc_panel.btn_fire.clicked.connect(self.on_bnc_fire)
        self.bnc_panel.btn_apply.clicked.connect(self.on_bnc_apply)
        self.bnc_panel.btn_read.clicked.connect(self.on_bnc_read)
        self.bnc_panel.btn_arm.clicked.connect(self.on_bnc_arm)
        
        # Channel enable buttons
        if hasattr(self.bnc_panel, "btn_en_a"):
            self.bnc_panel.btn_en_a.clicked.connect(lambda: self.on_bnc_enable_channel("A"))
            self.bnc_panel.btn_en_b.clicked.connect(lambda: self.on_bnc_enable_channel("B"))
            self.bnc_panel.btn_en_c.clicked.connect(lambda: self.on_bnc_enable_channel("C"))
            self.bnc_panel.btn_en_d.clicked.connect(lambda: self.on_bnc_enable_channel("D"))
        
        # Trigger enable
        if hasattr(self.bnc_panel, "btn_en_trig"):
            self.bnc_panel.btn_en_trig.clicked.connect(self.on_bnc_enable_trigger)
        
        # Apply trigger settings
        if hasattr(self.bnc_panel, "btn_apply_trigger"):
            self.bnc_panel.btn_apply_trigger.clicked.connect(self.on_bnc_apply_trigger)
        
        # Apply system settings (mode, period, burst)
        if hasattr(self.bnc_panel, "btn_apply_system"):
            self.bnc_panel.btn_apply_system.clicked.connect(self.on_bnc_apply_system)
        
        # Store/Recall
        if hasattr(self.bnc_panel, "btn_store"):
            self.bnc_panel.btn_store.clicked.connect(self.on_bnc_store)
        if hasattr(self.bnc_panel, "btn_recall"):
            self.bnc_panel.btn_recall.clicked.connect(self.on_bnc_recall)
        if hasattr(self.bnc_panel, "btn_factory"):
            self.bnc_panel.btn_factory.clicked.connect(self.on_bnc_factory_reset)

        self.rigol_panel.btn_r1.clicked.connect(self.on_rigol1_connect)
        self.rigol_panel.btn_r2.clicked.connect(self.on_rigol2_connect)
        self.rigol_panel.btn_r3.clicked.connect(self.on_rigol3_connect)
        self.rigol_panel.btn_capture.clicked.connect(self.on_capture_all_scopes)
        self.rigol_panel.btn_r1_single.clicked.connect(self.on_r1_single)
        self.rigol_panel.btn_r2_single.clicked.connect(self.on_r2_single)
        self.rigol_panel.btn_r3_single.clicked.connect(self.on_r3_single)
        self.rigol_panel.btn_export.clicked.connect(self.on_export_csv)

        self.rigol_panel.btn_r1_capture.clicked.connect(self.on_capture_r1)
        self.rigol_panel.btn_r2_capture.clicked.connect(self.on_capture_r2)
        self.rigol_panel.btn_r3_capture.clicked.connect(self.on_capture_r3)

        self.wj_panel.btn_hv_on.clicked.connect(self.on_wj_hv_on)
        self.wj_panel.btn_hv_off.clicked.connect(self.on_wj_hv_off)
        self.wj_panel.btn_reset.clicked.connect(self.on_wj_reset)
        # clicked emits a bool checked arg; swallow it so on_wj_set_voltage
        # falls back to the spin-box values instead of receiving kv=False.
        self.wj_panel.btn_set_v.clicked.connect(lambda: self.on_wj_set_voltage())
        self.wj_panel.btn_read.clicked.connect(self.on_wj_read)

        # --- Disconnect buttons ---
        self.dg_panel.btn_disconnect.clicked.connect(self.on_dg_disconnect)

        self.rigol_panel.btn_r1_disconnect.clicked.connect(self.on_r1_disconnect)
        self.rigol_panel.btn_r2_disconnect.clicked.connect(self.on_r2_disconnect)
        self.rigol_panel.btn_r3_disconnect.clicked.connect(self.on_r3_disconnect)

        # Hook each WJ unit's connect/disconnect
        for idx, row in enumerate(self.wj_panel.rows):
            row.connect.clicked.connect(lambda _, i=idx: self.on_wj_connect(i))
            row.disconnect.clicked.connect(lambda _, i=idx: self.on_wj_disconnect(i))


    def auto_connect_all(self):
        self.log("=== Auto-connect starting ===")
        flags = self.auto_connect_flags
        skipped = [k for k, v in flags.items() if not v]
        if skipped:
            self.log(f"[AutoConnect] Skipping (disabled): {', '.join(skipped)}")

        # ------------------------------
        # DG535
        # ------------------------------
        if flags.get("dg535", True):
            try:
                port = self.conn.get("DG535_COM", "COM4")
                self.dg.connect(port=port, gpib_addr=15)
                save_memory("DG535_COM", port)
                self.log(f"[DG535] Connected on {port}")
                self.dg_panel.lamp.set_status("green", "Connected")
                self._dg_read_all_settings()
                self.dg_panel.set_status(f"Connected on {port}")
            except Exception as e:
                self.log(f"[DG535] NOT CONNECTED: {e}")
                self.dg_panel.lamp.set_status("red", "Not Connected")
                self.dg_panel.set_status("Not connected")

        # ------------------------------
        # BNC575
        # ------------------------------
        if flags.get("bnc575", True):
            try:
                port = self.conn.get("BNC575_COM", "COM5")
                self.bnc.connect(port=port)
                self.bnc_connected = True
                save_memory("BNC575_COM", port)
                idn = self.bnc.identify()
                self.log(f"[BNC575] Connected on {port}: {idn}")
                self.bnc_panel.lamp.set_status("green", "Connected")
                self.bnc_panel.set_connected(True, idn)

                # Read current settings from device
                self._bnc_read_all_settings()

            except Exception as e:
                self.bnc_connected = False
                self.log(f"[BNC575] NOT CONNECTED: {e}")
                self.bnc_panel.lamp.set_status("red", "Not Connected")
                self.bnc_panel.set_connected(False)

        # ------------------------------
        # Opta pressure monitor (Modbus TCP). The connect itself runs on the
        # worker thread; the result comes back as link_up or link_lost.
        # ------------------------------
        if flags.get("opta", True):
            self.on_pressure_connect()

        # ------------------------------
        # Numato Relay Module (connect BEFORE WJ supplies to avoid port conflict)
        # ------------------------------
        relay_port = None
        if flags.get("relay", True):
            try:
                relay_port = self.conn.get("RELAY_COM", None)
                if relay_port:
                    self.numato_relay.connect(relay_port)
                    self.relay_panel.set_connected(True, relay_port)
                    self.log(f"[Relay] Connected on {relay_port}")
            except Exception as e:
                self.log(f"[Relay] NOT CONNECTED: {e}")
                self.relay_panel.set_connected(False)

        # ------------------------------
        # WJ HIGH VOLTAGE SUPPLIES (both on USB-serial)
        # ------------------------------
        # Identical USB-serial adapters can resolve to the same COM number, so
        # never open a port the relay or the other supply already owns.
        claimed_ports = {relay_port} if relay_port else set()
        for i, wj in enumerate(self.wj_units):
            if not flags.get(f"wj{i+1}", True):
                continue
            row = self.wj_panel.rows[i]
            port = self.conn.get(f"WJ{i+1}_COM")
            if not port:
                self.log(f"[WJ{i+1}] No saved port to auto-connect")
                row.lamp.set_status("red", "Not Connected")
                continue
            if port in claimed_ports:
                self.log(f"[WJ{i+1}] Skipping {port} (already used by another device)")
                row.lamp.set_status("red", "Not Connected")
                continue
            try:
                fw = self._identify_wj_port(i, port)
                wj.connect(port)
                claimed_ports.add(port)
                row.lamp.set_status("green", "Connected")
                self.log(f"[WJ{i+1}] Connected on {port}, firmware {fw}")
            except Exception as e:
                row.lamp.set_status("red", "Not Connected")
                self.log(f"[WJ{i+1}] NOT CONNECTED: {e}")

        # ------------------------------
        # Rigol Oscilloscopes
        # ------------------------------
        rigol_state_map = {
            "Rigol1_VISA": ("rigol1_connected", self.rigol1),
            "Rigol2_VISA": ("rigol2_connected", self.rigol2),
            "Rigol3_VISA": ("rigol3_connected", self.rigol3),
        }

        for key, (flag_name, scope) in rigol_state_map.items():
            # "Rigol1_VISA" -> "rigol1" auto-connect flag
            if not flags.get(key.split("_")[0].lower(), True):
                continue
            try:
                visa_addr = self.conn.get(key, "")
                if visa_addr:
                    scope.resource_name = visa_addr

                scope.connect()
                idn = scope._query("*IDN?")

                setattr(self, flag_name, True)
                save_memory(key, scope.resource_name)

                self.log(f"[AutoConnect] {key} CONNECTED → {idn}")
                if key == "Rigol1_VISA":
                    self.rigol_panel.lamp_r1.set_status("green", "Connected")
                elif key == "Rigol2_VISA":
                    self.rigol_panel.lamp_r2.set_status("green", "Connected")
                elif key == "Rigol3_VISA":
                    self.rigol_panel.lamp_r3.set_status("green", "Connected")

            except Exception as e:
                setattr(self, flag_name, False)
                self.log(f"[AutoConnect] {key} NOT CONNECTED: {e}")
                if key == "Rigol1_VISA":
                    self.rigol_panel.lamp_r1.set_status("red", "Not Connected")
                elif key == "Rigol2_VISA":
                    self.rigol_panel.lamp_r2.set_status("red", "Not Connected")
                elif key == "Rigol3_VISA":
                    self.rigol_panel.lamp_r3.set_status("red", "Not Connected")

        # ------------------------------
        # CFR Laser (RS-232 over USB)
        # ------------------------------
        if flags.get("laser", True):
            try:
                laser_port = self.conn.get("CFR_LASER_COM", "COM16")
                self.laser_panel.port_edit.setText(laser_port)
                if self.laser_panel.connect_to(laser_port):
                    self.log(f"[Laser1] Connected on {laser_port}")
                else:
                    self.log(f"[Laser1] NOT CONNECTED on {laser_port}")
            except Exception as e:
                self.log(f"[Laser1] NOT CONNECTED: {e}")

            try:
                laser2_port = self.conn.get("CFR_LASER2_COM", "COM11")
                self.laser_panel2.port_edit.setText(laser2_port)
                if self.laser_panel2.connect_to(laser2_port):
                    self.log(f"[Laser2] Connected on {laser2_port}")
                else:
                    self.log(f"[Laser2] NOT CONNECTED on {laser2_port}")
            except Exception as e:
                self.log(f"[Laser2] NOT CONNECTED: {e}")

        self.log("=== Auto-connect done ===")


    def _bnc_read_all_settings(self):
        """Read the full BNC575 configuration back and cache it.

        Runs at connect and after every apply, never in the fire path. The
        shot row uses these read-back values rather than the GUI's spin boxes,
        so a setting applied in an earlier GUI session is still recorded.
        """
        try:
            # Read timing settings
            wA, dA, wB, dB, wC, dC, wD, dD = self.bnc.read_settings()
            self.bnc_panel.set_widthA(wA)
            self.bnc_panel.set_delayA(dA)
            self.bnc_panel.set_widthB(wB)
            self.bnc_panel.set_delayB(dB)
            self.bnc_panel.set_widthC(wC)
            self.bnc_panel.set_delayC(dC)
            self.bnc_panel.set_widthD(wD)
            self.bnc_panel.set_delayD(dD)

            # Read period
            period = self.bnc.get_period()
            self.bnc_panel.set_period(period)

            # Read channel states, and polarity for the shot row
            widths = {"A": wA, "B": wB, "C": wC, "D": wD}
            delays = {"A": dA, "B": dB, "C": dC, "D": dD}
            channels = {}
            for ch in ['A', 'B', 'C', 'D']:
                enabled = self.bnc.get_channel_state(ch)
                self.bnc_panel.set_channel_enabled(ch, enabled)
                try:
                    polarity = self.bnc.get_channel_polarity(ch)
                    polarity = getattr(polarity, "value", polarity) or ""
                except Exception:
                    polarity = UNKNOWN
                channels[ch] = {
                    "delay_s": delays[ch],
                    "width_s": widths[ch],
                    "enabled": enabled,
                    "polarity": polarity,
                }

            # Read system mode
            mode = self.bnc.get_system_mode()
            if mode:
                self.bnc_panel.set_system_mode(mode.value)

            try:
                trigger_mode = self.bnc.get_trigger_mode()
                trigger_mode = getattr(trigger_mode, "value", trigger_mode) or UNKNOWN
            except Exception:
                trigger_mode = UNKNOWN

            self.system_state.update("bnc575", {
                "channels": channels,
                "period_s": period,
                "system_mode": mode.value if mode else UNKNOWN,
                "trigger_mode": trigger_mode,
                "armed": self.bnc_trigger_armed,
            }, source=SOURCE_READBACK)

            self.log("[BNC575] Read all settings from device")
        except Exception as e:
            self.log(f"[BNC575] Error reading settings: {e}")


    # ------------------------------------------------------------------
    #  SF6 Window Connection
    # ------------------------------------------------------------------
    def connect_sf6_window(self):
        """Connect signals from SF6 window to main window handlers"""
        # Duplicate WJ controls under the plot
        sw = self.sf6_window
        sw.btn_apply_program.clicked.connect(
            lambda: self.on_wj_set_voltage(sw.program_voltage.value(), sw.program_current.value())
        )
        sw.btn_hv_on.clicked.connect(self.on_wj_hv_on)
        sw.btn_hv_off.clicked.connect(self.on_wj_hv_off)
        sw.btn_reset.clicked.connect(self.on_wj_reset)
        sw.btn_read.clicked.connect(self.on_wj_read)

        for i in range(len(sw.wj_port_combos)):
            sw.btn_wj_connect[i].clicked.connect(
                lambda _, idx=i: self.on_wj_connect(idx, sw.wj_port_combos[idx].currentText())
            )
            sw.btn_wj_disconnect[i].clicked.connect(
                lambda _, idx=i: self.on_wj_disconnect(idx)
            )

        # Connect Numato Relay panel
        self.connect_relay_panel()

    def connect_relay_panel(self):
        """Connect signals from Numato Relay panel to handlers"""
        relay_panel = self.relay_panel

        # Populate COM ports
        self.refresh_relay_ports()

        # Connect buttons
        relay_panel.btn_refresh.clicked.connect(self.refresh_relay_ports)
        relay_panel.btn_connect.clicked.connect(self.on_relay_connect)
        relay_panel.btn_disconnect.clicked.connect(self.on_relay_disconnect)

        # Connect relay control signals
        relay_panel.relay_state_changed.connect(self.on_relay_state_changed)
        relay_panel.all_on_requested.connect(self.on_relay_all_on)
        relay_panel.all_off_requested.connect(self.on_relay_all_off)
        relay_panel.polling_toggle_requested.connect(self.on_relay_polling_toggle)

    def refresh_relay_ports(self):
        """Populate COM port list for relay panel"""
        ports = list_serial_ports()
        if not ports:
            ports = ["No COM ports"]

        relay_panel = self.relay_panel
        relay_panel.port_combo.clear()
        relay_panel.port_combo.addItems(ports)

        # Load last used port
        last_port = self.conn.get("RELAY_COM", None)
        if last_port and last_port in ports:
            relay_panel.port_combo.setCurrentText(last_port)

    def on_relay_connect(self):
        """Connect to Numato relay module"""
        relay_panel = self.relay_panel
        port = relay_panel.port_combo.currentText()

        if not port or port == "No COM ports":
            self.error_popup("No Port", "Select a serial port first.")
            return

        try:
            self.numato_relay.connect(port)
            relay_panel.set_connected(True, port)
            self.log(f"[Relay] Connected to {port}")
            # The module reports no relay states, and this GUI has issued no
            # commands yet, so the physical state is genuinely unknown.
            self.system_state.update(
                "relays", {"states": {}, "source": "unknown"}, source=SOURCE_COMMANDED)
            self.data_logger.log_relay_state({}, source="unknown at connect")
            self._mark_interlock(2, f"relay connected {port}")

            # Save port to memory
            self.conn["RELAY_COM"] = port
            save_memory("RELAY_COM", port)

        except Exception as e:
            self.log(f"[Relay ERROR] {e}")
            self.error_popup("Relay Connection Error", str(e))

    def on_relay_disconnect(self):
        """Disconnect from Numato relay module"""
        relay_panel = self.relay_panel

        # Stop polling first
        if self.relay_polling:
            self._stop_relay_polling()

        try:
            self.numato_relay.close()
            relay_panel.set_connected(False)
            self.log("[Relay] Disconnected")

        except Exception as e:
            self.log(f"[Relay ERROR] {e}")

    def on_relay_state_changed(self, channel: int, state: bool):
        """Handle relay switch toggle"""
        try:
            self.numato_relay.set_relay(channel, state)
            state_str = "ON" if state else "OFF"
            self.log(f"[Relay] Channel {channel} {state_str}")
            self._record_relay_state(channel, state, ok=True)
            self._mark_interlock(2, f"relay ch{channel} responded")

            # Interlock: turning ON Charging Relay (CH1) also energizes Discharging Relay (CH0)
            if channel == self._RELAY_CHARGING and state:
                self._relay_set(self._RELAY_DISCHARGING, True)

        except Exception as e:
            self.log(f"[Relay ERROR] {e}")
            self.error_popup("Relay Error", str(e))

    def on_relay_all_on(self):
        """Turn all relays ON"""
        try:
            self.numato_relay.all_on()
            self.relay_panel.update_all_states([True, True, True, True])
            self.log("[Relay] All channels ON")
            for _ch in range(4):
                self._record_relay_state(_ch, True, ok=True)
            self._mark_interlock(2, "relay all on responded")
        except Exception as e:
            self.log(f"[Relay ERROR] {e}")
            self.error_popup("Relay Error", str(e))

    def on_relay_all_off(self):
        """Turn all relays OFF"""
        try:
            self.numato_relay.all_off()
            self.relay_panel.update_all_states([False, False, False, False])
            self.log("[Relay] All channels OFF")
            for _ch in range(4):
                self._record_relay_state(_ch, False, ok=True)
            self._mark_interlock(2, "relay all off responded")
        except Exception as e:
            self.log(f"[Relay ERROR] {e}")
            self.error_popup("Relay Error", str(e))

    # ── GPIO Pushbutton Polling ────────────────────────────────────────

    def on_relay_polling_toggle(self, start: bool):
        """Start or stop GPIO pushbutton polling."""
        if start:
            self._start_relay_polling()
        else:
            self._stop_relay_polling()

    def _start_relay_polling(self):
        """Start background GPIO polling thread."""
        if not self.numato_relay.is_connected:
            self.log("[Relay] Cannot start polling — not connected")
            self.relay_panel.set_polling_active(False)
            return
        self.relay_polling = True
        self.relay_panel.set_polling_active(True)
        self.log("[Relay] GPIO pushbutton polling started (GPIO 2, 3, 4, 5)")
        import threading
        self.relay_poll_thread = threading.Thread(
            target=self._relay_poll_loop, daemon=True)
        self.relay_poll_thread.start()

    def _stop_relay_polling(self):
        """Stop the GPIO polling thread."""
        self.relay_polling = False
        self.relay_panel.set_polling_active(False)
        if self.relay_poll_thread:
            self.relay_poll_thread.join(timeout=1)
            self.relay_poll_thread = None
        self.log("[Relay] GPIO pushbutton polling stopped")

    def _relay_poll_loop(self):
        """Background thread: poll GPIO pins for pushbutton presses.

        button_map: (gpio_pin, relay_channel)
          GPIO 2 → Relay 1 (CH0) toggle
          GPIO 3 → Relay 2 (CH1) toggle
          GPIO 4 → Relay 3 (CH2) toggle
          GPIO 5 → Relay 4 (CH3) toggle
        Rising-edge detection prevents re-firing while button is held.
        """
        import time
        # (gpio_pin, relay_channel)
        button_map = [
            (2, 1),  # GPIO 2 → CH1 (Charging Relay 1)
            (3, 0),  # GPIO 3 → CH0 (Discharging Relay 1)
            (4, 2),  # GPIO 4 → Relay 3
            (5, 3),  # GPIO 5 → Relay 4
        ]
        prev = {gpio: False for gpio, _ in button_map}

        while self.relay_polling and self.numato_relay.is_connected:
            try:
                for gpio_pin, ch in button_map:
                    if not self.relay_polling:
                        break
                    current = self.numato_relay.gpio_read(gpio_pin)
                    time.sleep(0.02)
                    # Rising edge only — toggle relay once per press
                    if current and not prev[gpio_pin]:
                        new_state = not self.numato_relay.relay_states[ch]
                        if new_state:
                            self.numato_relay.relay_on(ch)
                        else:
                            self.numato_relay.relay_off(ch)
                        self.numato_relay.relay_states[ch] = new_state
                        self._relay_update_signal.emit(ch, new_state)
                    prev[gpio_pin] = current
                time.sleep(0.08)
            except Exception as e:
                self._relay_log_signal.emit(f"[Relay Poll ERROR] {e}")
                time.sleep(0.5)

    def _relay_pushbutton_ui_update(self, ch: int, state: bool):
        """Called on main thread after a pushbutton press updates relay state."""
        label = "ON" if state else "OFF"
        self.log(f"[Relay] GPIO button: CH{ch} → {label}")
        self.relay_panel.update_relay_state(ch, state)

    # ── Relay channel constants ────────────────────────────────────────
    _RELAY_CHARGING    = 1  # CH1 — Charging Relay 1  (NO)
    _RELAY_DISCHARGING = 0  # CH0 — Discharging Relay 1 (NC)

    # Channel -> shot-log name. This program only identifies two relays by
    # function ("Charging Relay 1" / "Discharging Relay 1"); neither the panel
    # nor the driver says which polarity rail they belong to, so the shot row
    # fills charge_positive/discharge_positive from them and leaves the
    # negative-rail columns UNKNOWN rather than guessing.
    _RELAY_NAMES = {
        0: "discharge_positive",
        1: "charge_positive",
        2: "relay3",
        3: "relay4",
    }

    def _relay_set(self, ch: int, state: bool):
        """Set a relay and update the GUI panel. Safe to call from main thread only."""
        if not self.numato_relay.is_connected:
            self.log(f"[Relay] Not connected — cannot set CH{ch}")
            return
        try:
            self.numato_relay.set_relay(ch, state)
            self.relay_panel.update_relay_state(ch, state)
            self.log(f"[Relay] CH{ch} → {'ON' if state else 'OFF'}")
            self._record_relay_state(ch, state, ok=True)
        except Exception as e:
            self.log(f"[Relay ERROR] CH{ch}: {e}")
            self._record_relay_state(ch, state, ok=False)

    def on_export_csv(self):
        """Manual export (toolbar/button): export every captured scope to its
        own CSV in this launch's session folder. Files are auto-named
        rigol<N>_<session timestamp>.csv to match the experiment log (e.g.
        experiment_log_20260616_171252.csv -> rigol1_20260616_171252.csv), so
        there is no Save dialog. Shows a completion popup."""
        if not self.captured_scopes:
            QMessageBox.warning(self, "No Data", "No waveform data captured yet!\n\nCapture from a scope first.")
            return
        self._start_async_export(silent=False)

    def _mark_captures_dirty(self):
        """Flag captured data as unsaved and (re)start the auto-save countdown.
        Called after every capture. Each new capture pushes the timer out so a
        burst of captures saves once, shortly after the last one."""
        self._captures_dirty = True
        if self.auto_save_delay_sec and self.auto_save_delay_sec > 0:
            self._auto_save_timer.start(int(self.auto_save_delay_sec * 1000))

    def _auto_save_fire(self):
        """Auto-save timer elapsed — silently write captures if still unsaved."""
        if not self._captures_dirty or not self.captured_scopes:
            return
        self.log(f"[AUTO-SAVE] {self.auto_save_delay_sec:.0f}s elapsed — saving captured waveforms...")
        self._start_async_export(silent=True)

    def _start_async_export(self, silent=False):
        """Spin up one background worker per captured scope. silent suppresses
        the completion popup (used for auto-save). Clears the dirty flag once
        every file is written."""
        if not self.captured_scopes:
            return

        session_dir = self.data_logger.get_session_dir()

        # One background worker per captured scope. Track how many are still
        # running so the completion popup / dirty-clear fires once everything
        # is written.
        self.export_workers = []
        self._export_done_paths = []
        self._export_pending = len(self.captured_scopes)
        self._export_silent = silent

        for scope_id in sorted(self.captured_scopes):
            path = self.data_logger.scope_export_path(
                scope_id, shot_index=self.shot_logger.session_shot_index)
            worker = CSVExportWorker(self.captured_scopes[scope_id], path)
            worker.finished.connect(self._on_one_export_finished)
            worker.error.connect(self.on_export_error)
            self.export_workers.append(worker)

        for worker in self.export_workers:
            worker.start()

        self.set_status("green", "Exporting...")
        self.log(f"[EXPORT] Exporting {self._export_pending} scope file(s) to {session_dir} ...")

    def _on_one_export_finished(self, filename):
        """One scope CSV finished; clear dirty + show summary once all are done."""
        self._export_done_paths.append(filename)
        self.log(f"[EXPORT] ✅ Saved {filename}")
        self._export_pending -= 1
        if self._export_pending <= 0:
            self._captures_dirty = False  # everything written — nothing to flush on close
            if not self._export_silent:
                files = "\n".join(self._export_done_paths)
                QMessageBox.information(
                    self,
                    "Export Complete",
                    f"✅ Exported {len(self._export_done_paths)} file(s):\n\n{files}"
                )
            self.set_status("green", "Export complete")

    def on_export_finished(self, filename):
        """Handle successful CSV export."""
        if self.export_progress:
            self.export_progress.close()

        QMessageBox.information(
            self,
            "Export Complete",
            f"✅ Data exported successfully!\n\nFile:\n{filename}"
        )
        self.set_status("green", "Export complete")
        self.log(f"[EXPORT] ✅ Saved to {filename}")

    def on_export_error(self, error_msg):
        """Handle CSV export error."""
        if self.export_progress:
            self.export_progress.close()

        QMessageBox.critical(
            self,
            "Export Error",
            f"❌ Failed to export CSV:\n\n{error_msg}"
        )
        self.set_status("red", "Export failed")
        self.log(f"[EXPORT] ❌ Error: {error_msg}")

    # def on_export_csv(self):
    #     import csv
    #     from datetime import datetime

    #     def export_scope_csv(scope, prefix):
    #         """Export current waveform data from scope to CSV (4 channels)."""
    #         data = scope.capture_four_channels()
    #         (t1, v1), (t2, v2), (t3, v3), (t4, v4) = data
            
    #         timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    #         filename = f"{prefix}_{timestamp}.csv"

    #         # Find max length among all channels
    #         max_len = max(len(t1), len(t2), len(t3), len(t4))

    #         with open(filename, "w", newline="") as f:
    #             writer = csv.writer(f)
    #             writer.writerow(["time_s", "ch1_v", "ch2_v", "ch3_v", "ch4_v"])
    #             for i in range(max_len):
    #                 row = [
    #                     t1[i] if i < len(t1) else "",
    #                     v1[i] if i < len(v1) else "",
    #                     v2[i] if i < len(v2) else "",
    #                     v3[i] if i < len(v3) else "",
    #                     v4[i] if i < len(v4) else "",
    #                 ]
    #                 writer.writerow(row)
    #         return filename

    #     try:
    #         saved_files = []

    #         if self.rigol1_connected:
    #             f = export_scope_csv(self.rigol1, "rigol1")
    #             saved_files.append(f)

    #         if self.rigol2_connected:
    #             f = export_scope_csv(self.rigol2, "rigol2")
    #             saved_files.append(f)

    #         if self.rigol3_connected:
    #             f = export_scope_csv(self.rigol3, "rigol3")
    #             saved_files.append(f)

    #         if not saved_files:
    #             self.error_popup("No Data", "No scopes are connected.")
    #             return

    #         msg = "Saved:\n" + "\n".join(saved_files)
    #         self.log(msg)
    #         self.set_status("green", "Waveforms exported")

    #     except Exception as e:
    #         self.error_popup("CSV Export Error", str(e))
    #         self.log(f"[CSV ERROR] {e}")


    # ------------------------------------------------------------------
    #  Helpers
    # ------------------------------------------------------------------
    def log(self, msg: str):
        self.log_panel.log(msg)
        # Mirror every on-screen line to gui_log_<session>.txt, flushed per
        # line: the GUI is usually closed within seconds of a shot.
        try:
            self.data_logger.append_gui_line(msg)
        except Exception:
            pass

    def _deferred_log(self, msg: str):
        """log() that also works before the log panel is built."""
        if getattr(self, "log_panel", None) is None:
            self._early_log_buffer.append(msg)
        else:
            self.log(msg)

    # Text + color for each Rigol capture-mode state shown in the status strip.
    _CAPTURE_STATE_STYLE = {
        "idle":      ("Idle",       "#9E9E9E"),  # gray
        "armed":     ("Armed",      "#FB8C00"),  # orange — waiting for trigger
        "capturing": ("Capturing",  "#1E88E5"),  # blue — reading memory
        "done":      ("Done",       "#43A047"),  # green
        "error":     ("Error",      "#E53935"),  # red
    }

    def _build_capture_status_strip(self, parent_layout):
        """Always-visible strip across the top showing R1/R2/R3 capture state."""
        strip = QHBoxLayout()
        title = QLabel("Scope Capture:")
        title.setStyleSheet("font-weight:bold;")
        strip.addWidget(title)

        self.capture_state_labels = {}
        for sid in (1, 2, 3):
            lbl = QLabel()
            lbl.setMinimumWidth(150)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.capture_state_labels[sid] = lbl
            strip.addWidget(lbl)
            self._set_capture_state(sid, "idle")

        strip.addStretch()
        parent_layout.addLayout(strip)

    def _set_capture_state(self, scope_id: int, state: str, detail: str = ""):
        """Update one scope's capture indicator (idle/armed/capturing/done/error)."""
        lbl = getattr(self, "capture_state_labels", {}).get(scope_id)
        if lbl is None:
            return
        text, color = self._CAPTURE_STATE_STYLE.get(state, ("?", "#9E9E9E"))
        label = f"R{scope_id}: {text}"
        if detail:
            label += f" ({detail})"
        lbl.setText(label)
        lbl.setStyleSheet(
            f"background-color:{color}; color:white; font-weight:bold;"
            " padding:4px 10px; border-radius:4px;"
        )

    # ------------------------------------------------------------------
    #  Pre-fire interlock checklist
    # ------------------------------------------------------------------
    # (index, label) for each auto-checked interlock step. Step 5 is the
    # gated Single + Capture action, built separately.
    _INTERLOCK_STEPS = [
        (1, "1. Laser Prep/Arm"),
        (2, "2. Relay Connection"),
        (3, "3. Power Supplies"),
        (4, "4. Pressure > 50 psi"),
    ]

    def _build_interlock_strip(self, parent_layout):
        """Latching pre-fire checklist next to the Scope Capture strip.

        Steps 1 (both lasers armed) and 4 (dome pressure > 50 psi) are polled
        automatically. Steps 2 (relay) and 3 (power supplies) latch when their
        own action handlers get a good response. Each step also has a Manual
        override checkbox. Once a step is green it STAYS green until Reset.
        Step 5 (Single + Capture) is enabled only when 1-4 are all green.
        """
        strip = QHBoxLayout()
        title = QLabel("Interlocks:")
        title.setStyleSheet("font-weight:bold;")
        strip.addWidget(title)

        # The operator sees the next shot number before firing.
        self.lbl_next_shot = QLabel()
        strip.addWidget(self.lbl_next_shot)
        strip.addSpacing(10)

        self.interlock_lamps = {}
        self.interlock_manual = {}
        self.interlock_passed = {}

        for idx, text in self._INTERLOCK_STEPS:
            lamp = StatusLamp(size=14, text=text)
            lamp.set_status("red")
            self.interlock_lamps[idx] = lamp
            self.interlock_passed[idx] = False
            strip.addWidget(lamp)

            chk = QCheckBox("man")
            chk.setToolTip("Manual override: force this step to pass")
            self.interlock_manual[idx] = chk
            strip.addWidget(chk)
            strip.addSpacing(8)

        # Step 5 - the gated fire/capture action.
        self.btn_interlock_fire = QPushButton("5. Single + Capture Scopes")
        self.btn_interlock_fire.setEnabled(False)
        self.btn_interlock_fire.setStyleSheet(
            "background-color:#c0392b; color:white; font-weight:bold;"
            " padding:4px 12px; border-radius:4px;")
        self.btn_interlock_fire.clicked.connect(self.on_interlock_fire)
        strip.addWidget(self.btn_interlock_fire)

        self.btn_interlock_reset = QPushButton("Reset")
        self.btn_interlock_reset.setToolTip("Clear all interlock latches")
        self.btn_interlock_reset.clicked.connect(self.reset_interlocks)
        strip.addWidget(self.btn_interlock_reset)

        strip.addStretch()
        parent_layout.addLayout(strip)

        self._update_next_shot_label()
        self._update_interlock_state()

        # Poll the cheap (no-serial) checks on a timer.
        self._interlock_timer = QTimer(self)
        self._interlock_timer.setInterval(1000)
        self._interlock_timer.timeout.connect(self._poll_interlocks)
        self._interlock_timer.start()

    def _mark_interlock(self, idx, source=""):
        """Latch step `idx` green (idempotent). Called by action handlers."""
        if not getattr(self, "interlock_passed", None):
            return
        if self.interlock_passed.get(idx):
            return
        self.interlock_passed[idx] = True
        lamp = self.interlock_lamps.get(idx)
        if lamp:
            lamp.set_status("green")
        self.log(f"[INTERLOCK] Step {idx} PASSED"
                 + (f" ({source})" if source else ""))
        self.data_logger.log_interlock(
            "PASS", step=dict(self._INTERLOCK_STEPS).get(idx, str(idx)),
            detail=source, passed=True)
        self._update_interlock_fire()
        self._update_interlock_state()

    def _update_interlock_fire(self):
        if hasattr(self, "btn_interlock_fire"):
            self.btn_interlock_fire.setEnabled(
                all(self.interlock_passed.values()))

    def reset_interlocks(self):
        for idx in self.interlock_passed:
            self.interlock_passed[idx] = False
            self.interlock_lamps[idx].set_status("red")
            self.interlock_manual[idx].setChecked(False)
        self._update_interlock_fire()
        self._update_interlock_state()
        self.log("[INTERLOCK] Checklist reset.")
        self.data_logger.log_interlock("CHECK", detail="checklist reset")

    def _poll_interlocks(self):
        """Timer tick: evaluate the auto-checked steps and honor manual
        overrides. Latched (green) steps are skipped so they never re-lock."""
        # Step 1 - both lasers armed (reads widget state only, no serial).
        if not self.interlock_passed.get(1):
            if self.interlock_manual[1].isChecked():
                self._mark_interlock(1, "manual")
            elif self._check_lasers_armed():
                self._mark_interlock(1, "both lasers armed")

        # Step 4 - dome pressure above 50 psi (latest in-range Opta reading).
        if not self.interlock_passed.get(4):
            if self.interlock_manual[4].isChecked():
                self._mark_interlock(4, "manual")
            elif self._check_pressure_ok():
                psi = getattr(self, "_latest_psi", 0.0)
                self._mark_interlock(4, f"{psi:.1f} psi")

        # Step 2 - relay connection. Latches on a good relay response (see the
        # relay handlers) but also passes on a live connection so it does not
        # stay red after auto-connect.
        if not self.interlock_passed.get(2):
            if self.interlock_manual[2].isChecked():
                self._mark_interlock(2, "manual")
            elif getattr(self, "numato_relay", None) and \
                    self.numato_relay.is_connected:
                self._mark_interlock(2, "relay connected")

        # Step 3 - power supplies. Latches from on_wj_read (a good R packet with
        # no fault); here we only honor a manual override checkbox.
        if not self.interlock_passed.get(3) and \
                self.interlock_manual[3].isChecked():
            self._mark_interlock(3, "manual")

        self._update_interlock_fire()
        self._update_interlock_state()

    def _check_lasers_armed(self):
        """True only if every present laser panel reports EXT-armed."""
        panels = [p for p in (getattr(self, "laser_panel", None),
                              getattr(self, "laser_panel2", None))
                  if p is not None]
        return bool(panels) and all(p.is_armed() for p in panels)

    def _check_pressure_ok(self):
        psi = getattr(self, "_latest_psi", None)
        return psi is not None and psi >= 50.0

    def on_interlock_fire(self):
        if not all(self.interlock_passed.values()):
            labels = dict(self._INTERLOCK_STEPS)
            failed = [labels.get(i, str(i))
                      for i, ok in self.interlock_passed.items() if not ok]
            self.error_popup(
                "Interlocks not satisfied",
                "All interlock steps (1-4) must be green before firing.")
            # A blocked attempt is not a shot: no shot number is consumed.
            self.data_logger.log_interlock("FAIL", detail="; ".join(failed), passed=False)
            self.data_logger.log_fire_blocked("interlocks_not_satisfied", "; ".join(failed))
            self.log(f"[SHOT] Fire blocked by interlocks: {', '.join(failed)}")
            return
        self.log("[INTERLOCK] All checks green - firing.")
        # Step 5 fires the real shot. on_bnc_fire is the only path that sends
        # the master trigger and records a shot row; arming the scopes is a
        # separate action (on_capture_all_scopes).
        self.on_bnc_fire()

    def set_status(self, color: str, text: str):
        self.status_lamp.set_status(color, text)

    def error_popup(self, title: str, text: str):
        QMessageBox.critical(self, title, text)

    # ------------------------------------------------------------------
    #  DG535 Handlers
    # ------------------------------------------------------------------
    def on_dg_connect(self):
        port = "COM4"
        try:
            self.set_status("yellow", f"Connecting DG535 on {port}...")
            self.log(f"[DG535] Connecting on {port}...")
            self.dg.connect(port=port, gpib_addr=15)
            save_memory("DG535_COM", port)
            self.set_status("green", "DG535 connected")
            self.log("[DG535] Connected.")
            self.dg_panel.lamp.set_status("green", "Connected")
            self.dg_panel.set_status(f"Connected on {port}")
            self._dg_read_all_settings()
        except Exception as e:
            self.set_status("red", "DG535 connection failed")
            self.log(f"[DG535 ERROR] {e}")
            self.error_popup("DG535 Error", str(e))

    def on_dg_readback(self):
        """Read the laser DG535 back into the panel and the system state."""
        if not self.dg.is_connected():
            self.error_popup("DG535", "Not connected")
            return
        self.set_status("yellow", "Reading DG535 back...")
        if self._dg_read_all_settings():
            self.set_status("green", "DG535 read back")
        else:
            self.set_status("red", "DG535 readback failed")

    def on_dg_apply_delays(self):
        """Write only the delays/references the operator actually changed.

        Never touches the trigger mode and never sends SS: the unit stays
        externally triggered by BNC575 channel B. Requires a readback first,
        so "unchanged" is measured against what the instrument reported, not
        against the panel's defaults.
        """
        if not self.dg.is_connected():
            self.error_popup("DG535", "Not connected")
            return
        last = getattr(self, "_dg_last_readback", None)
        if not last:
            self.error_popup("DG535", "Read the DG535 back before applying.")
            return

        from instruments.dg535 import Channel
        ch_ids = {"T0": Channel.T0, "A": Channel.A, "B": Channel.B,
                  "C": Channel.C, "D": Channel.D}

        # What the panel is asking for.
        desired = {}
        for name in ("A", "B", "C", "D"):
            ref_name, delay = self.dg_panel.get_delay_with_reference(name)
            desired[name] = {"ref": ref_name, "delay_s": float(delay)}

        # Reject a bad reference graph before writing anything.
        problem = self._dg_validate_references(desired)
        if problem:
            self.error_popup("DG535 reference error", problem)
            self.data_logger.log_error("DG535_laser", f"apply rejected: {problem}")
            return

        # Only channels the operator actually edited since the last readback.
        # Deliberately NOT a comparison against the readback: the instrument
        # reports more digits than the spin box shows, so comparing values
        # would mark untouched channels as changed.
        dirty = self.dg_panel.dirty_channels()
        changes = []
        for name in dirty:
            want = desired[name]
            have = last.get(name, {})
            changes.append((name, channel_name(have.get("ref")) or UNKNOWN,
                            have.get("delay_s"), want["ref"], want["delay_s"]))

        if not changes:
            self.log("[DG535] Apply: no channel has been edited since the readback.")
            self.error_popup("DG535", "Nothing to apply: no channel has been "
                                      "edited since the last readback.")
            return

        lines = [
            f"{name}:  {'' if old_d is None else f'{old_d * 1e6:.6f} us'} "
            f"(ref {old_ref})   ->   {new_d * 1e6:.6f} us (ref {new_ref})"
            for name, old_ref, old_d, new_ref, new_d in changes
        ]
        answer = QMessageBox.question(
            self, "Write to the laser DG535?",
            "These channels will be written to the laser DG535:\n\n"
            + "\n".join(lines)
            + "\n\nThe trigger mode is not changed and no fire is sent.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.log("[DG535] Apply cancelled by the operator.")
            return

        before = {n: (channel_name(c.get("ref")) or UNKNOWN, c.get("delay_s"))
                  for n, c in last.items()}
        try:
            for name, _old_ref, _old_d, new_ref, new_d in changes:
                self.dg.set_delay(ch_ids[name], ch_ids[new_ref], new_d)
                self.log(f"[DG535] Wrote {name} = {new_d * 1e6:.6f} us (ref {new_ref})")
        except Exception as e:
            self.log(f"[DG535 ERROR] write failed: {e}")
            self.data_logger.log_error("DG535_laser", f"apply write failed: {e}")
            self.error_popup("DG535 Apply Error", str(e))
            self._dg_read_all_settings()
            return

        # Confirm the instrument holds what we just wrote.
        self._dg_read_all_settings()
        after_state = (self.system_state.get("dg535_laser") or {}).get("channels", {})
        after = {n: (channel_name(c.get("ref")) or UNKNOWN, c.get("delay_s"))
                 for n, c in after_state.items()}

        mismatches = []
        for name, _old_ref, _old_d, new_ref, new_d in changes:
            got_ref, got_delay = after.get(name, (UNKNOWN, None))
            if got_ref != new_ref or got_delay is None or abs(got_delay - new_d) > 1e-11:
                mismatches.append(
                    f"{name}: wrote {new_d * 1e6:.6f} us (ref {new_ref}), "
                    f"read back "
                    f"{'nothing' if got_delay is None else f'{got_delay * 1e6:.6f} us'} "
                    f"(ref {got_ref})")

        self.data_logger.log_custom(
            "DG535_APPLY", "DG535_laser",
            param1=",".join(c[0] for c in changes),
            param2="mismatch" if mismatches else "verified",
            notes=("before " + "; ".join(f"{n}={d[1] if d[1] is None else f'{d[1] * 1e6:.6f}us'}"
                                         f"(ref {d[0]})" for n, d in sorted(before.items()))
                   + " | after " + "; ".join(f"{n}={d[1] if d[1] is None else f'{d[1] * 1e6:.6f}us'}"
                                             f"(ref {d[0]})" for n, d in sorted(after.items()))))

        if mismatches:
            detail = "\n".join(mismatches)
            self.log(f"[DG535 ERROR] readback does not match what was written:\n{detail}")
            self.data_logger.log_error("DG535_laser", "apply mismatch: " + "; ".join(mismatches))
            self.error_popup("DG535 did not take the change", detail)
            self.set_status("red", "DG535 apply MISMATCH")
        else:
            self.log(f"[DG535] Apply verified for {', '.join(c[0] for c in changes)}.")
            self.set_status("green", "DG535 delays applied")
            self.dg_panel.clear_dirty()

    @staticmethod
    def _dg_validate_references(desired):
        """'' if the reference graph is sane, else why it is not.

        A channel referenced to itself, or a loop such as B->D->B, would make
        the timing unresolvable (and the shot row's pulse spacing blank).
        """
        for name, entry in desired.items():
            if channel_name(entry.get("ref")) == name:
                return f"Channel {name} is referenced to itself."
        unresolved = [n for n, v in resolve_absolute_delays(desired).items() if v is None]
        if unresolved:
            return ("Circular or unresolvable reference chain for: "
                    + ", ".join(sorted(unresolved)))
        return ""

    def on_dg_disconnect(self):
        try:
            self.dg.close()
        except:
            pass
        self.dg_panel.lamp.set_status("red", "Disconnected")
        self.dg_panel.set_status("Not connected")
        self.log("[DG535] Disconnected")


    # ------------------------------------------------------------------
    #  BNC575 Handlers
    # ------------------------------------------------------------------
    def on_bnc_connect(self):
        port = "COM5"
        try:
            self.set_status("yellow", f"Connecting BNC575 on {port}...")
            self.log(f"[BNC575] Connecting on {port}...")
            self.bnc.connect(port=port)
            self.bnc_connected = True

            idn = self.bnc.identify()
            save_memory("BNC575_COM", port)

            self.set_status("green", "BNC575 connected")
            self.log(f"[BNC575] Connected: {idn}")
            self.bnc_panel.lamp.set_status("green", "Connected")
            self.bnc_panel.set_connected(True, idn)

            self._bnc_read_all_settings()

        except Exception as e:
            self.bnc_connected = False
            self.set_status("red", "BNC575 connection failed")
            self.log(f"[BNC575 ERROR] {e}")
            self.bnc_panel.set_connected(False)
            self.error_popup("BNC575 Error", str(e))


    def on_bnc_disconnect(self):
        try:
            self.bnc.close()
        except:
            pass
        self.bnc_panel.lamp.set_status("red", "Disconnected")
        self.bnc_panel.set_connected(False)
        self.log("[BNC575] Disconnected")
        self.bnc_connected = False

    def on_bnc_apply(self):
        if not self.bnc_connected:
            self.error_popup("BNC575", "Not connected")
            return
            
        try:
            wA = self.bnc_panel.get_widthA()
            dA = self.bnc_panel.get_delayA()
            wB = self.bnc_panel.get_widthB()
            dB = self.bnc_panel.get_delayB()
            wC = self.bnc_panel.get_widthC()
            dC = self.bnc_panel.get_delayC()
            wD = self.bnc_panel.get_widthD()
            dD = self.bnc_panel.get_delayD()

            self.bnc.apply_settings(wA, dA, wB, dB, wC, dC, wD, dD)
            
            period = self.bnc_panel.get_period()
            self.bnc.set_period(period)
            
            self.data_logger.log_bnc575_config(wA, dA, wB, dB, wC, dC, wD, dD)

            self.log(f"[BNC575] Settings applied:")
            self.log(f"  A: w={wA:.3e}s, d={dA:.3e}s")
            self.log(f"  B: w={wB:.3e}s, d={dB:.3e}s")
            self.log(f"  C: w={wC:.3e}s, d={dC:.3e}s")
            self.log(f"  D: w={wD:.3e}s, d={dD:.3e}s")
            self.log(f"  Period: {period:.3e}s")
            # Re-read so the cached config is what the instrument holds, not
            # what the spin boxes say. Connect/apply only, never at fire time.
            self._bnc_read_all_settings()
            self.set_status("green", "BNC575 settings applied")

        except Exception as e:
            self.set_status("red", "BNC575 apply failed")
            self.log(f"[BNC575 ERROR] {e}")
            self.data_logger.log_error("BNC575", str(e))
            self.error_popup("BNC575 Error", str(e))

    def on_bnc_read(self):
        if not self.bnc_connected:
            self.error_popup("BNC575", "Not connected")
            return
            
        try:
            self._bnc_read_all_settings()
            self.set_status("green", "BNC575 settings read")

        except Exception as e:
            self.set_status("red", "BNC575 read failed")
            self.log(f"[BNC575 ERROR] {e}")
            self.error_popup("BNC575 Read Error", str(e))

    def on_bnc_arm(self):
        if not self.bnc_connected:
            self.error_popup("BNC575", "Not connected")
            return
            
        try:
            source = self.bnc_panel.get_trigger_source()
            slope = self.bnc_panel.get_trigger_slope()
            level = self.bnc_panel.get_trigger_level()

            if not self.bnc_trigger_armed:
                self.bnc.set_trigger_settings(source, slope, level)
                self.bnc.arm_trigger()
                self.bnc_trigger_armed = True
                self.system_state.update("bnc575", {"armed": True})
                self.bnc_panel.btn_arm.setText("Disarm (EXT TRIG)")
                self.data_logger.log_bnc575_arm(level)
                self.set_status("green", "BNC575 armed (EXT)")
                self.log(f"[BNC575] Armed for external trigger: {source}/{slope} @ {level:.2f} V")
            else:
                self.bnc.disarm_trigger()
                self.bnc_trigger_armed = False
                self.system_state.update("bnc575", {"armed": False})
                self.bnc_panel.btn_arm.setText("Arm (EXT TRIG)")
                self.set_status("yellow", "BNC575 disarmed")
                self.log("[BNC575] Disarmed external trigger")
        except Exception as e:
            self.set_status("red", "BNC575 arm failed")
            self.log(f"[BNC575 ERROR] {e}")
            self.data_logger.log_error("BNC575", str(e))
            self.error_popup("BNC575 Arm Error", str(e))


    def on_bnc_fire(self):
        if not self.bnc_connected:
            self.error_popup("BNC575", "Not connected")
            self.data_logger.log_fire_blocked("bnc575_not_connected")
            return

        # Cached state only: nothing is queried in the fire path.
        #
        # fire_internal() sends :PULSE0:MODE SING then :PULSE0:STATE ON and
        # never touches :PULSE0:TRIG:MODE. In TRIG/DUAL mode that just re-arms
        # the unit to wait for an external edge, so no t0 is produced - a
        # missed shot that would still consume a shot number.
        bnc_state = self.system_state.get("bnc575")
        cached_mode = str(bnc_state.get("trigger_mode", "") or "").upper()
        if cached_mode in ("TRIG", "TRIGGERED", "DUAL") or bnc_state.get("armed"):
            detail = (f"cached trigger mode {cached_mode or UNKNOWN}, "
                      f"armed={bnc_state.get('armed')}")
            self.log(f"[BNC575] Fire BLOCKED - {detail}")
            self.data_logger.log_fire_blocked(
                "bnc575_in_external_trigger_mode", detail)
            self.error_popup(
                "BNC575 in external trigger mode",
                "The BNC575 is set for an external trigger, so the fire "
                "command would not produce t0.\n\nDisarm it (Arm/Disarm EXT "
                "TRIG) and fire again.")
            return

        # SAFETY INTERLOCK: Ensure WJ HV supplies are OFF before firing.
        # The WJs charge the Marx and must be off at t0; the charge values
        # cached while HV was on are what the shot row reports.
        if not self.ensure_wj_hv_off():
            self.log("[BNC575] Fire ABORTED - WJ HV interlock failed")
            self.data_logger.log_fire_blocked(
                "wj_hv_off_unconfirmed", "HV could not be confirmed off")
            return

        # A connected scope that is not armed will miss this shot. Cached
        # state only, and never a reason to block: the shot goes ahead and the
        # row records which scopes were not ready.
        unarmed = [f"rigol{sid}" for sid in (1, 2, 3)
                   if getattr(self, f"rigol{sid}_connected", False)
                   and not (self.system_state.get(f"rigol{sid}") or {}).get("armed")]
        notes = ""
        if unarmed:
            notes = "scopes not armed at t0: " + ", ".join(unarmed)
            self.log(f"[BNC575] WARNING: {notes} - they will miss this shot")
            self.data_logger.log_error("Shot", notes)

        try:
            self.set_status("yellow", "Firing BNC575 internal pulse...")
            # ================= MASTER SHOT (t0) =================
            # This is the only shot command the PC sends. Trigger chain:
            #   BNC575 fire  = t0
            #     channel A -> screen room DG535 (NOT connected to this PC),
            #                  whose A output at 180 us triggers the Marx
            #                  trigger generator
            #     channel B -> laser DG535 (self.dg, GPIB 15 over Prologix),
            #                  A = laser 1 flashlamp, B = laser 1 Q-switch,
            #                  C = laser 2 flashlamp, D = laser 2 Q-switch
            # Nothing is queried between here and the trigger: the snapshot is
            # built from cached state only, and the shot number is written
            # immediately after the command returns.
            self.bnc.fire_internal()
            self._record_shot(notes=notes)
            self.data_logger.log_bnc575_pulse(mode='INTERNAL')
            self.set_status("green", "BNC575 internal fired")
            self.log("[BNC575] Internal pulse fired.")
        except Exception as e:
            self.set_status("red", "BNC575 fire failed")
            self.log(f"[BNC575 ERROR] {e}")
            self.data_logger.log_error("BNC575", str(e))
            self.error_popup("BNC575 Fire Error", str(e))

    def on_bnc_apply_trigger(self):
        if not self.bnc_connected:
            self.error_popup("BNC575", "Not connected")
            return
            
        try:
            source = self.bnc_panel.get_trigger_source()
            slope = self.bnc_panel.get_trigger_slope()
            level = self.bnc_panel.get_trigger_level()
            
            self.bnc.set_trigger_settings(source, slope, level)
            self.log(f"[BNC575] Trigger settings applied: {source}, {slope}, {level:.2f} V")
            self.set_status("green", "Trigger settings applied")
        except Exception as e:
            self.log(f"[BNC575 ERROR] {e}")
            self.error_popup("BNC575 Trigger Error", str(e))

    def on_bnc_apply_system(self):
        if not self.bnc_connected:
            self.error_popup("BNC575", "Not connected")
            return
            
        try:
            mode_str = self.bnc_panel.get_system_mode()
            mode_map = {
                "NORM": SystemMode.CONTINUOUS,
                "SING": SystemMode.SINGLE,
                "BURS": SystemMode.BURST,
                "DCYC": SystemMode.DUTY_CYCLE
            }
            mode = mode_map.get(mode_str, SystemMode.CONTINUOUS)
            
            self.bnc.set_system_mode(mode)
            
            period = self.bnc_panel.get_period()
            self.bnc.set_period(period)
            
            if mode == SystemMode.BURST and hasattr(self.bnc_panel, 'burst_count'):
                count = self.bnc_panel.burst_count.value()
                self.bnc.set_burst_count(count)
                self.log(f"[BNC575] System: mode={mode_str}, period={period:.6e}s, burst={count}")
            else:
                self.log(f"[BNC575] System: mode={mode_str}, period={period:.6e}s")
            
            self.set_status("green", "System settings applied")
            
        except Exception as e:
            self.log(f"[BNC575 ERROR] {e}")
            self.error_popup("BNC575 System Error", str(e))

    def on_bnc_enable_channel(self, channel: str):
        if not self.bnc_connected:
            return
            
        try:
            enabled = self.bnc_panel.is_channel_enabled(channel)
            self.bnc.set_channel_state(channel, enabled)
            self.log(f"[BNC575] Channel {channel} {'ENABLED' if enabled else 'DISABLED'}")
        except Exception as e:
            self.log(f"[BNC575 ERROR] {e}")
            self.error_popup("BNC575 Channel Error", str(e))

    def on_bnc_enable_trigger(self):
        if not self.bnc_connected:
            return
            
        try:
            enabled = self.bnc_panel.is_trigger_enabled()
            self.bnc.enable_trigger(enabled)
            self.log(f"[BNC575] Trigger output {'ENABLED' if enabled else 'DISABLED'}")
        except Exception as e:
            self.log(f"[BNC575 ERROR] {e}")
            self.error_popup("BNC575 Trigger Error", str(e))

    def on_bnc_store(self):
        if not self.bnc_connected:
            self.error_popup("BNC575", "Not connected")
            return
            
        try:
            location = self.bnc_panel.store_location.value()
            self.bnc.store_config(location)
            self.log(f"[BNC575] Stored config to location {location}")
            self.set_status("green", f"Config stored to {location}")
        except Exception as e:
            self.log(f"[BNC575 ERROR] {e}")
            self.error_popup("BNC575 Store Error", str(e))

    def on_bnc_recall(self):
        if not self.bnc_connected:
            self.error_popup("BNC575", "Not connected")
            return
            
        try:
            location = self.bnc_panel.store_location.value()
            self.bnc.recall_config(location)
            self._bnc_read_all_settings()
            self.log(f"[BNC575] Recalled config from location {location}")
            self.set_status("green", f"Config recalled from {location}")
        except Exception as e:
            self.log(f"[BNC575 ERROR] {e}")
            self.error_popup("BNC575 Recall Error", str(e))

    def on_bnc_factory_reset(self):
        if not self.bnc_connected:
            self.error_popup("BNC575", "Not connected")
            return
            
        reply = QMessageBox.question(
            self, "Factory Reset",
            "Reset BNC575 to factory defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
            
        try:
            self.bnc.recall_defaults()
            self._bnc_read_all_settings()
            self.log("[BNC575] Reset to factory defaults")
            self.set_status("green", "Factory reset complete")
        except Exception as e:
            self.log(f"[BNC575 ERROR] {e}")
            self.error_popup("BNC575 Reset Error", str(e))


    # ------------------------------------------------------------------
    #  Rigol Handlers
    # ------------------------------------------------------------------
    def on_rigol1_connect(self):
        try:
            self.set_status("yellow", "Connecting Rigol #1...")
            self.rigol1.connect()
            idn = self.rigol1._query("*IDN?")
            save_memory("Rigol1_VISA", self.rigol1.resource_name)
            self.rigol1_connected = True

            self.set_status("green", "Rigol #1 connected")
            self.log(f"[Rigol1] {idn}")
            self.rigol_panel.lamp_r1.set_status("green", "Connected")
        except Exception as e:
            self.rigol1_connected = False
            self.set_status("red", "Rigol #1 connection failed")
            self.log(f"[Rigol1 ERROR] {e}")
            self.error_popup("Rigol #1 Error", str(e))

    def on_rigol2_connect(self):
        try:
            self.set_status("yellow", "Connecting Rigol #2...")
            self.rigol2.connect()
            idn = self.rigol2._query("*IDN?")
            save_memory("Rigol2_VISA", self.rigol2.resource_name)
            self.rigol2_connected = True
            self.set_status("green", "Rigol #2 connected")
            self.log(f"[Rigol2] {idn}")
            self.rigol_panel.lamp_r2.set_status("green", "Connected")
        except Exception as e:
            self.rigol2_connected = False
            self.set_status("red", "Rigol #2 connection failed")
            self.log(f"[Rigol2 ERROR] {e}")
            self.error_popup("Rigol #2 Error", str(e))

    def on_rigol3_connect(self):
        try:
            self.set_status("yellow", "Connecting Rigol #3...")
            self.rigol3.connect()
            idn = self.rigol3._query("*IDN?")
            save_memory("Rigol3_VISA", self.rigol3.resource_name)
            self.rigol3_connected = True
            self.set_status("green", "Rigol #3 connected")
            self.log(f"[Rigol3] {idn}")
            self.rigol_panel.lamp_r3.set_status("green", "Connected")
        except Exception as e:
            self.rigol3_connected = False
            self.set_status("red", "Rigol #3 connection failed")
            self.log(f"[Rigol3 ERROR] {e}")
            self.error_popup("Rigol #3 Error", str(e))


    def on_capture_r1(self):
        """Capture 4 channels from Rigol #1"""
        if not self.rigol1_connected:
            self.error_popup("Rigol #1", "Not connected.")
            return
        self.start_four_channel_capture(self.rigol1, "Rigol #1", 1)


    def on_capture_r2(self):
        """Capture 4 channels from Rigol #2"""
        if not self.rigol2_connected:
            self.error_popup("Rigol #2", "Not connected.")
            return
        self.start_four_channel_capture(self.rigol2, "Rigol #2", 2)


    def on_capture_r3(self):
        """Capture 4 channels from Rigol #3"""
        if not self.rigol3_connected:
            self.error_popup("Rigol #3", "Not connected.")
            return
        self.start_four_channel_capture(self.rigol3, "Rigol #3", 3)

    # A scope may sit armed for a long time between arming and the shot.
    _CAPTURE_TIMEOUT_S = 1800.0

    def start_four_channel_capture(self, rigol, name, scope_id):
        """Start a 4-channel capture worker for a scope"""
        self.set_status("yellow", f"Capturing {name} (4 channels)...")
        self.log(f"[{name}] armed, waiting up to "
                 f"{self._CAPTURE_TIMEOUT_S / 60:.0f} min for the trigger...")
        self._set_capture_state(scope_id, "armed")
        self.system_state.update(f"rigol{scope_id}", {
            "connected": True, "armed": True, "capture_ok": None,
        }, source=SOURCE_COMMANDED)

        worker = CaptureFourChannelWorker(
            rigol, name, timeout=self._CAPTURE_TIMEOUT_S)
        worker.finished.connect(lambda data, nm: self.on_four_channel_capture_finished(data, nm, scope_id))
        worker.error.connect(lambda msg, nm, sid=scope_id: self.on_single_capture_error(msg, nm, sid))

        # Store worker reference to prevent garbage collection
        setattr(self, f'capture_worker_{scope_id}', worker)
        worker.start()
        self._start_capture_countdown(scope_id, self._CAPTURE_TIMEOUT_S)

    def _start_capture_countdown(self, scope_id, timeout_s):
        """Show the remaining trigger wait in the capture status strip."""
        if not hasattr(self, "_capture_deadlines"):
            self._capture_deadlines = {}
        self._capture_deadlines[scope_id] = time.monotonic() + timeout_s
        timer = getattr(self, "_capture_countdown_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setInterval(1000)
            timer.timeout.connect(self._tick_capture_countdown)
            self._capture_countdown_timer = timer
        if not timer.isActive():
            timer.start()
        self._tick_capture_countdown()

    def _tick_capture_countdown(self):
        now = time.monotonic()
        for scope_id, deadline in list(getattr(self, "_capture_deadlines", {}).items()):
            remaining = deadline - now
            if remaining <= 0:
                self._capture_deadlines.pop(scope_id, None)
                self._set_capture_state(scope_id, "error", "trigger timeout")
                continue
            self._set_capture_state(
                scope_id, "armed",
                f"waiting {int(remaining // 60)}:{int(remaining % 60):02d}")
        if not getattr(self, "_capture_deadlines", None):
            timer = getattr(self, "_capture_countdown_timer", None)
            if timer is not None:
                timer.stop()

    def _stop_capture_countdown(self, scope_id):
        deadlines = getattr(self, "_capture_deadlines", None)
        if deadlines:
            deadlines.pop(scope_id, None)
        if not deadlines:
            timer = getattr(self, "_capture_countdown_timer", None)
            if timer is not None:
                timer.stop()

    def _finish_pending_capture(self, scope_id):
        """Log SCOPE_ALL once every scope armed by Capture All has finished.

        This used to live at the end of the old inline capture-all loop; the
        scopes now finish in background workers, so the event is raised here.
        """
        pending = getattr(self, "_pending_capture_ids", None)
        if not pending:
            return
        pending.discard(scope_id)
        if not pending:
            self.data_logger.log_scope_all_capture()
            self.log("[CAPTURE] All armed scopes have finished.")

    def on_four_channel_capture_finished(self, data, name, scope_id):
        """Handle 4-channel capture completion"""
        self._stop_capture_countdown(scope_id)
        (t1, v1), (t2, v2), (t3, v3), (t4, v4) = data
        # Store data for export
        self.current_data = data  # ← ADD THIS LINE
        self.captured_scopes[scope_id] = data
        self._mark_captures_dirty()

        # Update the appropriate plot
        if scope_id == 1:
            self.scope_window.update_r1(t1, v1, t2, v2, t3, v3, t4, v4)
        elif scope_id == 2:
            self.scope_window.update_r2(t1, v1, t2, v2, t3, v3, t4, v4)
        elif scope_id == 3:
            self.scope_window.update_r3(t1, v1, t2, v2, t3, v3, t4, v4)

        # Log capture (count non-empty channels). A capture that finishes
        # after the shot row was written is tied to the shot by this event's
        # shot number rather than by rewriting the CSV row.
        ch_counts = [len(t1), len(t2), len(t3), len(t4)]
        self.data_logger.log_scope_capture(
            scope_id, ch_counts[0], ch_counts[1],
            shot_number=self._current_shot_number if self._current_shot_number else '')
        self.system_state.update(f"rigol{scope_id}", {
            "armed": False,
            "capture_ok": True,
            "file": Path(self.data_logger.scope_export_path(
                scope_id, shot_index=self.shot_logger.session_shot_index)).name,
        }, source=SOURCE_READBACK)

        self.set_status("green", f"{name} captured (4 ch)")
        self._set_capture_state(scope_id, "done", f"{max(len(t1), len(t2), len(t3), len(t4))} pts")
        self._finish_pending_capture(scope_id)
        self.log(f"[{name}] 4-channel capture complete. Points: CH1={len(t1)}, CH2={len(t2)}, CH3={len(t3)}, CH4={len(t4)}")

    def on_r1_disconnect(self):
        try:
            self.rigol1.disconnect()
        except:
            pass
        self.rigol_panel.lamp_r1.set_status("red", "Disconnected")
        self.log("[Rigol1] Disconnected")
        self.rigol1_connected = False

    def on_r2_disconnect(self):
        try:
            self.rigol2.disconnect()
        except:
            pass
        self.rigol_panel.lamp_r2.set_status("red", "Disconnected")
        self.log("[Rigol2] Disconnected")
        self.rigol2_connected = False

    def on_r3_disconnect(self):
        try:
            self.rigol3.disconnect()
        except:
            pass
        self.rigol_panel.lamp_r3.set_status("red", "Disconnected")
        self.log("[Rigol3] Disconnected")
        self.rigol3_connected = False


    def on_single_capture_error(self, msg, name, scope_id=None):
        self.set_status("red", f"{name} error")
        if scope_id is not None:
            self._stop_capture_countdown(scope_id)
            self._set_capture_state(scope_id, "error")
            self.system_state.update(f"rigol{scope_id}", {
                "armed": False, "capture_ok": False,
            }, source=SOURCE_READBACK)
            self._finish_pending_capture(scope_id)
        self.error_popup(f"{name} Capture Error", msg)
        self.log(f"[{name} ERROR] {msg}")


    def on_capture_all_scopes(self):
        """Arm all three scopes for the next shot. Arming only.

        This used to turn HV off, arm the BNC575 for an external trigger,
        configure the DG535 (configure_pulse_A -> set_single_shot) and
        software fire it. None of that happens here any more:

          * nothing is written to the laser DG535 - it stays externally
            triggered by BNC575 channel B at all times
          * the BNC575 is not armed for an external trigger, which would stop
            its own fire command from producing t0
          * HV is not touched. Arming scopes must not change the HV state; the
            HV interlock lives in on_bnc_fire, the only shot path.

        Each scope then waits for its trigger in a background worker, so the
        GUI stays responsive until the shot. SCOPE_ALL is logged by
        _finish_pending_capture once every armed scope has finished.
        """
        self.set_status("yellow", "Arming scopes...")
        self.log("[CAPTURE] Arming all connected scopes (SINGLE)...")

        armed = []
        self._pending_capture_ids = set()
        try:
            for scope_id, (scope, connected) in enumerate(
                    ((self.rigol1, self.rigol1_connected),
                     (self.rigol2, self.rigol2_connected),
                     (self.rigol3, self.rigol3_connected)), start=1):
                if not connected:
                    self._set_capture_state(scope_id, "idle")
                    continue
                scope.stop()
                scope.single()
                self.data_logger.log_scope_arm(scope_id)
                # Starts the background worker and marks the scope armed.
                self.start_four_channel_capture(
                    scope, f"Rigol #{scope_id}", scope_id)
                self._pending_capture_ids.add(scope_id)
                armed.append(f"Rigol #{scope_id}")
        except Exception as e:
            self.error_popup("Rigol Error", f"Failed to arm scopes: {e}")
            self.data_logger.log_error("SCOPE", str(e))
            return

        if armed:
            self.set_status("green", f"Armed: {', '.join(armed)}")
            self.log(f"[CAPTURE] {', '.join(armed)} armed and waiting. "
                     f"Press BNC575 Fire to shoot.")
        else:
            self.set_status("yellow", "No scopes connected")
            self.log("[CAPTURE] No connected scopes to arm.")


    def on_r1_single(self):
        try:
            if self.rigol1_connected:
                self.rigol1.single()
                self.log("[Rigol1] Set to SINGLE")
                self.set_status("green", "Rigol1 SINGLE")
            else:
                self.error_popup("Rigol1", "Not connected.")
        except Exception as e:
            self.error_popup("Rigol1 Error", str(e))

    def on_r2_single(self):
        try:
            if self.rigol2_connected:
                self.rigol2.single()
                self.log("[Rigol2] Set to SINGLE")
                self.set_status("green", "Rigol2 SINGLE")
            else:
                self.error_popup("Rigol2", "Not connected.")
        except Exception as e:
            self.error_popup("Rigol2 Error", str(e))

    def on_r3_single(self):
        try:
            if self.rigol3_connected:
                self.rigol3.single()
                self.log("[Rigol3] Set to SINGLE")
                self.set_status("green", "Rigol3 SINGLE")
            else:
                self.error_popup("Rigol3", "Not connected.")
        except Exception as e:
            self.error_popup("Rigol3 Error", str(e))


    # ------------------------------------------------------------------
    #  WJ HV POWER SUPPLY HANDLERS
    # ------------------------------------------------------------------
    def ensure_wj_hv_off(self, max_retries: int = 5, retry_delay: float = 0.3) -> bool:
        """
        Safety interlock: Turn off HV on all connected WJ supplies and verify.

        Returns True if all connected supplies confirm HV is OFF.
        Returns True if no supplies are connected (nothing to interlock).
        Returns False if any supply fails to confirm HV OFF after retries.
        """
        import time

        # Check which WJ units are connected
        connected_units = []
        for i, wj in enumerate(self.wj_units):
            if wj.is_connected:
                connected_units.append((i, wj))

        if not connected_units:
            self.log("[SAFETY] No WJ supplies connected - proceeding")
            return True

        self.log(f"[SAFETY] Turning off HV on {len(connected_units)} connected WJ supply(ies)...")
        self.set_status("yellow", "Turning off HV supplies...")

        # Send HV OFF to all connected units
        for i, wj in connected_units:
            try:
                resp = wj.hv_off_pulse()
                self.log(f"[WJ{i+1}] HV OFF command sent: {resp}")
            except Exception as e:
                self.log(f"[WJ{i+1} ERROR] Failed to send HV OFF: {e}")
                self.error_popup("WJ Safety Error", f"Failed to turn off WJ{i+1}: {e}")
                return False

        # Give supplies time to respond
        time.sleep(0.1)

        # Verify HV is off on all units with retries
        for i, wj in connected_units:
            hv_confirmed_off = False

            for attempt in range(max_retries):
                try:
                    data = wj.query()

                    if data.get("type") != "R":
                        self.log(f"[WJ{i+1}] Query returned non-R packet: {data}")
                        time.sleep(retry_delay)
                        continue

                    hv_on = data.get("hv_on", True)  # Default to True (unsafe) if missing

                    if not hv_on:
                        self.log(f"[WJ{i+1}] HV confirmed OFF (attempt {attempt + 1})")
                        hv_confirmed_off = True
                        break
                    else:
                        self.log(f"[WJ{i+1}] HV still ON, retrying... (attempt {attempt + 1}/{max_retries})")
                        # Send another HV OFF command
                        wj.hv_off_pulse()
                        time.sleep(retry_delay)

                except Exception as e:
                    self.log(f"[WJ{i+1} ERROR] Query failed: {e}")
                    time.sleep(retry_delay)

            if not hv_confirmed_off:
                self.log(f"[WJ{i+1}] FAILED to confirm HV OFF after {max_retries} attempts!")
                self.error_popup("WJ Safety Error",
                    f"WJ{i+1} failed to confirm HV OFF.\nFiring aborted for safety.")
                self.set_status("red", f"WJ{i+1} HV OFF failed - ABORT")
                return False

        self.log("[SAFETY] All WJ supplies confirmed HV OFF - safe to fire")
        return True

    # GUI unit index -> supply key in instruments/glassman_id.py.
    _WJ_SUPPLY_KEYS = ("NEG", "POS")   # WJ1 = negative, WJ2 = positive

    def _identify_wj_port(self, index, port):
        """Confirm the supply on `port` really is WJ{index+1} before connecting.

        Polarity comes from the USB serial each supply's own chip reports
        (SUPPLIES in instruments/glassman_id.py). That serial follows the
        supply to any socket; COM numbers and hub locations do not, and these
        two supplies have been seen swapping hub locations. The WJ protocol
        itself cannot report polarity, model or serial number.

        Returns the firmware version (logged, not matched on). Raises IOError
        if the port is gone, holds the other supply, or never answers.
        """
        key = self._WJ_SUPPLY_KEYS[index]
        p = next((p for p in list_ports.comports() if p.device == port), None)
        if p is None:
            raise IOError(f"{port} is not present")
        if not wj_matches(p, WJ_SUPPLIES[key]):
            actual = p.serial_number or ""
            other = next((k for k, rule in WJ_SUPPLIES.items() if wj_matches(p, rule)), None)
            raise IOError(
                f"{port} has USB serial {actual!r}; WJ{index+1} is the {key} supply"
                + (f" and {port} is the {other} supply" if other else ""))
        self.wj_units[index].close()   # release the port if this unit already holds it
        version = wj_read_version(port)
        if version is None:
            raise IOError(f"no WJ reply on {port}")
        return version

    def on_wj_connect(self, index, port_override=None):
        row = self.wj_panel.rows[index]
        port = port_override or row.port_combo.currentText()

        if port_override:
            row.port_combo.setCurrentText(port)

        if port == "No COM ports":
            self.log(f"[WJ{index+1}] No ports available")
            row.lamp.set_status("red", "No Ports")
            return

        try:
            self.log(f"[WJ{index+1}] Connecting on {port}...")
            fw = self._identify_wj_port(index, port)
            self.wj_units[index].connect(port)
            save_memory(f"WJ{index+1}_COM", port)
            row.lamp.set_status("green", "Connected")
            self.log(f"[WJ{index+1}] Connected on {port}, firmware {fw}")
        except Exception as e:
            self.log(f"[WJ{index+1} ERROR] {e}")
            row.lamp.set_status("red", "Error")


    def on_wj_hv_on(self):
        # Interlock: energize charging relay (NO→closed) and discharging relay (NC→open)
        self._relay_set(self._RELAY_CHARGING,    True)
        self._relay_set(self._RELAY_DISCHARGING, True)

        # Send V/I + HV_ON in ONE packet so we make only one round-trip per
        # supply per click — anything more collides with the WJ reader
        # thread's Q polls. Voltage is the spinbox value; current is each
        # supply's MAX (matches Apply Program behavior).
        kv = self.wj_panel.voltage.value()

        for i, wj in enumerate(self.wj_units):
            try:
                wj_ma = wj.imax_ma
                resp = wj.send_set(kv=kv, ma=wj_ma, hv_on=True)
                self.data_logger.log_wj_command(i+1, "HV_ON")
                self.log(f"[WJ{i+1}] HV ON @ {kv} kV, {wj_ma} mA (MAX) → {resp}")
            except Exception as e:
                self.log(f"[WJ{i+1} ERROR] {e}")
                self.data_logger.log_error(f"WJ{i+1}", str(e))

    def on_wj_hv_off(self):
        # Interlock: de-energize charging relay (NO→open), keep discharging relay energized (NC stays open)
        self._relay_set(self._RELAY_CHARGING, False)

        for i, wj in enumerate(self.wj_units):
            try:
                resp = wj.hv_off_pulse()
                self.data_logger.log_wj_command(i+1, "HV_OFF")
                self.log(f"[WJ{i+1}] HV OFF → {resp}")
            except Exception as e:
                self.log(f"[WJ{i+1} ERROR] {e}")
                self.data_logger.log_error(f"WJ{i+1}", str(e))


    def on_wj_reset(self):
        for i, wj in enumerate(self.wj_units):
            try:
                wj.reset_pulse()
                self.data_logger.log_wj_command(i+1, "RESET")
                self.log(f"[WJ{i+1}] Reset OK")
            except Exception as e:
                self.log(f"[WJ{i+1} ERROR] {e}")
                self.data_logger.log_error(f"WJ{i+1}", str(e))

    def on_wj_set_voltage(self, kv=None, ma=None):
        if kv is None:
            kv = self.wj_panel.voltage.value()
        # Current is always commanded to each WJ supply's maximum on Apply
        # Program — user wants every supply opened wide.

        for i, wj in enumerate(self.wj_units):
            try:
                wj_ma = wj.imax_ma
                resp = wj.set_program(kv, wj_ma)
                self.data_logger.log_wj_command(i+1, "SET_PROGRAM", f"{kv}kV_{wj_ma}mA")
                self.log(f"[WJ{i+1}] Set → {kv} kV, {wj_ma} mA (MAX) ({resp})")
            except Exception as e:
                self.log(f"[WJ{i+1} ERROR] {e}")
                self.data_logger.log_error(f"WJ{i+1}", str(e))


    def on_wj_disconnect(self, index):
        try:
            self.wj_units[index].close()
        except:
            pass

        self.wj_panel.rows[index].lamp.set_status("red", "Disconnected")
        self.log(f"[WJ{index+1}] Disconnected")


    def on_wj_read(self):
        all_good = bool(self.wj_units)
        for i, wj in enumerate(self.wj_units):
            try:
                data = wj.query()
                self.log(f"[WJ{i+1}] Readback: {data}")

                row = self.wj_panel.rows[i]

                if data.get("type") != "R":
                    row.label_status.setText("No R packet")
                    all_good = False
                    continue

                if data.get("fault", False):
                    all_good = False

                kv = data.get("kv", 0.0)
                ma = data.get("ma", 0.0)
                hv = data.get("hv_on", False)
                fault = data.get("fault", False)

                try:
                    self.data_logger.log_wj_voltage(i+1, kv, ma, hv, fault)
                except Exception as e:
                    self.log(f"[DataLogger ERROR] Failed to log WJ{i+1} data: {e}")

                self._cache_wj_packet(i, data)

                row.label_status.setText(
                    f"{kv:.2f} kV | {ma:.3f} mA | "
                    f"HV={'ON' if hv else 'OFF'} | "
                    f"Fault={'YES' if fault else 'NO'}"
                )

            except Exception as e:
                self.log(f"[WJ{i+1} ERROR] {e}")
                self.data_logger.log_error(f"WJ{i+1}", str(e))
                row = self.wj_panel.rows[i]
                row.label_status.setText("Read Error")
                all_good = False

        # Interlock step 3: valid readback (R packet, no fault) from every
        # supply means the programmed voltage is applied and healthy.
        if all_good:
            self._mark_interlock(3, "power supplies read back OK")


    # ------------------------------------------------------------------
    #  Shot snapshot, state caches and shutdown
    # ------------------------------------------------------------------
    def _update_next_shot_label(self):
        """Show the number the next shot will get (and any counter warning)."""
        label = getattr(self, "lbl_next_shot", None)
        if label is None:
            return
        try:
            nxt = self.shot_logger.peek_next_shot_number()
        except Exception:
            nxt = "?"
        if self.shot_logger.counter_available:
            label.setText(f"Next shot: {nxt}")
            label.setStyleSheet("font-weight:bold;")
        else:
            label.setText(f"Next shot: {nxt}  (COUNTER LOCKED)")
            label.setStyleSheet(
                "font-weight:bold; background-color:#C62828; color:white;"
                " padding:2px 6px; border-radius:3px;")

    def _update_interlock_state(self):
        """Cache the interlock picture for the shot row."""
        labels = dict(self._INTERLOCK_STEPS)
        failed = [labels.get(i, str(i))
                  for i, ok in self.interlock_passed.items() if not ok]
        manual = [labels.get(i, str(i))
                  for i, chk in self.interlock_manual.items() if chk.isChecked()]
        self.system_state.update("interlocks", {
            "master_pass": not failed,
            "failed": failed,
            "manual": manual,
            "steps": dict(self.interlock_passed),
        }, source=SOURCE_READBACK)

    def _cache_wj_packet(self, unit_index, data):
        """Store one WJ Q reply in the system state.

        program_kv is the last value this GUI commanded (v_set_kv): the WJ
        protocol cannot read the programmed setpoint back, only the measured
        output, so it is commanded state, not confirmed.
        """
        unit = f"wj{unit_index + 1}"
        kv = data.get("kv")
        ma = data.get("ma")
        hv_on = data.get("hv_on")
        fault = data.get("fault")
        values = {
            "measured_kv": kv,
            "current_ma": ma,
            "hv_on": hv_on,
            "fault": fault,
            "connected": True,
            "program_kv": getattr(self.wj_units[unit_index], "v_set_kv", None),
        }
        # Keep the last readback taken while HV was still on. The fire path
        # dumps HV before the trigger, so these are the charge values.
        if hv_on:
            values["charge_kv"] = kv
            values["charge_ma"] = ma
            values["charge_monotonic"] = time.monotonic()
        self.system_state.update(unit, values, source=SOURCE_READBACK)

    def on_wj_packet(self, unit_index, data):
        """Full Q reply from a WJ reader thread (kV, mA, HV state, fault)."""
        if data.get("type") != "R":
            return
        self._cache_wj_packet(unit_index, data)
        try:
            self.data_logger.log_wj_voltage(
                unit_index + 1, data.get("kv", 0.0), data.get("ma", 0.0),
                data.get("hv_on", False), data.get("fault", False))
        except Exception as e:
            self._deferred_log(f"[DataLogger ERROR] WJ{unit_index+1}: {e}")

    def _record_relay_state(self, channel, state, ok=True):
        """Log a relay command and cache the commanded state.

        The Numato driver's get_state() returns its own software cache, not a
        hardware read, so a relay state is only ever "commanded" here. Nothing
        claims it was confirmed.
        """
        name = self._RELAY_NAMES.get(channel, f"ch{channel}")
        try:
            self.data_logger.log_relay_command(name, channel, state, ok=ok, confirmed=None)
        except Exception:
            pass
        states = dict((self.system_state.get("relays") or {}).get("states", {}))
        states[name] = bool(state) if ok else None
        self.system_state.update(
            "relays", {"states": states, "source": "commanded"}, source=SOURCE_COMMANDED)
        try:
            self.data_logger.log_relay_state(states, source="commanded")
        except Exception:
            pass

    def _dg_read_all_settings(self):
        """Read the laser DG535 back: delays, references and trigger mode.

        Runs at connect, from the Read Back button, and after every Apply.
        Never in the fire path. Channel map on this system: A = laser 1
        flashlamp, B = laser 1 Q-switch, C = laser 2 flashlamp, D = laser 2
        Q-switch. Each delay is relative to a reference channel (the unit
        currently has B referenced to A and D to C), so the shot row resolves
        every chain back to T0 before comparing.

        Returns True if the readback succeeded.
        """
        from instruments.dg535 import Channel
        ids = {"A": Channel.A, "B": Channel.B, "C": Channel.C, "D": Channel.D}
        try:
            channels = {}
            for name, ch_id in ids.items():
                ref, delay = self.dg.get_delay(ch_id)
                channels[name] = {"ref": ref, "delay_s": delay}
            try:
                mode = self.dg.get_trigger_mode()
                mode_name = getattr(mode, "name", str(mode))
            except Exception:
                mode_name = UNKNOWN

            self.system_state.update("dg535_laser", {
                "channels": channels,
                "trigger_mode": mode_name,
            }, source=SOURCE_READBACK)
            self._dg_last_readback = {n: dict(c) for n, c in channels.items()}

            # Fill the panel with what the instrument actually holds, and let
            # Apply compare against it.
            try:
                for name, entry in channels.items():
                    self.dg_panel.set_delay_with_reference(
                        name, channel_name(entry["ref"]) or "T0", entry["delay_s"])
                self.dg_panel.set_trigger_mode_text(mode_name)
                self.dg_panel.set_apply_enabled(True)
            except Exception as e:
                self.log(f"[DG535] Panel update failed: {e}")

            self.data_logger.log_dg535_readback(
                {n: (channel_name(c["ref"]) or c["ref"], c["delay_s"])
                 for n, c in channels.items()},
                mode_name, source="DG535_laser")
            self.log("[DG535] Laser DG535 read back: "
                     + ", ".join(f"{n}={c['delay_s'] * 1e6:.3f}us (ref "
                                 f"{channel_name(c['ref'])})"
                                 for n, c in sorted(channels.items()))
                     + f", trigger {mode_name}")
            return True
        except Exception as e:
            self.log(f"[DG535] Could not read configuration back: {e}")
            self.data_logger.log_error("DG535_laser", f"readback failed: {e}")
            return False

    def _on_laser_event(self, tag, event, payload):
        """Laser panel event, possibly from one of the panel's worker threads.

        Only the data logger and the system state are touched here (both
        lock-guarded). No widgets, because this is not always the GUI thread.
        """
        key = "laser2" if tag.strip().endswith("2") else "laser1"
        values = {k: payload[k] for k in ("armed", "interlock_ok", "fault", "state", "mode")
                  if k in payload}
        if event == "ARM":
            values.setdefault("armed", True)
        elif event == "DISARM":
            values["armed"] = False
        try:
            self.system_state.update(key, values, source=SOURCE_READBACK)
            self.data_logger.log_laser_event(
                tag, event, state=payload.get("state", ""),
                detail=payload.get("detail", ""))
        except Exception:
            pass

    def _record_shot(self, notes=""):
        """Claim the global shot number and write the frozen snapshot.

        Called immediately after the BNC575 fire command returns, never
        before. Never raises: a logging failure must not look like a failed
        shot, and the number stays consumed either way.
        """
        shot_number = None
        if not self.shot_logger.counter_available:
            # Another GUI owns the counter. The shot still happened, so it
            # still gets a row - with a blank shot number and a note.
            notes = ("; ".join(filter(None, [notes, "shot counter locked by "
                     f"another GUI instance ({self.shot_logger.counter.lock_message}); "
                     "no global shot number assigned"])))
            self.log("[SHOT] WARNING: fired, but the shot counter is locked by "
                     "another GUI instance - the row has no shot number")
            self.data_logger.log_error(
                "Shot", "counter locked by another instance; shot number not claimed")
            session_index = self.shot_logger.next_session_index()
        else:
            try:
                shot_number = self.shot_logger.claim_shot_number()
                session_index = self.shot_logger.session_shot_index
            except Exception as e:
                self.log(f"[SHOT ERROR] could not claim a shot number: {e}")
                self.data_logger.log_error("Shot", f"counter write failed: {e}")
                self.error_popup("Shot counter error",
                                 f"The shot fired but the counter could not be written:\n{e}")
                notes = "; ".join(filter(None, [notes, f"counter write failed: {e}"]))
                session_index = self.shot_logger.next_session_index()

        self._current_shot_number = shot_number
        try:
            # Freeze the state first: background threads keep updating it.
            snapshot = self.system_state.snapshot()
            now = time.monotonic()
            for unit in ("wj1", "wj2"):
                section = snapshot.get(unit) or {}
                stamped = section.get("charge_monotonic")
                if stamped is not None:
                    section["charge_age_ms"] = (now - stamped) * 1000.0

            scope_files = {}
            for sid in (1, 2, 3):
                if getattr(self, f"rigol{sid}_connected", False):
                    scope_files[sid] = Path(self.data_logger.scope_export_path(
                        sid, shot_index=session_index)).name

            row = build_shot_row(
                snapshot,
                shot_number="" if shot_number is None else shot_number,
                session_shot_index=session_index,
                datetime_str=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                timestamp_sec=self.data_logger._get_timestamp(),
                session_dir=self.data_logger.get_session_dir(),
                experiment_log_file=Path(self.data_logger.get_log_file_path()).name,
                gui_version=self.shot_logger.gui_version,
                scope_files=scope_files,
                notes=notes,
            )
            label = f"#{shot_number}" if shot_number is not None else "(no number)"
            if self.shot_logger.write_row(row):
                self.log(f"[SHOT] {label} recorded "
                         f"(shot {session_index} this session)")
            else:
                self.log(f"[SHOT ERROR] shot {label} fired but its row "
                         f"could not be written - see the logs")
                self.set_status("red", f"Shot {label}: row write FAILED")
            self.data_logger.log_shot(
                "" if shot_number is None else shot_number, session_index, notes=notes)
        except Exception as e:
            self.log(f"[SHOT ERROR] snapshot failed for shot {shot_number}: {e}")
            self.data_logger.log_error("Shot", f"snapshot failed: {e}")

        self._update_next_shot_label()
        return shot_number

    def _atexit_cleanup(self):
        """Backup for closeEvent: release the counter lock on any exit path."""
        try:
            if getattr(self, "shot_logger", None) is not None:
                self.shot_logger.close()
        except Exception:
            pass

    def on_open_scope_window(self):
        self.scope_window.show()
        self.scope_window.raise_()
        self.scope_window.activateWindow()

    def _save_captures_sync(self):
        """Write all captured scopes to rigol<N>_<session ts>.csv in the session
        folder, synchronously (on the calling thread) so the files are flushed
        before the app exits. Used by closeEvent. Returns the paths written."""
        saved = []
        for scope_id in sorted(self.captured_scopes):
            path = self.data_logger.scope_export_path(
                scope_id, shot_index=self.shot_logger.session_shot_index)
            try:
                # CSVExportWorker.run() is plain (no thread) when called directly.
                CSVExportWorker(self.captured_scopes[scope_id], path).run()
                saved.append(path)
            except Exception as e:
                self.log(f"[AUTO-SAVE] {path} failed: {e}")
        self._captures_dirty = False
        return saved

    def closeEvent(self, event):
        # Flush any captured waveforms that haven't been saved yet. The auto-save
        # timer may not have fired, or a capture happened after the last save, so
        # _captures_dirty tells us whether there is anything to write.
        self._auto_save_timer.stop()
        if hasattr(self, "_interlock_timer"):
            self._interlock_timer.stop()
        if getattr(self, "_capture_countdown_timer", None) is not None:
            self._capture_countdown_timer.stop()
        if self._captures_dirty and self.captured_scopes:
            try:
                saved_files = self._save_captures_sync()
                if saved_files:
                    self.log(f"[AUTO-SAVE] Saved on close: {', '.join(saved_files)}")
            except Exception as e:
                self.log(f"[AUTO-SAVE ERROR] Failed to save scope data: {e}")

        if hasattr(self, 'wj_workers'):
            for worker in self.wj_workers:
                if worker.isRunning():
                    worker.stop()

        if self.pressure_thread is not None:
            # Close the Modbus socket on the worker thread, then let it exit.
            self.pressure_worker.request_shutdown.emit()
            if not self.pressure_thread.wait(3000):
                self.log("[Opta] worker thread did not stop within 3 s")
            self.pressure_thread = None   # worker is deleteLater'd with the thread

        if hasattr(self, 'scope_window') and self.scope_window:
            self.scope_window.close()

        if hasattr(self, 'sf6_window') and self.sf6_window:
            self.sf6_window.close()

        # Shot logs and the counter must be complete: the GUI is usually
        # closed within seconds of a shot.
        try:
            self.data_logger.log_session_end(self.shot_logger.session_shot_index)
        except Exception as e:
            print(f"[SESSION_END failed] {e}")
        try:
            self.shot_logger.close()        # releases the counter lock
        except Exception as e:
            print(f"[shot logger close failed] {e}")

        if hasattr(self, 'data_logger') and self.data_logger:
            self.data_logger.close()

        if hasattr(self, 'laser_panel') and self.laser_panel:
            try:
                self.laser_panel.shutdown()
            except Exception as e:
                self.log(f"[Laser1] shutdown error: {e}")

        if hasattr(self, 'laser_panel2') and self.laser_panel2:
            try:
                self.laser_panel2.shutdown()
            except Exception as e:
                self.log(f"[Laser2] shutdown error: {e}")

        event.accept()
