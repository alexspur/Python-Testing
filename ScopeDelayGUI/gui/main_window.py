# gui/main_window.py
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QMessageBox, QPushButton, QSizePolicy, QGridLayout,
    QScrollArea, QFrame, QLabel, QCheckBox,
)
from PyQt6.QtCore import QThread, Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import QFileDialog, QProgressDialog, QMessageBox
from PyQt6.QtCore import Qt
import time

from gui.dg535_panel import DG535Panel
from gui.bnc575_panel import BNC575Panel
from gui.rigol_panel import RigolPanel
from gui.sf6_window import SF6Window
from gui.wj_panel import WJPanel
from gui.scope_plot_window import ScopePlotWindow
from gui.wj_plot_window import WJPlotWindow
from gui.numato_relay_panel import NumatoRelayPanel
from gui.glassman_panel import GlassmanMegaReader, GlassmanCalibrationDialog
from gui.laser_panel import LaserPanel

from utils.logger import LogPanel
from utils.status_lamp import StatusLamp
from utils.serial_tools import list_serial_ports
from utils.capture_single_worker import CaptureSingleWorker, CaptureFourChannelWorker
from utils.connect_memory import load_memory, save_memory
from utils.data_logger import DataLogger
from utils.csv_export_worker import CSVExportWorker

from instruments.dg535 import DG535Controller
from instruments.bnc575 import BNC575Controller, SystemMode, TriggerMode, TriggerEdge
from instruments.rigol import RigolScope
from instruments.wj import WJPowerSupply
from instruments.numato_relay import NumatoRelayController
from instruments.glassman import GlassmanSerial


class ScopeDelayMainWindow(QMainWindow):
    _relay_update_signal = pyqtSignal(int, bool)  # (channel, state) — safe cross-thread UI update
    _relay_log_signal = pyqtSignal(str)            # log messages from poll thread

    # Which instruments auto_connect_all() will try on startup. Any value is
    # coerced with bool(), so 1/0 and True/False both work. main.py can pass
    # an overriding dict to ScopeDelayMainWindow(auto_connect={...}).
    DEFAULT_AUTO_CONNECT = {
        "dg535":  True,
        "bnc575": True,
        "mega":   True,   # Glassman / Marx Mega
        "relay":  True,   # Numato relay module
        "wj1":    True,   # negative WJ supply
        "wj2":    True,   # positive WJ supply
        "rigol1": True,
        "rigol2": True,
        "rigol3": True,
        "laser":  True,   # Quantel CFR laser (RS-232 over USB)
    }

    def __init__(self, auto_connect=None, startup_pressure_psi=20.0,
                 hv_on_pressure_psi=20.0, hv_on_delay_sec=3.0,
                 auto_save_delay_sec=10.0, prepressurize_on_hv_on=True,
                 pressure_gauge_min=0.0, pressure_gauge_max=100.0,
                 pressure_control_max=120.0, pressure_presets=None,
                 startup_charge_kv=60.0):
        super().__init__()

        # Startup "Set Voltage" (kV) preloaded into both supplies' voltage boxes
        # (main WJ panel + SF6 window). HV ON sends this kV to both the WJ
        # supplies and the Glassman. Configurable from main.py.
        self.startup_charge_kv = startup_charge_kv

        # Default state of the "Pre-pressurize dome on HV ON" checkbox, the dome
        # pressure gauge range (PSI), the pressure setpoint max, and the quick
        # preset values. All configurable from main.py.
        self._prepressurize_default = bool(prepressurize_on_hv_on)
        self.pressure_gauge_min = pressure_gauge_min
        self.pressure_gauge_max = pressure_gauge_max
        self.pressure_control_max = pressure_control_max
        self.pressure_presets = pressure_presets

        # Merge any caller overrides over the defaults, coercing to bool so
        # 1/0/"on" style values behave.
        self.auto_connect_flags = dict(self.DEFAULT_AUTO_CONNECT)
        if auto_connect:
            for k, v in auto_connect.items():
                self.auto_connect_flags[k] = bool(v)

        # Pressure the Mega is commanded to on startup (None disables it).
        self.startup_pressure_psi = startup_pressure_psi

        # On HV ON: raise the dome to hv_on_pressure_psi, wait hv_on_delay_sec
        # for it to settle, THEN actually enable HV. _hv_on_pending guards the
        # countdown so a repeat press is ignored and an HV-off press cancels it.
        self.hv_on_pressure_psi = hv_on_pressure_psi
        self.hv_on_delay_sec = hv_on_delay_sec
        self._hv_on_pending = False

        self.setWindowTitle("Scope + Delay + SF6 Control")
        self.setGeometry(100, 100, 1700, 900)
        self.setMinimumSize(800, 600)
        self.conn = load_memory()
        self.wj_plot_window = None

        # Initialize data logger
        self.data_logger = DataLogger()

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
        # Apply the configured default for the HV-ON pre-pressurize toggle.
        self.wj_panel.chk_prepressurize.setChecked(self._prepressurize_default)
        # Preload the configured startup charge voltage.
        self.wj_panel.voltage.setValue(self.startup_charge_kv)

        self.wj_panel.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed
        )

        self.numato_relay = NumatoRelayController()

        # The Mega owns everything now (Glassman monitor/HV/setpoints, SF6
        # dome pressure on A5, Parker regulator on DAC CH1, Marx rail
        # monitors). The old Portenta (self.arduino) is gone.
        self.glassman_mega = GlassmanSerial()
        self.glassman_mega_reader: GlassmanMegaReader | None = None
        self.glassman_vmon_pin = 0.0
        self.glassman_imon_pin = 0.0
        self.glassman_hv_on = False  # last HV state from the Mega, for logging

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

        # Create SF6 window as separate top-level window (now includes WJ plots)
        self.sf6_window = SF6Window(
            pressure_gauge_min=self.pressure_gauge_min,
            pressure_gauge_max=self.pressure_gauge_max,
            pressure_control_max=self.pressure_control_max,
            pressure_presets=self.pressure_presets,
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

        # Position and show all windows on startup
        self.position_and_show_windows()

        # Log the data file location
        self.log(f"[DATA LOGGER] Saving to: {self.data_logger.get_log_file_path()}")

        # Write a test log entry to verify logging is working
        self.data_logger.log_info("SYSTEM", "GUI started successfully")
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

        # Glassman Mega COM combo (Portenta is the shared SF6 Arduino — no combo here)
        gm_combo = self.wj_panel.glassman_mega_port_combo
        prev = gm_combo.currentText()
        gm_combo.clear()
        gm_combo.addItems(ports)
        last_mega = self.conn.get("Glassman_Mega_COM", None)
        if prev in ports:
            gm_combo.setCurrentText(prev)
        elif last_mega and last_mega in ports:
            gm_combo.setCurrentText(last_mega)

    # ------------------------------------------------------------------
    #  Glassman / Mega helper (the Mega is the only controller now)
    # ------------------------------------------------------------------
    def glassman_send_mega(self, cmd: str):
        if not self.glassman_mega.is_connected:
            self.log("[Glassman] Mega not connected")
            return
        try:
            self.glassman_mega.send(cmd)
            self.log(f"[Glassman->MEGA] {cmd}")
        except Exception as e:
            self.log(f"[Glassman] Mega send error: {e}")

    def on_glassman_mega_connect(self):
        port = self.wj_panel.glassman_mega_port_combo.currentText()
        if not port or port == "No COM ports":
            self.log("[Glassman] No port selected for Mega")
            return
        try:
            self.glassman_mega.connect(port)
            self.wj_panel.glassman_mega_lamp.set_status("green", "Connected")
            self.wj_panel.glassman_mega_status.setText(f"Mega on {port}")
            save_memory("Glassman_Mega_COM", port)
            self.log(f"[Glassman] Mega connected on {port}")
            self._start_glassman_mega_reader()
        except Exception as e:
            self.wj_panel.glassman_mega_lamp.set_status("red", "Not Connected")
            self.wj_panel.glassman_mega_status.setText("Connect failed")
            self.log(f"[Glassman] Mega connect failed: {e}")

    def on_glassman_mega_disconnect(self):
        self._stop_glassman_mega_reader()
        self.glassman_mega.close()
        self.wj_panel.glassman_mega_lamp.set_status("red", "Disconnected")
        self.wj_panel.glassman_mega_status.setText("Not Connected")
        self.log("[Glassman] Mega disconnected")

    def _start_glassman_mega_reader(self):
        if self.glassman_mega_reader is not None:
            return
        self.glassman_mega_reader = GlassmanMegaReader(self.glassman_mega)
        self.glassman_mega_reader.parsed.connect(self._on_glassman_mega_parsed)
        self.glassman_mega_reader.raw_line.connect(lambda s: self.log(f"[Glassman MEGA] {s}"))
        self.glassman_mega_reader.start()

    def _stop_glassman_mega_reader(self):
        if self.glassman_mega_reader is not None:
            self.glassman_mega_reader.stop()
            self.glassman_mega_reader = None

    def _on_glassman_mega_parsed(self, d: dict):
        if "vmon_pin" in d:
            self.glassman_vmon_pin = d["vmon_pin"]
            self.wj_panel.lbl_gm_vmon_pin.setText(f"{d['vmon_pin']:.4f} V")
        if "imon_pin" in d:
            self.glassman_imon_pin = d["imon_pin"]
            self.wj_panel.lbl_gm_imon_pin.setText(f"{d['imon_pin']:.4f} V")
        if "vmon" in d:
            self.wj_panel.lbl_gm_vmon.setText(f"{d['vmon']:.3f} V")
        if "imon" in d:
            self.wj_panel.lbl_gm_imon.setText(f"{d['imon']:.3f} V")
        if "marx_pos_kv" in d:
            self.wj_panel.lbl_gm_marx_pos.setText(f"{d['marx_pos_kv']:.2f} kV")
        if "marx_pos_pin" in d:
            self.wj_panel.lbl_gm_marx_pos_pin.setText(f"({d['marx_pos_pin']:.4f} V)")
        if "marx_neg_kv" in d:
            self.wj_panel.lbl_gm_marx_neg.setText(f"{d['marx_neg_kv']:.2f} kV")
        if "marx_neg_pin" in d:
            self.wj_panel.lbl_gm_marx_neg_pin.setText(f"({d['marx_neg_pin']:.4f} V)")
        if "kv" in d:
            self.wj_panel.lbl_gm_kv.setText(f"{d['kv']:.2f} kV")
            # The "Positive" gauge in the WJ controls now shows the Glassman
            # (Mega) output instead of the unused positive WJ supply.
            try:
                self.sf6_window.kv2_gauge.update_value(d["kv"])
            except Exception:
                pass
        if "ma" in d:
            self.wj_panel.lbl_gm_ma.setText(f"{d['ma']:.4f} mA")
            try:
                self.sf6_window.ma2_gauge.update_value(d["ma"])
            except Exception:
                pass
        if "hv_on" in d:
            self.glassman_hv_on = d["hv_on"]
            if d["hv_on"]:
                self.wj_panel.lbl_gm_hv.setText("HV: ON")
                self.wj_panel.lbl_gm_hv.setStyleSheet("font-weight:bold;color:green;")
            else:
                self.wj_panel.lbl_gm_hv.setText("HV: OFF")
                self.wj_panel.lbl_gm_hv.setStyleSheet("font-weight:bold;color:red;")

        # Persist Glassman readback + Marx charge to the experiment CSV. The
        # Mega prints a full line ~2 Hz, so this logs at that cadence (same
        # idea as the WJ reader's log_wj_voltage).
        if "kv" in d or "ma" in d:
            try:
                self.data_logger.log_glassman_voltage(
                    d.get("kv", 0.0), d.get("ma", 0.0), self.glassman_hv_on
                )
            except Exception as e:
                self.log(f"[DataLogger ERROR] Glassman: {e}")
        if "marx_pos_kv" in d or "marx_neg_kv" in d:
            try:
                self.data_logger.log_marx_charge(
                    d.get("marx_pos_kv", 0.0), d.get("marx_neg_kv", 0.0)
                )
            except Exception as e:
                self.log(f"[DataLogger ERROR] Marx: {e}")

        # Pressure: the Mega's A5 reading is the sole source for the SF6
        # dome pressure gauge now that the Portenta is gone.
        if "psi" in d:
            try:
                self._latest_psi = float(d["psi"])
            except (TypeError, ValueError):
                pass
            try:
                self.sf6_window.sf6_panel.ai_ch2.update_value(d["psi"])
            except Exception:
                pass

        # Append to plot buffers if this parsed line carried kv or mA.
        if ("kv" in d or "ma" in d) and hasattr(self, "wj_start_time"):
            import time as _t
            t = _t.time() - self.wj_start_time
            self.wj_t_gm_buf.append(t)
            self.wj_kv_gm_buf.append(d.get("kv", self.wj_kv_gm_buf[-1] if self.wj_kv_gm_buf else 0.0))
            self.wj_ma_gm_buf.append(d.get("ma", self.wj_ma_gm_buf[-1] if self.wj_ma_gm_buf else 0.0))
            if len(self.wj_t_gm_buf) > self.wj_max_points:
                self.wj_t_gm_buf = self.wj_t_gm_buf[-self.wj_max_points:]
                self.wj_kv_gm_buf = self.wj_kv_gm_buf[-self.wj_max_points:]
                self.wj_ma_gm_buf = self.wj_ma_gm_buf[-self.wj_max_points:]
            try:
                self.sf6_window.kv_gm_curve.setData(self.wj_t_gm_buf, self.wj_kv_gm_buf)
                self.sf6_window.ma_gm_curve.setData(self.wj_t_gm_buf, self.wj_ma_gm_buf)
                self.sf6_window.update_wj_scroll(t)
            except Exception:
                pass

        # Append to Marx plot buffers if this parsed line carried Marx rail kV.
        if ("marx_pos_kv" in d or "marx_neg_kv" in d) and hasattr(self, "wj_start_time"):
            import time as _t
            t = _t.time() - self.wj_start_time
            self.wj_t_marx_buf.append(t)
            self.wj_marx_pos_buf.append(d.get("marx_pos_kv", self.wj_marx_pos_buf[-1] if self.wj_marx_pos_buf else 0.0))
            self.wj_marx_neg_buf.append(d.get("marx_neg_kv", self.wj_marx_neg_buf[-1] if self.wj_marx_neg_buf else 0.0))
            if len(self.wj_t_marx_buf) > self.wj_max_points:
                self.wj_t_marx_buf = self.wj_t_marx_buf[-self.wj_max_points:]
                self.wj_marx_pos_buf = self.wj_marx_pos_buf[-self.wj_max_points:]
                self.wj_marx_neg_buf = self.wj_marx_neg_buf[-self.wj_max_points:]
            try:
                self.sf6_window.marx_pos_curve.setData(self.wj_t_marx_buf, self.wj_marx_pos_buf)
                self.sf6_window.marx_neg_curve.setData(self.wj_t_marx_buf, self.wj_marx_neg_buf)
                self.sf6_window.update_wj_scroll(t)
            except Exception:
                pass

    def on_glassman_calibrate(self):
        dlg = GlassmanCalibrationDialog(self)
        dlg.show()


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
        # Glassman buffers (fed by the Mega reader thread)
        self.wj_t_gm_buf = []
        self.wj_kv_gm_buf = []
        self.wj_ma_gm_buf = []
        # Marx rail charge buffers (fed by the Mega reader thread)
        self.wj_t_marx_buf = []
        self.wj_marx_pos_buf = []
        self.wj_marx_neg_buf = []
        self.wj_max_points = 3000  # Store ~5 minutes of history at ~10 Hz

        for idx, wj in enumerate(self.wj_units):
            worker = WJReaderThread(wj)
            worker.new_data.connect(lambda t, kv, ma, i=idx: self.handle_wj_plot_data(i, t, kv, ma))
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
                # unit_index == 1 (positive WJ supply) no longer drives the
                # kv2/ma2 gauges — those now show the Glassman Mega output,
                # updated from _on_glassman_mega_parsed.
            except Exception:
                pass

        # Log WJ data
        try:
            self.data_logger.log_wj_voltage(unit_index + 1, kv, ma, hv_on=False, fault=False)
        except Exception as e:
            self.log(f"[DataLogger ERROR] Failed to log WJ{unit_index+1} plot data: {e}")

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
            save_key="CFR_LASER_COM", log_tag="Laser1")
        self.laser_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self.laser_panel2 = LaserPanel(
            log_func=self.log, save_func=save_memory,
            default_port="COM11", title="CFR Laser 2",
            save_key="CFR_LASER2_COM", log_tag="Laser2")
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
        self.dg_panel.btn_fire.clicked.connect(self.on_dg_fire)

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

        # Glassman Mega connect/disconnect + calibration (Portenta is the SF6 Arduino)
        self.wj_panel.btn_glassman_mega_connect.clicked.connect(self.on_glassman_mega_connect)
        self.wj_panel.btn_glassman_mega_disconnect.clicked.connect(self.on_glassman_mega_disconnect)
        self.wj_panel.btn_glassman_calibrate.clicked.connect(self.on_glassman_calibrate)


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
        # SF6 dome pressure now comes from the Mega (A5), and the Parker
        # regulator setpoint is the Mega's DAC CH1 (PSI command). The old
        # Portenta auto-connect / pressure stream / Marx valve relays were
        # removed when the Mega took over everything.
        # ------------------------------

        # ------------------------------
        # Glassman / Marx Mega (owns HV monitor, setpoints, pressure, Marx)
        # ------------------------------
        if flags.get("mega", True):
            try:
                mega_port = self.conn.get("Glassman_Mega_COM", None)
                if mega_port:
                    self.glassman_mega.connect(mega_port)
                    self.wj_panel.glassman_mega_port_combo.setCurrentText(mega_port)
                    self.wj_panel.glassman_mega_lamp.set_status("green", "Connected")
                    self.wj_panel.glassman_mega_status.setText(f"Mega on {mega_port}")
                    save_memory("Glassman_Mega_COM", mega_port)
                    self._start_glassman_mega_reader()
                    self.log(f"[Glassman] Mega connected on {mega_port}")
                    # The Parker regulator is on the Mega's DAC CH1, so the
                    # startup pressure can only be commanded now.
                    self._apply_startup_pressure()
                else:
                    self.log("[Glassman] No saved Mega port to auto-connect")
            except Exception as e:
                self.wj_panel.glassman_mega_lamp.set_status("red", "Not Connected")
                self.wj_panel.glassman_mega_status.setText("Connect failed")
                self.log(f"[Glassman] Mega NOT CONNECTED: {e}")

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
        # WJ HIGH VOLTAGE SUPPLIES
        # ------------------------------
        default_wj_ports = ["COM11", "COM13"]  # Changed defaults to avoid relay port
        for i, wj in enumerate(self.wj_units):
            if not flags.get(f"wj{i+1}", True):
                continue
            try:
                port = self.conn.get(f"WJ{i+1}_COM", default_wj_ports[i])
                # Skip if this port is already used by relay
                if port == relay_port:
                    self.log(f"[WJ{i+1}] Skipping {port} (used by relay)")
                    self.wj_panel.rows[i].lamp.set_status("red", "Not Connected")
                    continue
                wj.connect(port)
                self.wj_panel.rows[i].lamp.set_status("green", "Connected")
                self.log(f"[WJ{i+1}] Connected on {port}")
            except Exception as e:
                self.wj_panel.rows[i].lamp.set_status("red", "Not Connected")
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
        """Read all BNC575 settings and update panel"""
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
            
            # Read channel states
            for ch in ['A', 'B', 'C', 'D']:
                enabled = self.bnc.get_channel_state(ch)
                self.bnc_panel.set_channel_enabled(ch, enabled)
            
            # Read system mode
            mode = self.bnc.get_system_mode()
            if mode:
                self.bnc_panel.set_system_mode(mode.value)
            
            self.log("[BNC575] Read all settings from device")
        except Exception as e:
            self.log(f"[BNC575] Error reading settings: {e}")


    # ------------------------------------------------------------------
    #  SF6 Window Connection
    # ------------------------------------------------------------------
    def connect_sf6_window(self):
        """Connect signals from SF6 window to main window handlers"""
        # The SF6 panel is now just a live dome-pressure monitor (Mega A5);
        # it has no connect buttons or Marx switches anymore.

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

        if hasattr(self.sf6_window, 'pressure_panel'):
            self.sf6_window.pressure_panel.btn_apply.clicked.connect(self.on_set_pressure)

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

    def _relay_set(self, ch: int, state: bool):
        """Set a relay and update the GUI panel. Safe to call from main thread only."""
        if not self.numato_relay.is_connected:
            self.log(f"[Relay] Not connected — cannot set CH{ch}")
            return
        try:
            self.numato_relay.set_relay(ch, state)
            self.relay_panel.update_relay_state(ch, state)
            self.log(f"[Relay] CH{ch} → {'ON' if state else 'OFF'}")
        except Exception as e:
            self.log(f"[Relay ERROR] CH{ch}: {e}")

    def on_set_pressure(self):
        """Handle pressure setpoint change"""
        try:
            psi = self.sf6_window.pressure_panel.get_psi()

            # The Parker regulator is driven by the Mega's DAC CH1. Send the raw
            # PSI setpoint and let the Mega apply its regulator calibration
            # (PSI->DAC volts) and clamp out-of-range values.
            self.glassman_send_mega(f"PSI {psi:.2f}")

            self.sf6_window.pressure_panel.update_output_display(psi)
            self.data_logger.log_glassman_command("PSI", f"{psi:.2f}psi")
            self.log(f"[Pressure] Set {psi:.2f} PSI -> Mega DAC CH1")

        except Exception as e:
            self.log(f"[Pressure ERROR] {e}")
            self.error_popup("Pressure Control Error", str(e))

    def _command_pressure(self, psi):
        """Send a PSI setpoint to the Mega (DAC CH1) and sync the pressure
        panel UI. Returns the clamped/float psi."""
        psi = float(psi)
        self.glassman_send_mega(f"PSI {psi:.2f}")
        self.data_logger.log_glassman_command("PSI", f"{psi:.2f}psi")
        pp = getattr(self.sf6_window, "pressure_panel", None)
        if pp is not None:
            pp.combo_unit.setCurrentText("PSI")
            pp.spin_value.setValue(psi)
            pp.update_output_display(psi)
        return psi

    def _apply_startup_pressure(self):
        """Command the configured startup pressure to the Mega (DAC CH1) and
        sync the pressure panel UI. Called once the Mega is connected."""
        if self.startup_pressure_psi is None:
            return
        try:
            psi = self._command_pressure(self.startup_pressure_psi)
            self.log(f"[Pressure] Startup pressure set to {psi:.1f} PSI")
        except Exception as e:
            self.log(f"[Pressure] Startup set failed: {e}")

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
            path = self.data_logger.scope_export_path(scope_id)
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
        self._update_interlock_fire()

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
        self.log("[INTERLOCK] Checklist reset.")

    def _poll_interlocks(self):
        """Timer tick: evaluate the auto-checked steps and honor manual
        overrides. Latched (green) steps are skipped so they never re-lock."""
        # Step 1 - both lasers armed (reads widget state only, no serial).
        if not self.interlock_passed.get(1):
            if self.interlock_manual[1].isChecked():
                self._mark_interlock(1, "manual")
            elif self._check_lasers_armed():
                self._mark_interlock(1, "both lasers armed")

        # Step 4 - dome pressure above 50 psi (cached Mega reading).
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
            self.error_popup(
                "Interlocks not satisfied",
                "All interlock steps (1-4) must be green before firing.")
            return
        self.log("[INTERLOCK] All checks green - running Single + Capture.")
        self.on_capture_all_scopes()

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
        except Exception as e:
            self.set_status("red", "DG535 connection failed")
            self.log(f"[DG535 ERROR] {e}")
            self.error_popup("DG535 Error", str(e))

    def on_dg_fire(self):
        try:
            # SAFETY INTERLOCK: Ensure WJ HV supplies are OFF before firing
            if not self.ensure_wj_hv_off():
                self.log("[DG535] Fire ABORTED - WJ HV interlock failed")
                return

            delayA = self.dg_panel.get_delayA()
            widthA = self.dg_panel.get_widthA()

            self.log(f"[DG535] Config pulse A: delay={delayA:.3e}, width={widthA:.3e}")
            self.set_status("yellow", "Configuring DG535...")
            self.dg.configure_pulse_A(delayA, widthA)
            self.data_logger.log_dg535_config(delayA, widthA)

            self.dg.set_single_shot()
            self.dg.fire()
            self.data_logger.log_dg535_pulse(delayA, widthA)

            self.set_status("green", "DG535 pulse fired")
            self.log("[DG535] Pulse fired.")
        except Exception as e:
            self.set_status("red", "DG535 fire failed")
            self.log(f"[DG535 ERROR] {e}")
            self.data_logger.log_error("DG535", str(e))
            self.error_popup("DG535 Fire Error", str(e))

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
                self.bnc_panel.btn_arm.setText("Disarm (EXT TRIG)")
                self.data_logger.log_bnc575_arm(level)
                self.set_status("green", "BNC575 armed (EXT)")
                self.log(f"[BNC575] Armed for external trigger: {source}/{slope} @ {level:.2f} V")
            else:
                self.bnc.disarm_trigger()
                self.bnc_trigger_armed = False
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
            return

        # SAFETY INTERLOCK: Ensure WJ HV supplies are OFF before firing
        if not self.ensure_wj_hv_off():
            self.log("[BNC575] Fire ABORTED - WJ HV interlock failed")
            return

        try:
            self.set_status("yellow", "Firing BNC575 internal pulse...")
            self.bnc.fire_internal()
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

    def start_four_channel_capture(self, rigol, name, scope_id):
        """Start a 4-channel capture worker for a scope"""
        self.set_status("yellow", f"Capturing {name} (4 channels)...")
        self.log(f"[{name}] 4-channel capture started...")
        self._set_capture_state(scope_id, "armed")

        worker = CaptureFourChannelWorker(rigol, name, timeout=300.0)
        worker.finished.connect(lambda data, nm: self.on_four_channel_capture_finished(data, nm, scope_id))
        worker.error.connect(lambda msg, nm, sid=scope_id: self.on_single_capture_error(msg, nm, sid))
        
        # Store worker reference to prevent garbage collection
        setattr(self, f'capture_worker_{scope_id}', worker)
        worker.start()

    def on_four_channel_capture_finished(self, data, name, scope_id):
        """Handle 4-channel capture completion"""
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

        # Log capture (count non-empty channels)
        ch_counts = [len(t1), len(t2), len(t3), len(t4)]
        self.data_logger.log_scope_capture(scope_id, ch_counts[0], ch_counts[1])

        self.set_status("green", f"{name} captured (4 ch)")
        self._set_capture_state(scope_id, "done", f"{max(len(t1), len(t2), len(t3), len(t4))} pts")
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
            self._set_capture_state(scope_id, "error")
        self.error_popup(f"{name} Capture Error", msg)
        self.log(f"[{name} ERROR] {msg}")


    def on_capture_all_scopes(self):
        """Capture all 4 channels from all connected scopes"""
        self.set_status("yellow", "Preparing for 4-channel capture...")
        self.log("[CAPTURE] Starting 4-channel capture sequence...")

        # SAFETY INTERLOCK: Ensure WJ HV supplies are OFF before firing
        if not self.ensure_wj_hv_off():
            self.log("[CAPTURE] Capture ABORTED - WJ HV interlock failed")
            return

        # 1. STOP and ARM all Rigols early
        try:
            if self.rigol1_connected:
                self.rigol1.stop()
                self.rigol1.single()
                self.data_logger.log_scope_arm(1)
            if self.rigol2_connected:
                self.rigol2.stop()
                self.rigol2.single()
                self.data_logger.log_scope_arm(2)
            if self.rigol3_connected:
                self.rigol3.stop()
                self.rigol3.single()
                self.data_logger.log_scope_arm(3)

            self.log("[CAPTURE] Rigols set to SINGLE")
            # Show "Armed" for every connected scope, and force a repaint now —
            # capture-all blocks the GUI thread during the trigger wait, so this
            # is the operator's cue that the scopes are armed and waiting.
            from PyQt6.QtWidgets import QApplication
            for sid, connected in ((1, self.rigol1_connected),
                                   (2, self.rigol2_connected),
                                   (3, self.rigol3_connected)):
                self._set_capture_state(sid, "armed" if connected else "idle")
            QApplication.processEvents()
        except Exception as e:
            self.error_popup("Rigol Error", f"Failed to arm scopes: {e}")
            self.data_logger.log_error("SCOPE", str(e))
            return

        time.sleep(0.25)

        # 2. ARM BNC575 for external trigger
        try:
            self.bnc.arm_external_trigger(level=3.0)
            self.data_logger.log_bnc575_arm(3.0)
            self.log("[BNC575] Armed for external trigger")
        except Exception as e:
            self.error_popup("BNC575 Error", str(e))
            self.data_logger.log_error("BNC575", str(e))
            return

        # 3. CONFIGURE DG535 but DO NOT FIRE YET
        try:
            delayA = self.dg_panel.get_delayA()
            widthA = self.dg_panel.get_widthA()
            self.dg.configure_pulse_A(delayA, widthA)
            self.data_logger.log_dg535_config(delayA, widthA)
            self.dg.set_single_shot()
        except Exception as e:
            self.error_popup("DG535 Error", str(e))
            self.data_logger.log_error("DG535", str(e))
            return

        time.sleep(0.2)

        # 4. FIRE DG535 (MASTER TRIGGER)
        self.log("[CAPTURE] Firing DG535...")
        try:
            self.dg.fire()
            self.data_logger.log_dg535_pulse(delayA, widthA)
            self.log("[DG535] Trigger pulse fired.")
        except Exception as e:
            self.error_popup("DG535 Fire Error", str(e))
            self.data_logger.log_error("DG535", str(e))
            return

        time.sleep(0.5)

        # 5. CAPTURE waveforms (4 channels each)
        self.set_status("yellow", "Capturing 4-channel waveforms...")

        # if self.rigol1_connected:
        #     data = self.rigol1.wait_and_capture_four()
        #     (t1, v1), (t2, v2), (t3, v3), (t4, v4) = data
        #     self.scope_window.update_r1(t1, v1, t2, v2, t3, v3, t4, v4)
        #     self.data_logger.log_scope_capture(1, len(t1), len(t2))
        #     self.log(f"[Rigol1] Captured: CH1={len(t1)}, CH2={len(t2)}, CH3={len(t3)}, CH4={len(t4)} pts")

        # if self.rigol2_connected:
        #     data = self.rigol2.wait_and_capture_four()
        #     (t1, v1), (t2, v2), (t3, v3), (t4, v4) = data
        #     self.scope_window.update_r2(t1, v1, t2, v2, t3, v3, t4, v4)
        #     self.data_logger.log_scope_capture(2, len(t1), len(t2))
        #     self.log(f"[Rigol2] Captured: CH1={len(t1)}, CH2={len(t2)}, CH3={len(t3)}, CH4={len(t4)} pts")

        # if self.rigol3_connected:
        #     data = self.rigol3.wait_and_capture_four()
        #     (t1, v1), (t2, v2), (t3, v3), (t4, v4) = data
        #     self.scope_window.update_r3(t1, v1, t2, v2, t3, v3, t4, v4)
        #     self.data_logger.log_scope_capture(3, len(t1), len(t2))
        #     self.log(f"[Rigol3] Captured: CH1={len(t1)}, CH2={len(t2)}, CH3={len(t3)}, CH4={len(t4)} pts")

        # self.data_logger.log_scope_all_capture()

        # self.set_status("green", "4-channel capture complete")
        # self.log("[CAPTURE] Done.")
        if self.rigol1_connected:
            data = self.rigol1.wait_and_capture_four()
            self.current_data = data  # ← ADD THIS
            self.captured_scopes[1] = data
            (t1, v1), (t2, v2), (t3, v3), (t4, v4) = data
            self.scope_window.update_r1(t1, v1, t2, v2, t3, v3, t4, v4)
            self.data_logger.log_scope_capture(1, len(t1), len(t2))
            self._set_capture_state(1, "done", f"{max(len(t1), len(t2), len(t3), len(t4))} pts")
            self.log(f"[Rigol1] Captured: CH1={len(t1)}, CH2={len(t2)}, CH3={len(t3)}, CH4={len(t4)} pts")

        if self.rigol2_connected:
            data = self.rigol2.wait_and_capture_four()
            self.current_data = data  # ← ADD THIS
            self.captured_scopes[2] = data
            (t1, v1), (t2, v2), (t3, v3), (t4, v4) = data
            self.scope_window.update_r2(t1, v1, t2, v2, t3, v3, t4, v4)
            self.data_logger.log_scope_capture(2, len(t1), len(t2))
            self._set_capture_state(2, "done", f"{max(len(t1), len(t2), len(t3), len(t4))} pts")
            self.log(f"[Rigol2] Captured: CH1={len(t1)}, CH2={len(t2)}, CH3={len(t3)}, CH4={len(t4)} pts")

        if self.rigol3_connected:
            data = self.rigol3.wait_and_capture_four()
            self.current_data = data  # ← ADD THIS
            self.captured_scopes[3] = data
            (t1, v1), (t2, v2), (t3, v3), (t4, v4) = data
            self.scope_window.update_r3(t1, v1, t2, v2, t3, v3, t4, v4)
            self.data_logger.log_scope_capture(3, len(t1), len(t2))
            self._set_capture_state(3, "done", f"{max(len(t1), len(t2), len(t3), len(t4))} pts")
            self.log(f"[Rigol3] Captured: CH1={len(t1)}, CH2={len(t2)}, CH3={len(t3)}, CH4={len(t4)} pts")

        self.data_logger.log_scope_all_capture()
        self._mark_captures_dirty()
        self.set_status("green", "4-channel capture complete")
        self.log("[CAPTURE] Done.")


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
            self.wj_units[index].connect(port)
            save_memory(f"WJ{index+1}_COM", port)
            row.lamp.set_status("green", "Connected")
        except Exception as e:
            self.log(f"[WJ{index+1} ERROR] {e}")
            row.lamp.set_status("red", "Error")


    def on_wj_hv_on(self):
        # Pre-pressurize sequence: raise the dome to the HV-on pressure first,
        # wait for it to settle, THEN actually enable HV (see _do_wj_hv_on).
        if self._hv_on_pending:
            self.log("[HV] HV-on already pending — ignoring repeat press")
            return

        # The "Pre-pressurize dome on HV ON" checkbox lets the operator skip the
        # auto pressure-raise + settle delay (e.g. when the dome is already at
        # pressure) and enable HV immediately.
        prepressurize = self.wj_panel.chk_prepressurize.isChecked()
        if not prepressurize:
            self.log("[HV] Pre-pressurize disabled — enabling HV immediately")
            self._hv_on_pending = True
            self._do_wj_hv_on()
            return

        try:
            psi = self._command_pressure(self.hv_on_pressure_psi)
            self.log(f"[Pressure] Raising to {psi:.1f} PSI before HV on")
        except Exception as e:
            self.log(f"[Pressure ERROR] {e}")

        delay = float(self.hv_on_delay_sec)
        self._hv_on_pending = True
        self.log(f"[HV] Waiting {delay:.1f}s for pressure to settle before HV on...")
        QTimer.singleShot(int(delay * 1000), self._do_wj_hv_on)

    def _do_wj_hv_on(self):
        # If HV-off was pressed during the countdown, abort the enable.
        if not self._hv_on_pending:
            self.log("[HV] HV-on cancelled before it fired")
            return
        self._hv_on_pending = False

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

        # Glassman: program the V-PROGRAM DAC to the same kV *before* closing
        # the HV ENABLE relay, so the supply ramps to the right setpoint
        # instead of starting at whatever the DAC was last commanded to.
        self.glassman_send_mega(f"KV {float(kv):.2f}")
        self.glassman_send_mega("ON")
        self.data_logger.log_glassman_command("HV_ON", f"{float(kv):.2f}kV")

    def on_wj_hv_off(self):
        # Cancel any in-flight pre-pressurize HV-on countdown.
        if self._hv_on_pending:
            self._hv_on_pending = False
            self.log("[HV] Pending HV-on cancelled by HV OFF")

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

        # Glassman HV disable
        self.glassman_send_mega("OFF")
        self.data_logger.log_glassman_command("HV_OFF")


    def on_wj_reset(self):
        for i, wj in enumerate(self.wj_units):
            try:
                wj.reset_pulse()
                self.data_logger.log_wj_command(i+1, "RESET")
                self.log(f"[WJ{i+1}] Reset OK")
            except Exception as e:
                self.log(f"[WJ{i+1} ERROR] {e}")
                self.data_logger.log_error(f"WJ{i+1}", str(e))

        # Zero the Glassman V-PROGRAM via the Mega's DAC. (No I-PROGRAM
        # control anymore — Mega only has the GP8413 channel 0 wired to
        # V-PROGRAM.)
        self.glassman_send_mega("ZERO")

    def on_wj_set_voltage(self, kv=None, ma=None):
        if kv is None:
            kv = self.wj_panel.voltage.value()
        # Current is always commanded to each WJ supply's maximum on Apply
        # Program — user wants every supply opened wide. The Glassman's
        # I-PROGRAM is no longer driven from the GUI (the Mega only has a
        # V-PROGRAM DAC via GP8413); current limit is set on the supply.

        for i, wj in enumerate(self.wj_units):
            try:
                wj_ma = wj.imax_ma
                resp = wj.set_program(kv, wj_ma)
                self.data_logger.log_wj_command(i+1, "SET_PROGRAM", f"{kv}kV_{wj_ma}mA")
                self.log(f"[WJ{i+1}] Set → {kv} kV, {wj_ma} mA (MAX) ({resp})")
            except Exception as e:
                self.log(f"[WJ{i+1} ERROR] {e}")
                self.data_logger.log_error(f"WJ{i+1}", str(e))

        # Glassman voltage now comes from the Mega's I2C DAC via "KV <kv>".
        # The Mega clamps to 0..125 kV internally, so pass the spinbox value
        # straight through.
        self.glassman_send_mega(f"KV {float(kv):.2f}")


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
            path = self.data_logger.scope_export_path(scope_id)
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

        try:
            self._stop_glassman_mega_reader()
            self.glassman_mega.close()
        except Exception as e:
            self.log(f"[Glassman] shutdown error: {e}")

        if hasattr(self, 'scope_window') and self.scope_window:
            self.scope_window.close()

        if hasattr(self, 'sf6_window') and self.sf6_window:
            self.sf6_window.close()

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
