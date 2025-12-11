# # # # # gui/main_window.py
# # # # from PyQt6.QtWidgets import (
# # # #     QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QMessageBox, QPushButton, QSizePolicy, QGridLayout,
# # # # )
# # # # from PyQt6.QtCore import QThread, Qt






# # # # import time

# # # # from gui.dg535_panel import DG535Panel
# # # # from gui.bnc575_panel import BNC575Panel
# # # # from gui.rigol_panel import RigolPanel
# # # # from gui.sf6_window import SF6Window
# # # # from gui.wj_panel import WJPanel
# # # # from gui.scope_plot_window import ScopePlotWindow
# # # # from gui.wj_plot_window import WJPlotWindow

# # # # from utils.logger import LogPanel
# # # # from utils.status_lamp import StatusLamp
# # # # from utils.serial_tools import list_serial_ports
# # # # from utils.capture_single_worker import CaptureSingleWorker
# # # # from utils.connect_memory import load_memory, save_memory
# # # # from utils.arduino_stream_worker import ArduinoStreamWorker
# # # # from utils.data_logger import DataLogger



# # # # from instruments.dg535 import DG535Controller
# # # # from instruments.bnc575 import BNC575Controller
# # # # from instruments.rigol import RigolScope
# # # # from instruments.arduino import ArduinoController
# # # # # from ScopeDelayGUI.instruments.wj import WJPowerSupply
# # # # from instruments.wj import WJPowerSupply


# # # # class ScopeDelayMainWindow(QMainWindow):
# # # #     def __init__(self):
# # # #         super().__init__()

# # # #         self.setWindowTitle("Scope + Delay + SF6 Control")
# # # #         self.setGeometry(100, 100, 1700, 900)
# # # #         self.conn = load_memory()
# # # #         self.wj_plot_window = None

# # # #         # Initialize data logger
# # # #         self.data_logger = DataLogger()

# # # #         # --- instruments ---
# # # #         self.dg = DG535Controller()
# # # #         self.bnc = BNC575Controller()
# # # #         self.bnc_trigger_armed = False
# # # #         # default VISA addresses (change to match your scopes)
# # # #         # self.rigol1 = RigolScope("USB0::0x1AB1::0x0514::DS7A233300256::0::INSTR")
# # # #         # self.rigol2 = RigolScope("USB0::0x1AB1::0x0514::DS7A232900210::0::INSTR")
# # # #         # self.rigol3 = RigolScope("USB0::0x1AB1::0x0514::DS7A230800035::0::INSTR")
# # # #         # NEW ORDER (matches your physical setup)

# # # #         self.rigol2 = RigolScope("USB0::0x1AB1::0x0514::DS7A230800035::0::INSTR")  # Physical scope 1
# # # #         self.rigol3 = RigolScope("USB0::0x1AB1::0x0514::DS7A233300256::0::INSTR")  # Physical scope 2
# # # #         self.rigol1 = RigolScope("USB0::0x1AB1::0x0514::DS7A232900210::0::INSTR")  # Physical scope 3
    
# # # #         # self.wj = WJPowerSupply(port="COM6")
# # # #         # self.wj = WJPowerSupply(vmax_kv=100.0, imax_ma=6.0)

# # # #         # self.wj_panel = WJPanel()
# # # #         # Multiple WJ supplies
# # # #         self.wj_units = [
# # # #             WJPowerSupply(vmax_kv=100.0, imax_ma=6.0),
# # # #             WJPowerSupply(vmax_kv=100.0, imax_ma=6.0)
# # # #         ]

# # # #         # Panel now supports 2 units
# # # #         self.wj_panel = WJPanel(num_units=2)


# # # #         self.wj_panel.setSizePolicy(
# # # #             QSizePolicy.Policy.Preferred,
# # # #             QSizePolicy.Policy.Fixed
# # # #         )

# # # #         self.arduino = ArduinoController()
        
# # # #         self.rigol1_connected = False
# # # #         self.rigol2_connected = False
# # # #         self.rigol3_connected = False

# # # #         central = QWidget()
# # # #         self.setCentralWidget(central)
# # # #         main_layout = QVBoxLayout()
# # # #         central.setLayout(main_layout)

# # # #         # Remove tabs - just use main layout for Scope + Delay controls
# # # #         self.build_scope_controls(main_layout)
# # # #         self.refresh_wj_ports()

# # # #         # Create SF6 window as separate top-level window (now includes WJ plots)
# # # #         self.sf6_window = SF6Window()


# # # #         # Load remembered connection info


# # # #         # Attempt auto-connect
# # # #         self.auto_connect_all()
# # # #         # Populate COM list initially
# # # #         self.refresh_arduino_ports()

# # # #         # Connect SF6 window controls
# # # #         self.connect_sf6_window()

# # # #         # Create scope plot window
# # # #         self.scope_window = ScopePlotWindow(parent=self)

# # # #         # Start WJ reader threads and connect to SF6 window plot
# # # #         self.start_wj_readers()

# # # #         # Position and show all windows on startup
# # # #         self.position_and_show_windows()

# # # #         # Log the data file location
# # # #         self.log(f"[DATA LOGGER] Saving to: {self.data_logger.get_log_file_path()}")

# # # #         # Write a test log entry to verify logging is working
# # # #         self.data_logger.log_info("SYSTEM", "GUI started successfully")

        
# # # #     def refresh_wj_ports(self):
# # # #         """Populate COM lists for each WJ unit, selecting last used port."""
# # # #         ports = list_serial_ports()
# # # #         if not ports:
# # # #             ports = ["No COM ports"]

# # # #         for i, row in enumerate(self.wj_panel.rows):
# # # #             row.port_combo.clear()
# # # #             row.port_combo.addItems(ports)

# # # #             # Load last used
# # # #             last_port = self.conn.get(f"WJ{i+1}_COM", None)
# # # #             if last_port and last_port in ports:
# # # #                 row.port_combo.setCurrentText(last_port)

# # # #         # Mirror ports into SF6 window duplicates
# # # #         if hasattr(self, "sf6_window") and hasattr(self.sf6_window, "wj_port_combos"):
# # # #             for i, combo in enumerate(self.sf6_window.wj_port_combos):
# # # #                 combo.blockSignals(True)
# # # #                 combo.clear()
# # # #                 combo.addItems(ports)

# # # #                 last_port = self.conn.get(f"WJ{i+1}_COM", None)
# # # #                 if last_port and last_port in ports:
# # # #                     combo.setCurrentText(last_port)
# # # #                 combo.blockSignals(False)
    

# # # #     def start_wj_readers(self):
# # # #         """Start WJ reader threads and connect to SF6 window plot"""
# # # #         from gui.wj_plot_window import WJReaderThread
# # # #         import time

# # # #         self.wj_workers = []
# # # #         self.wj_start_time = time.time()
# # # #         self.wj_t_buf = []
# # # #         self.wj_kv1_buf = []
# # # #         self.wj_ma1_buf = []
# # # #         self.wj_kv2_buf = []
# # # #         self.wj_ma2_buf = []
# # # #         self.wj_max_points = 500

# # # #         for idx, wj in enumerate(self.wj_units):
# # # #             worker = WJReaderThread(wj)
# # # #             worker.new_data.connect(lambda t, kv, ma, i=idx: self.handle_wj_plot_data(i, t, kv, ma))
# # # #             worker.start()
# # # #             self.wj_workers.append(worker)

# # # #     def handle_wj_plot_data(self, unit_index, t, kv, ma):
# # # #         """Handle incoming WJ data for plotting in SF6 window"""
# # # #         import time

# # # #         # Normalize time to shared reference
# # # #         t = time.time() - self.wj_start_time

# # # #         # Update live gauge displays in SF6 window
# # # #         if hasattr(self, "sf6_window"):
# # # #             try:
# # # #                 if unit_index == 0:
# # # #                     self.sf6_window.kv1_gauge.update_value(kv)
# # # #                     self.sf6_window.ma1_gauge.update_value(ma)
# # # #                 elif unit_index == 1:
# # # #                     self.sf6_window.kv2_gauge.update_value(kv)
# # # #                     self.sf6_window.ma2_gauge.update_value(ma)
# # # #             except Exception:
# # # #                 pass

# # # #         # Log WJ data (we don't have HV status here, so pass False for now)
# # # #         # The WJReaderThread only gets kV and mA, not HV status
# # # #         try:
# # # #             self.data_logger.log_wj_voltage(unit_index + 1, kv, ma, hv_on=False, fault=False)
# # # #         except Exception as e:
# # # #             self.log(f"[DataLogger ERROR] Failed to log WJ{unit_index+1} plot data: {e}")

# # # #         # Store data with separate time arrays for each unit
# # # #         # Unit 1
# # # #         if unit_index == 0:
# # # #             # Ensure we have matching arrays by using separate time buffer for unit 1
# # # #             if not hasattr(self, 'wj_t1_buf'):
# # # #                 self.wj_t1_buf = []
# # # #             self.wj_t1_buf.append(t)
# # # #             self.wj_kv1_buf.append(kv)
# # # #             self.wj_ma1_buf.append(ma)

# # # #             # Rolling window for unit 1
# # # #             if len(self.wj_t1_buf) > self.wj_max_points:
# # # #                 self.wj_t1_buf = self.wj_t1_buf[-self.wj_max_points:]
# # # #                 self.wj_kv1_buf = self.wj_kv1_buf[-self.wj_max_points:]
# # # #                 self.wj_ma1_buf = self.wj_ma1_buf[-self.wj_max_points:]

# # # #             # Update curves for unit 1
# # # #             self.sf6_window.kv1_curve.setData(self.wj_t1_buf, self.wj_kv1_buf)
# # # #             self.sf6_window.ma1_curve.setData(self.wj_t1_buf, self.wj_ma1_buf)

# # # #         # Unit 2
# # # #         elif unit_index == 1:
# # # #             # Ensure we have matching arrays by using separate time buffer for unit 2
# # # #             if not hasattr(self, 'wj_t2_buf'):
# # # #                 self.wj_t2_buf = []
# # # #             self.wj_t2_buf.append(t)
# # # #             self.wj_kv2_buf.append(kv)
# # # #             self.wj_ma2_buf.append(ma)

# # # #             # Rolling window for unit 2
# # # #             if len(self.wj_t2_buf) > self.wj_max_points:
# # # #                 self.wj_t2_buf = self.wj_t2_buf[-self.wj_max_points:]
# # # #                 self.wj_kv2_buf = self.wj_kv2_buf[-self.wj_max_points:]
# # # #                 self.wj_ma2_buf = self.wj_ma2_buf[-self.wj_max_points:]

# # # #             # Update curves for unit 2
# # # #             self.sf6_window.kv2_curve.setData(self.wj_t2_buf, self.wj_kv2_buf)
# # # #             self.sf6_window.ma2_curve.setData(self.wj_t2_buf, self.wj_ma2_buf)

# # # #     def position_and_show_windows(self):
# # # #         """Position windows on appropriate monitors and show them"""
# # # #         from PyQt6.QtGui import QGuiApplication

# # # #         screens = QGuiApplication.screens()
# # # #         if not screens:
# # # #             # Fallback: just show windows normally
# # # #             self.scope_window.showMaximized()
# # # #             self.sf6_window.showMaximized()
# # # #             return

# # # #         # Sort screens left-to-right by x coordinate
# # # #         screens_sorted = sorted(screens, key=lambda s: s.geometry().x())

# # # #         # Assign based on physical layout: left (vertical) -> SF6, middle -> main window, right -> scope
# # # #         if len(screens_sorted) >= 3:
# # # #             left_screen, middle_screen, right_screen = screens_sorted[:3]
# # # #         elif len(screens_sorted) == 2:
# # # #             left_screen, right_screen = screens_sorted
# # # #             middle_screen = left_screen  # fallback: place main on left if only two
# # # #         else:
# # # #             left_screen = middle_screen = right_screen = screens_sorted[0]

# # # #         # Main window on middle screen
# # # #         self.setScreen(middle_screen)
# # # #         mid_geo = middle_screen.geometry()
# # # #         self.move(mid_geo.x() + 50, mid_geo.y() + 50)

# # # #         # SF6 window on left screen
# # # #         self.sf6_window.setScreen(left_screen)
# # # #         self.sf6_window.move(left_screen.geometry().topLeft())
# # # #         self.sf6_window.showMaximized()

# # # #         # Scope window on right screen
# # # #         self.scope_window.setScreen(right_screen)
# # # #         self.scope_window.move(right_screen.geometry().topLeft())
# # # #         self.scope_window.showMaximized()

# # # #     def build_scope_controls(self, main_layout):
# # # #         layout = QHBoxLayout()

# # # #         # --------------------------------
# # # #         # Create instrument panels
# # # #         # --------------------------------
# # # #         self.dg_panel = DG535Panel()
# # # #         self.dg_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

# # # #         self.bnc_panel = BNC575Panel()
# # # #         self.bnc_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

# # # #         self.rigol_panel = RigolPanel()
# # # #         self.rigol_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

# # # #         self.wj_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

# # # #         # --------------------------------
# # # #         # GRID LAYOUT (2x2)
# # # #         # --------------------------------
# # # #         grid = QGridLayout()
# # # #         grid.addWidget(self.dg_panel, 0, 0)
# # # #         grid.addWidget(self.bnc_panel, 0, 1)
# # # #         grid.addWidget(self.rigol_panel, 1, 0)
# # # #         grid.addWidget(self.wj_panel, 1, 1)

# # # #         # --------------------------------
# # # #         # Left column containing grid + status + logs + button
# # # #         # --------------------------------
# # # #         left_column = QVBoxLayout()
# # # #         left_column.addLayout(grid)

# # # #         self.status_lamp = StatusLamp()
# # # #         self.log_panel = LogPanel()

# # # #         left_column.addWidget(self.status_lamp)
# # # #         left_column.addWidget(self.log_panel)

# # # #         self.btn_open_scope = QPushButton("Open Scope Display Window")
# # # #         left_column.addWidget(self.btn_open_scope)
# # # #         self.btn_open_scope.clicked.connect(self.on_open_scope_window)

# # # #         left_column.addStretch()

# # # #         layout.addLayout(left_column, 1)

# # # #         # Add the layout to the main window
# # # #         main_layout.addLayout(layout)

# # # #         # --------------------------------
# # # #         # Connect buttons
# # # #         # --------------------------------
# # # #         self.dg_panel.btn_connect.clicked.connect(self.on_dg_connect)
# # # #         self.dg_panel.btn_fire.clicked.connect(self.on_dg_fire)

# # # #         self.bnc_panel.btn_connect.clicked.connect(self.on_bnc_connect)
# # # #         self.bnc_panel.btn_fire.clicked.connect(self.on_bnc_fire)
# # # #         self.bnc_panel.btn_apply.clicked.connect(self.on_bnc_apply)
# # # #         self.bnc_panel.btn_read.clicked.connect(self.on_bnc_read)
# # # #         self.bnc_panel.btn_arm.clicked.connect(self.on_bnc_arm)
# # # #         if hasattr(self.bnc_panel, "btn_en_a"):
# # # #             self.bnc_panel.btn_en_a.toggled.connect(lambda s: self.on_bnc_enable_channel("CHA", s))
# # # #             self.bnc_panel.btn_en_b.toggled.connect(lambda s: self.on_bnc_enable_channel("CHB", s))
# # # #             self.bnc_panel.btn_en_c.toggled.connect(lambda s: self.on_bnc_enable_channel("CHC", s))
# # # #             self.bnc_panel.btn_en_d.toggled.connect(lambda s: self.on_bnc_enable_channel("CHD", s))
# # # #         if hasattr(self.bnc_panel, "btn_en_trig"):
# # # #             self.bnc_panel.btn_en_trig.toggled.connect(self.on_bnc_enable_trigger)
# # # #         if hasattr(self.bnc_panel, "btn_apply_trigger"):
# # # #             self.bnc_panel.btn_apply_trigger.clicked.connect(self.on_bnc_apply_trigger)

# # # #         self.rigol_panel.btn_r1.clicked.connect(self.on_rigol1_connect)
# # # #         self.rigol_panel.btn_r2.clicked.connect(self.on_rigol2_connect)
# # # #         self.rigol_panel.btn_r3.clicked.connect(self.on_rigol3_connect)
# # # #         self.rigol_panel.btn_capture.clicked.connect(self.on_capture_all_scopes)
# # # #         self.rigol_panel.btn_r1_single.clicked.connect(self.on_r1_single)
# # # #         self.rigol_panel.btn_r2_single.clicked.connect(self.on_r2_single)
# # # #         self.rigol_panel.btn_r3_single.clicked.connect(self.on_r3_single)
# # # #         self.rigol_panel.btn_export.clicked.connect(self.on_export_csv)

# # # #         self.rigol_panel.btn_r1_capture.clicked.connect(self.on_capture_r1)
# # # #         self.rigol_panel.btn_r2_capture.clicked.connect(self.on_capture_r2)
# # # #         self.rigol_panel.btn_r3_capture.clicked.connect(self.on_capture_r3)




# # # #         # self.wj_panel.btn_connect.clicked.connect(self.on_wj_connect)
# # # #         self.wj_panel.btn_hv_on.clicked.connect(self.on_wj_hv_on)
# # # #         self.wj_panel.btn_hv_off.clicked.connect(self.on_wj_hv_off)
# # # #         self.wj_panel.btn_reset.clicked.connect(self.on_wj_reset)
# # # #         self.wj_panel.btn_set_v.clicked.connect(self.on_wj_set_voltage)
# # # #         # self.wj_panel.btn_set_i.clicked.connect(self.on_wj_set_current)
# # # #         self.wj_panel.btn_read.clicked.connect(self.on_wj_read)

# # # #         # --- Disconnect buttons ---
# # # #         self.dg_panel.btn_disconnect.clicked.connect(self.on_dg_disconnect)
# # # #         self.bnc_panel.btn_disconnect.clicked.connect(self.on_bnc_disconnect)

# # # #         self.rigol_panel.btn_r1_disconnect.clicked.connect(self.on_r1_disconnect)
# # # #         self.rigol_panel.btn_r2_disconnect.clicked.connect(self.on_r2_disconnect)
# # # #         self.rigol_panel.btn_r3_disconnect.clicked.connect(self.on_r3_disconnect)

# # # #         # self.wj_panel.btn_disconnect.clicked.connect(self.on_wj_disconnect)
# # # #         # -------------------------------------------
# # # #         # Hook each WJ unit's connect/disconnect
# # # #         # -------------------------------------------
# # # #         for idx, row in enumerate(self.wj_panel.rows):
# # # #             row.connect.clicked.connect(lambda _, i=idx: self.on_wj_connect(i))
# # # #             row.disconnect.clicked.connect(lambda _, i=idx: self.on_wj_disconnect(i))


# # # #     def auto_connect_all(self):
# # # #         self.log("=== Auto-connect starting ===")

# # # #         # ------------------------------
# # # #         # DG535
# # # #         # ------------------------------
# # # #         try:
# # # #             port = self.conn.get("DG535_COM", "COM4")
# # # #             self.dg.connect(port=port, gpib_addr=15)
# # # #             save_memory("DG535_COM", port)
# # # #             self.log(f"[DG535] Connected on {port}")
# # # #             self.dg_panel.lamp.set_status("green", "Connected")
# # # #         except Exception as e:
# # # #             self.log(f"[DG535] NOT CONNECTED: {e}")
# # # #             self.dg_panel.lamp.set_status("red", "Not Connected")

# # # #         # ------------------------------
# # # #         # BNC575
# # # #         # ------------------------------
# # # #         try:
# # # #             port = self.conn.get("BNC575_COM", "COM5")
# # # #             self.bnc.connect(port=port)
# # # #             self.bnc_connected = True
# # # #             save_memory("BNC575_COM", port)
# # # #             self.log(f"[BNC575] Connected on {port}")
# # # #             self.bnc_panel.lamp.set_status("green", "Connected")
# # # #         except Exception as e:
# # # #             self.bnc_connected = False
# # # #             self.log(f"[BNC575] NOT CONNECTED: {e}")
# # # #             self.bnc_panel.lamp.set_status("red", "Not Connected")

# # # #         # ------------------------------
# # # #         # Arduino / SF6
# # # #         # ------------------------------
# # # #         try:
# # # #             port = self.conn.get("Arduino_COM", "COM8")   # your actual Arduino port
# # # #             self.arduino.connect(port)
# # # #             save_memory("Arduino_COM", port)
# # # #             self.log(f"[Arduino] Connected on {port}")
# # # #             self.sf6_window.sf6_panel.lamp.set_status("green", "Connected")

# # # #             # Start Arduino stream worker for continuous data reading
# # # #             self.arduino_stream = ArduinoStreamWorker(self.arduino)
# # # #             self.arduino_stream.data_signal.connect(self.on_analog_data)
# # # #             self.arduino_stream.error_signal.connect(lambda msg: self.log(f"[Arduino Stream ERROR] {msg}"))
# # # #             self.arduino_stream.start()
# # # #             self.log("[Arduino] Stream worker started")

# # # #         except Exception as e:
# # # #             self.log(f"[Arduino] NOT CONNECTED: {e}")
# # # #             self.sf6_window.sf6_panel.lamp.set_status("red", "Not Connected")


# # # #         # ------------------------------
# # # #         # WJ HIGH VOLTAGE SUPPLY
# # # #         # ------------------------------
# # # #         # try:
# # # #         #     port = self.conn.get("WJ_COM", "COM6")
# # # #         #     self.wj.connect(port)
# # # #         #     save_memory("WJ_COM", port)
# # # #         #     self.log(f"[WJ] Connected on {port}")
# # # #         #     self.wj_panel.lamp.set_status("green", "Connected")

# # # #         # except Exception as e:
# # # #         #     self.log(f"[WJ] NOT CONNECTED: {e}")
# # # #         #     self.wj_panel.lamp.set_status("red", "Not Connected")

# # # #         # ------------------------------
# # # #         # WJ HIGH VOLTAGE SUPPLIES
# # # #         # ------------------------------
# # # #         default_wj_ports = ["COM6", "COM11"]  # Default ports for WJ1 and WJ2
# # # #         for i, wj in enumerate(self.wj_units):
# # # #             try:
# # # #                 port = self.conn.get(f"WJ{i+1}_COM", default_wj_ports[i])
# # # #                 wj.connect(port)
# # # #                 self.wj_panel.rows[i].lamp.set_status("green", "Connected")
# # # #                 self.log(f"[WJ{i+1}] Connected on {port}")
# # # #             except Exception as e:
# # # #                 self.wj_panel.rows[i].lamp.set_status("red", "Not Connected")
# # # #                 self.log(f"[WJ{i+1}] NOT CONNECTED: {e}")


# # # #         # ------------------------------
# # # #         # Rigol Oscilloscopes
# # # #         # ------------------------------
# # # #         rigol_state_map = {
# # # #             "Rigol1_VISA": ("rigol1_connected", self.rigol1),
# # # #             "Rigol2_VISA": ("rigol2_connected", self.rigol2),
# # # #             "Rigol3_VISA": ("rigol3_connected", self.rigol3),
# # # #         }

# # # #         for key, (flag_name, scope) in rigol_state_map.items():
# # # #             try:
# # # #                 visa_addr = self.conn.get(key, "")
# # # #                 if visa_addr:
# # # #                     scope.resource_str = visa_addr

# # # #                 scope.connect()
# # # #                 idn = scope.identify()

# # # #                 setattr(self, flag_name, True)
# # # #                 save_memory(key, scope.resource_str)

# # # #                 self.log(f"[AutoConnect] {key} CONNECTED → {idn}")
# # # #                 if key == "Rigol1_VISA":
# # # #                     self.rigol_panel.lamp_r1.set_status("green", "Connected")
# # # #                 elif key == "Rigol2_VISA":
# # # #                     self.rigol_panel.lamp_r2.set_status("green", "Connected")
# # # #                 elif key == "Rigol3_VISA":
# # # #                     self.rigol_panel.lamp_r3.set_status("green", "Connected")

# # # #             except Exception as e:
# # # #                 setattr(self, flag_name, False)
# # # #                 self.log(f"[AutoConnect] {key} NOT CONNECTED: {e}")
# # # #                 if key == "Rigol1_VISA":
# # # #                     self.rigol_panel.lamp_r1.set_status("red", "Not Connected")
# # # #                 elif key == "Rigol2_VISA":
# # # #                     self.rigol_panel.lamp_r2.set_status("red", "Not Connected")
# # # #                 elif key == "Rigol3_VISA":
# # # #                     self.rigol_panel.lamp_r3.set_status("red", "Not Connected")


# # # #         self.log("=== Auto-connect done ===")






# # # #     # ------------------------------------------------------------------
# # # #     #  SF6 Window Connection
# # # #     # ------------------------------------------------------------------
# # # #     def connect_sf6_window(self):
# # # #         """Connect signals from SF6 window to main window handlers"""
# # # #         sf6_panel = self.sf6_window.sf6_panel

# # # #         # connect Arduino + switches
# # # #         sf6_panel.btn_connect.clicked.connect(self.on_arduino_connect)
# # # #         sf6_panel.btn_disconnect.clicked.connect(self.on_arduino_disconnect)
# # # #         # Explicit physical mapping for each GUI switch
# # # #         # Order: [GUI0, GUI1, GUI2, GUI3, GUI4, GUI5, GUI6, GUI7]
# # # #         # GUI index → Physical DO mapping
# # # #         sf6_output_map = {
# # # #             0: 0,   # GUI: Marx 1 Supply → DO00
# # # #             1: 4,   # GUI: Marx 1 Return → DO04
# # # #             2: 1,   # GUI: Marx 2 Supply → DO01
# # # #             3: 5,   # GUI: Marx 2 Return → DO05
# # # #             4: 2,   # GUI: Marx 3 Supply → DO02
# # # #             5: 6,   # GUI: Marx 3 Return → DO06
# # # #             6: 3,   # GUI: Marx 4 Supply → DO03
# # # #             7: 7,   # GUI: Marx 4 Return → DO07
# # # #         }

# # # #         for gui_i, sw in enumerate(sf6_panel.switches):
# # # #             physical_do = sf6_output_map[gui_i]
# # # #             sw.stateChanged.connect(lambda on, do=physical_do:
# # # #                         self.on_sf6_switch_changed(do, 1 if on else 0))

# # # #         # Duplicate WJ controls under the plot
# # # #         sw = self.sf6_window
# # # #         sw.btn_apply_program.clicked.connect(
# # # #             lambda: self.on_wj_set_voltage(sw.program_voltage.value(), sw.program_current.value())
# # # #         )
# # # #         sw.btn_hv_on.clicked.connect(self.on_wj_hv_on)
# # # #         sw.btn_hv_off.clicked.connect(self.on_wj_hv_off)
# # # #         sw.btn_reset.clicked.connect(self.on_wj_reset)
# # # #         sw.btn_read.clicked.connect(self.on_wj_read)

# # # #         for i in range(len(sw.wj_port_combos)):
# # # #             sw.btn_wj_connect[i].clicked.connect(
# # # #                 lambda _, idx=i: self.on_wj_connect(idx, sw.wj_port_combos[idx].currentText())
# # # #             )
# # # #             sw.btn_wj_disconnect[i].clicked.connect(
# # # #                 lambda _, idx=i: self.on_wj_disconnect(idx)
# # # #             )

# # # #         # If Arduino connected during auto-connect:
# # # #         if hasattr(self.arduino, "serial") and self.arduino.serial:
# # # #             sf6_panel.lamp.set_status("green", "Connected")
# # # #         else:
# # # #             sf6_panel.lamp.set_status("red", "Not Connected")


# # # #     def on_export_csv(self):
# # # #         try:
# # # #             saved_files = []

# # # #             if self.rigol1_connected:
# # # #                 f = self.rigol1.export_csv("rigol1")
# # # #                 saved_files.append(f)

# # # #             if self.rigol2_connected:
# # # #                 f = self.rigol2.export_csv("rigol2")
# # # #                 saved_files.append(f)

# # # #             if self.rigol3_connected:
# # # #                 f = self.rigol3.export_csv("rigol3")
# # # #                 saved_files.append(f)

# # # #             if not saved_files:
# # # #                 self.error_popup("No Data", "No scopes are connected.")
# # # #                 return

# # # #             msg = "Saved:\n" + "\n".join(saved_files)
# # # #             self.log(msg)
# # # #             self.set_status("green", "Waveforms exported")

# # # #         except Exception as e:
# # # #             self.error_popup("CSV Export Error", str(e))
# # # #             self.log(f"[CSV ERROR] {e}")


# # # #     # ------------------------------------------------------------------
# # # #     #  Helpers
# # # #     # ------------------------------------------------------------------
# # # #     def log(self, msg: str):
# # # #         self.log_panel.log(msg)

# # # #     def set_status(self, color: str, text: str):
# # # #         self.status_lamp.set_status(color, text)

# # # #     def error_popup(self, title: str, text: str):
# # # #         QMessageBox.critical(self, title, text)

# # # #     def refresh_arduino_ports(self):
# # # #         ports = list_serial_ports()
# # # #         sf6_panel = self.sf6_window.sf6_panel
# # # #         sf6_panel.port_list.clear()
# # # #         if not ports:
# # # #             sf6_panel.port_list.addItem("No COM ports")
# # # #         else:
# # # #             sf6_panel.port_list.addItems(ports)


# # # #     # ------------------------------------------------------------------
# # # #     #  DG535 Handlers
# # # #     # ------------------------------------------------------------------
# # # #     def on_dg_connect(self):
# # # #         # Change port name if needed
# # # #         port = "COM4"
# # # #         try:
# # # #             self.set_status("yellow", f"Connecting DG535 on {port}...")
# # # #             self.log(f"[DG535] Connecting on {port}...")
# # # #             self.dg.connect(port=port, gpib_addr=15)
# # # #             save_memory("DG535_COM", port)
# # # #             self.set_status("green", "DG535 connected")
# # # #             self.log("[DG535] Connected.")
# # # #         except Exception as e:
# # # #             self.set_status("red", "DG535 connection failed")
# # # #             self.log(f"[DG535 ERROR] {e}")
# # # #             self.error_popup("DG535 Error", str(e))

# # # #     def on_dg_fire(self):
# # # #         try:
# # # #             # Get values in seconds using the unit selector buttons
# # # #             delayA = self.dg_panel.get_delayA()
# # # #             widthA = self.dg_panel.get_widthA()

# # # #             self.log(f"[DG535] Config pulse A: delay={delayA:.3e}, width={widthA:.3e}")
# # # #             self.set_status("yellow", "Configuring DG535...")
# # # #             self.dg.configure_pulse_A(delayA, widthA)
# # # #             self.data_logger.log_dg535_config(delayA, widthA)

# # # #             self.dg.set_single_shot()
# # # #             self.dg.fire()
# # # #             self.data_logger.log_dg535_pulse(delayA, widthA)

# # # #             self.set_status("green", "DG535 pulse fired")
# # # #             self.log("[DG535] Pulse fired.")
# # # #         except Exception as e:
# # # #             self.set_status("red", "DG535 fire failed")
# # # #             self.log(f"[DG535 ERROR] {e}")
# # # #             self.data_logger.log_error("DG535", str(e))
# # # #             self.error_popup("DG535 Fire Error", str(e))

# # # #     def on_dg_disconnect(self):
# # # #         try:
# # # #             self.dg.close()
# # # #         except:
# # # #             pass
# # # #         self.dg_panel.lamp.set_status("red", "Disconnected")
# # # #         self.log("[DG535] Disconnected")
# # # #     # ------------------------------------------------------------------
# # # #     #  BNC575 Handlers
# # # #     # ------------------------------------------------------------------

# # # #     def on_bnc_connect(self):
# # # #         port = "COM5"
# # # #         try:
# # # #             self.set_status("yellow", f"Connecting BNC575 on {port}...")
# # # #             self.log(f"[BNC575] Connecting on {port}...")
# # # #             self.bnc.connect(port=port)

# # # #             idn = self.bnc.identify()
# # # #             save_memory("BNC575_COM", port)

# # # #             self.set_status("green", "BNC575 connected")
# # # #             self.log(f"[BNC575] Connected: {idn}")

# # # #             self.bnc_panel.widthA.setValue(1e-6)
# # # #             self.bnc_panel.delayA.setValue(0)
# # # #             self.bnc_panel.widthB.setValue(1e-6)
# # # #             self.bnc_panel.delayB.setValue(0)
# # # #             self.bnc_panel.widthC.setValue(40e-6)
# # # #             self.bnc_panel.delayC.setValue(0)
# # # #             self.bnc_panel.widthD.setValue(40e-6)
# # # #             self.bnc_panel.delayD.setValue(0)

# # # #         except Exception as e:
# # # #             self.set_status("red", "BNC575 connection failed")
# # # #             self.log(f"[BNC575 ERROR] {e}")
# # # #             self.error_popup("BNC575 Error", str(e))


# # # #     def on_bnc_disconnect(self):
# # # #         try:
# # # #             self.bnc.close()
# # # #         except:
# # # #             pass
# # # #         self.bnc_panel.lamp.set_status("red", "Disconnected")
# # # #         self.log("[BNC575] Disconnected")
# # # #         self.bnc_connected = False

# # # #     def on_bnc_apply(self):
# # # #         try:
# # # #             # Get values in seconds using the unit selector buttons
# # # #             wA = self.bnc_panel.get_widthA()
# # # #             dA = self.bnc_panel.get_delayA()
# # # #             wB = self.bnc_panel.get_widthB()
# # # #             dB = self.bnc_panel.get_delayB()
# # # #             wC = self.bnc_panel.get_widthC()
# # # #             dC = self.bnc_panel.get_delayC()
# # # #             wD = self.bnc_panel.get_widthD()
# # # #             dD = self.bnc_panel.get_delayD()

# # # #             self.bnc.apply_settings(wA, dA, wB, dB, wC, dC, wD, dD)
# # # #             self.data_logger.log_bnc575_config(wA, dA, wB, dB, wC, dC, wD, dD)

# # # #             self.log("[BNC575] Settings applied.")
# # # #             self.set_status("green", "BNC575 settings applied")

# # # #         except Exception as e:
# # # #             self.set_status("red", "BNC575 apply failed")
# # # #             self.data_logger.log_error("BNC575", str(e))
# # # #             self.error_popup("BNC575 Error", str(e))

# # # #     #         self.error_popup("BNC575 Read Error", str(e))
# # # #     def on_bnc_read(self):
# # # #         try:
# # # #             # wA, dA, wB, dB, wC, dC, wD, dD = self.bnc.read_settings()
# # # #             vals = self.bnc.read_settings()
# # # #             wA, dA, wB, dB, wC, dC, wD, dD = vals

# # # #             self.bnc_panel.widthA.setValue(wA)
# # # #             self.bnc_panel.delayA.setValue(dA)
# # # #             self.bnc_panel.widthB.setValue(wB)
# # # #             self.bnc_panel.delayB.setValue(dB)
# # # #             self.bnc_panel.widthC.setValue(wC)
# # # #             self.bnc_panel.delayC.setValue(dC)
# # # #             self.bnc_panel.widthD.setValue(wD)
# # # #             self.bnc_panel.delayD.setValue(dD)

# # # #             self.set_status("green", "BNC575 settings read")

# # # #         except Exception as e:
# # # #             self.set_status("red", "BNC575 read failed")
# # # #             self.error_popup("BNC575 Read Error", str(e))

# # # #     def on_bnc_arm(self):
# # # #         try:
# # # #             source = self.bnc_panel.trig_source.currentText()
# # # #             slope = self.bnc_panel.trig_slope.currentText()
# # # #             level = self.bnc_panel.trig_level.value()

# # # #             if not self.bnc_trigger_armed:
# # # #                 # Apply trigger settings from GUI then arm
# # # #                 self.bnc.set_trigger_settings(source, slope, level)
# # # #                 self.bnc.arm_trigger()
# # # #                 self.bnc_trigger_armed = True
# # # #                 self.bnc_panel.btn_arm.setText("Disarm (EXT TRIG)")
# # # #                 self.data_logger.log_bnc575_arm(level)
# # # #                 self.set_status("green", "BNC575 armed (EXT)")
# # # #                 self.log(f"[BNC575] Armed for external trigger: {source}/{slope} @ {level:.2f} V")
# # # #             else:
# # # #                 # Disarm
# # # #                 self.bnc.disarm_trigger()
# # # #                 self.bnc_trigger_armed = False
# # # #                 self.bnc_panel.btn_arm.setText("Arm (EXT TRIG)")
# # # #                 self.set_status("yellow", "BNC575 disarmed")
# # # #                 self.log("[BNC575] Disarmed external trigger")
# # # #         except Exception as e:
# # # #             self.set_status("red", "BNC575 arm failed")
# # # #             self.log(f"[BNC575 ERROR] {e}")
# # # #             self.data_logger.log_error("BNC575", str(e))
# # # #             self.error_popup("BNC575 Arm Error", str(e))


# # # #     def on_bnc_fire(self):
# # # #         try:
# # # #             self.set_status("yellow", "Firing BNC575 internal pulse...")
# # # #             self.bnc.fire_internal()
# # # #             self.data_logger.log_bnc575_pulse(mode='INTERNAL')
# # # #             self.set_status("green", "BNC575 internal fired")
# # # #             self.log("[BNC575] Internal pulse fired.")
# # # #         except Exception as e:
# # # #             self.set_status("red", "BNC575 fire failed")
# # # #             self.log(f"[BNC575 ERROR] {e}")
# # # #             self.data_logger.log_error("BNC575", str(e))
# # # #             self.error_popup("BNC575 Fire Error", str(e))

# # # #     def on_bnc_apply_trigger(self):
# # # #         source = self.bnc_panel.trig_source.currentText()
# # # #         slope = self.bnc_panel.trig_slope.currentText()
# # # #         level = self.bnc_panel.trig_level.value()
# # # #         try:
# # # #             self.bnc.set_trigger_settings(source, slope, level)
# # # #             self.log(f"[BNC575] Trigger settings applied: {source}, {slope}, {level:.2f} V")
# # # #             self.set_status("green", "Trigger settings applied")
# # # #         except Exception as e:
# # # #             self.error_popup("BNC575 Trigger Error", str(e))
# # # #             self.log(f"[BNC575 ERROR] {e}")

# # # #     def on_bnc_enable_channel(self, channel: str, enabled: bool):
# # # #         try:
# # # #             self.bnc.enable_output(channel, enabled)
# # # #             self.log(f"[BNC575] {channel} {'ENABLED' if enabled else 'DISABLED'}")
# # # #         except Exception as e:
# # # #             self.error_popup("BNC575 Channel Error", str(e))
# # # #             self.log(f"[BNC575 ERROR] {e}")

# # # #     def on_bnc_enable_trigger(self, enabled: bool):
# # # #         try:
# # # #             # Just enable/disable the trigger output, don't automatically arm
# # # #             self.bnc.enable_trigger(enabled)
# # # #             # Don't change armed state - user must press "Arm" button separately
# # # #             self.log(f"[BNC575] Trigger output {'ENABLED' if enabled else 'DISABLED'}")
# # # #         except Exception as e:
# # # #             self.error_popup("BNC575 Trigger Error", str(e))
# # # #             self.log(f"[BNC575 ERROR] {e}")


# # # #     # ------------------------------------------------------------------
# # # #     #  Rigol Handlers
# # # #     # ------------------------------------------------------------------
# # # #     def on_rigol1_connect(self):
# # # #         try:
# # # #             self.set_status("yellow", "Connecting Rigol #1...")
# # # #             # self.rigol1.connect()
# # # #             # idn = self.rigol1.identify()
# # # #             # self.rigol1_connected = True
# # # #             self.rigol1.connect()
# # # #             idn = self.rigol1.identify()
# # # #             save_memory("Rigol1_VISA", self.rigol1.resource_str)
# # # #             self.rigol1_connected = True

# # # #             self.set_status("green", "Rigol #1 connected")
# # # #             self.log(f"[Rigol1] {idn}")
# # # #         except Exception as e:
# # # #             self.rigol1_connected = False
# # # #             self.set_status("red", "Rigol #1 connection failed")
# # # #             self.log(f"[Rigol1 ERROR] {e}")
# # # #             self.error_popup("Rigol #1 Error", str(e))

# # # #     def on_rigol2_connect(self):
# # # #         try:
# # # #             self.set_status("yellow", "Connecting Rigol #2...")
# # # #             # self.rigol2.connect()
# # # #             # idn = self.rigol2.identify()
# # # #             # self.rigol2_connected = True
# # # #             self.rigol2.connect()
# # # #             idn = self.rigol2.identify()
# # # #             save_memory("Rigol2_VISA", self.rigol2.resource_str)
# # # #             self.rigol2_connected = True
# # # #             self.set_status("green", "Rigol #2 connected")
# # # #             self.log(f"[Rigol2] {idn}")
# # # #         except Exception as e:
# # # #             self.rigol2_connected = False
# # # #             self.set_status("red", "Rigol #2 connection failed")
# # # #             self.log(f"[Rigol2 ERROR] {e}")
# # # #             self.error_popup("Rigol #2 Error", str(e))

# # # #     def on_rigol3_connect(self):
# # # #         try:
# # # #             self.set_status("yellow", "Connecting Rigol #3...")
# # # #             # self.rigol3.connect()
# # # #             # idn = self.rigol3.identify()
# # # #             # self.rigol3_connected = True
# # # #             self.rigol3.connect()
# # # #             idn = self.rigol3.identify()
# # # #             save_memory("Rigol3_VISA", self.rigol3.resource_str)
# # # #             self.rigol3_connected = True
# # # #             self.set_status("green", "Rigol #3 connected")
# # # #             self.log(f"[Rigol3] {idn}")
# # # #         except Exception as e:
# # # #             self.rigol3_connected = False
# # # #             self.set_status("red", "Rigol #3 connection failed")
# # # #             self.log(f"[Rigol3 ERROR] {e}")
# # # #             self.error_popup("Rigol #3 Error", str(e))
# # # #     # def _capture_single_scope(self, rigol, plot_widget, name):
# # # #     #         try:
# # # #     #             self.set_status("yellow", f"Capturing {name}...")
# # # #     #             self.log(f"[{name}] Preparing for capture...")

# # # #     #             rigol.inst.write(":STOP;:SINGLE")
# # # #     #             time.sleep(0.2)

# # # #     #             (t1, v1), (t2, v2) = rigol.wait_and_capture()

# # # #     #             plot_widget.plot(t1, v1, pen="r")
# # # #     #             plot_widget.plot(t2, v2, pen="b")

# # # #     #             self.set_status("green", f"{name} captured")
# # # #     #             self.log(f"[{name}] Capture complete.")

# # # #     #         except Exception as e:
# # # #     #             self.error_popup(f"{name} Capture Error", str(e))
# # # #     #             self.log(f"[{name} ERROR] {e}")
# # # #     def _capture_single_scope(self, rigol, plot_widget, name):
# # # #         try:
# # # #             # ⭐ CLEAR BEFORE PLOTTING
# # # #             plot_widget.clear()

# # # #             self.set_status("yellow", f"Capturing {name}...")
# # # #             self.log(f"[{name}] Preparing for capture...")

# # # #             # rigol.inst.write(":STOP;:SINGLE")
# # # #             rigol.inst.write(":STOP")
# # # #             rigol.inst.write(":SINGLE")
# # # #             time.sleep(0.2)

# # # #             (t1, v1), (t2, v2) = rigol.wait_and_capture()

# # # #             plot_widget.plot(t1, v1, pen="r")
# # # #             plot_widget.plot(t2, v2, pen="b")

# # # #             self.set_status("green", f"{name} captured")
# # # #             self.log(f"[{name}] Capture complete.")

# # # #         except Exception as e:
# # # #             self.error_popup(f"{name} Capture Error", str(e))
# # # #             self.log(f"[{name} ERROR] {e}")


# # # #     def on_capture_r1(self):
# # # #         if not self.rigol1_connected:
# # # #             self.error_popup("Rigol #1", "Not connected.")
# # # #             return
# # # #         self.start_single_capture(self.rigol1, self.scope_window.plot1, "Rigol #1")


# # # #     def on_capture_r2(self):
# # # #         if not self.rigol2_connected:
# # # #             self.error_popup("Rigol #2", "Not connected.")
# # # #             return
# # # #         self.start_single_capture(self.rigol2, self.scope_window.plot2, "Rigol #2")


# # # #     def on_capture_r3(self):
# # # #         if not self.rigol3_connected:
# # # #             self.error_popup("Rigol #3", "Not connected.")
# # # #             return
# # # #         self.start_single_capture(self.rigol3, self.scope_window.plot3, "Rigol #3")
# # # #     def start_single_capture(self, rigol, plot_widget, name):
# # # #         self.set_status("yellow", f"Capturing {name}...")
# # # #         self.log(f"[{name}] capture started...")

# # # #         rigol.arm()
        
# # # #         self.single_worker = CaptureSingleWorker(rigol, name)
# # # #         self.single_worker.finished.connect(lambda ch1, ch2, nm: self.on_single_capture_finished(ch1, ch2, plot_widget, nm))
# # # #         self.single_worker.error.connect(lambda msg: self.on_single_capture_error(msg, name))
# # # #         self.single_worker.start()

# # # #     def on_r1_disconnect(self):
# # # #         try:
# # # #             self.rigol1.close()
# # # #         except:
# # # #             pass
# # # #         self.rigol_panel.lamp_r1.set_status("red", "Disconnected")
# # # #         self.log("[Rigol1] Disconnected")
# # # #         self.rigol1_connected = False

# # # #     def on_r2_disconnect(self):
# # # #         try:
# # # #             self.rigol2.close()
# # # #         except:
# # # #             pass
# # # #         self.rigol_panel.lamp_r2.set_status("red", "Disconnected")
# # # #         self.log("[Rigol2] Disconnected")
# # # #         self.rigol2_connected = False

# # # #     def on_r3_disconnect(self):
# # # #         try:
# # # #             self.rigol3.close()
# # # #         except:
# # # #             pass
# # # #         self.rigol_panel.lamp_r3.set_status("red", "Disconnected")
# # # #         self.log("[Rigol3] Disconnected")
# # # #         self.rigol3_connected = False



# # # #     # def on_single_capture_finished(self, ch1, ch2, plot_widget, name):
# # # #     #     (t1, v1) = ch1
# # # #     #     (t2, v2) = ch2

# # # #     #     plot_widget.clear()
# # # #     #     plot_widget.plot(t1, v1, pen="r")
# # # #     #     plot_widget.plot(t2, v2, pen="b")

# # # #     #     self.set_status("green", f"{name} captured")
# # # #     #     self.log(f"[{name}] capture complete.")
# # # #     def on_single_capture_finished(self, ch1, ch2, plot_widget, name):
# # # #         (t1, v1) = ch1
# # # #         (t2, v2) = ch2

# # # #         # Log scope capture
# # # #         scope_id = 0
# # # #         if plot_widget == self.scope_window.plot1:
# # # #             self.scope_window.update_r1(t1, v1, t2, v2)
# # # #             scope_id = 1
# # # #         elif plot_widget == self.scope_window.plot2:
# # # #             self.scope_window.update_r2(t1, v1, t2, v2)
# # # #             scope_id = 2
# # # #         elif plot_widget == self.scope_window.plot3:
# # # #             self.scope_window.update_r3(t1, v1, t2, v2)
# # # #             scope_id = 3

# # # #         self.data_logger.log_scope_capture(scope_id, len(t1), len(t2))

# # # #         self.set_status("green", f"{name} captured")
# # # #         self.log(f"[{name}] capture complete.")



# # # #     def on_single_capture_error(self, msg, name):
# # # #         self.set_status("red", f"{name} error")
# # # #         self.error_popup(f"{name} Capture Error", msg)
# # # #         self.log(f"[{name} ERROR] {msg}")


    

# # # #     def on_capture_all_scopes(self):
# # # #         self.set_status("yellow", "Preparing for capture...")
# # # #         self.log("[CAPTURE] Starting threaded capture...")

# # # #         # -------------------------------------------
# # # #         # 1. STOP and ARM all Rigols early
# # # #         # -------------------------------------------
# # # #         try:
# # # #             if self.rigol1_connected:
# # # #                 self.rigol1.inst.write(":STOP;:SINGLE")
# # # #                 self.data_logger.log_scope_arm(1)
# # # #             if self.rigol2_connected:
# # # #                 self.rigol2.inst.write(":STOP;:SINGLE")
# # # #                 self.data_logger.log_scope_arm(2)
# # # #             if self.rigol3_connected:
# # # #                 self.rigol3.inst.write(":STOP;:SINGLE")
# # # #                 self.data_logger.log_scope_arm(3)

# # # #             self.log("[CAPTURE] Rigols set to SINGLE")
# # # #         except Exception as e:
# # # #             self.error_popup("Rigol Error", f"Failed to arm scopes: {e}")
# # # #             self.data_logger.log_error("SCOPE", str(e))
# # # #             return

# # # #         # Allow scopes to settle into WAIT mode
# # # #         time.sleep(0.25)

# # # #         # -------------------------------------------
# # # #         # 2. ARM BNC575 for external trigger
# # # #         # -------------------------------------------
# # # #         try:
# # # #             self.bnc.arm_external_trigger(level=3.0)
# # # #             self.data_logger.log_bnc575_arm(3.0)
# # # #             self.log("[BNC575] Armed for external trigger")
# # # #         except Exception as e:
# # # #             self.error_popup("BNC575 Error", str(e))
# # # #             self.data_logger.log_error("BNC575", str(e))
# # # #             return

# # # #         # -------------------------------------------
# # # #         # 3. CONFIGURE DG535 but DO NOT FIRE YET
# # # #         # -------------------------------------------
# # # #         try:
# # # #             # Get values in seconds using the unit selector buttons
# # # #             delayA = self.dg_panel.get_delayA()
# # # #             widthA = self.dg_panel.get_widthA()
# # # #             self.dg.configure_pulse_A(delayA, widthA)
# # # #             self.data_logger.log_dg535_config(delayA, widthA)
# # # #             self.dg.set_single_shot()
# # # #         except Exception as e:
# # # #             self.error_popup("DG535 Error", str(e))
# # # #             self.data_logger.log_error("DG535", str(e))
# # # #             return

# # # #         # Small delay before firing
# # # #         time.sleep(0.2)

# # # #         # -------------------------------------------
# # # #         # 4. FIRE DG535 (MASTER TRIGGER)
# # # #         # -------------------------------------------
# # # #         self.log("[CAPTURE] Firing DG535...")
# # # #         try:
# # # #             self.dg.fire()
# # # #             self.data_logger.log_dg535_pulse(delayA, widthA)
# # # #             self.log("[DG535] Trigger pulse fired.")
# # # #         except Exception as e:
# # # #             self.error_popup("DG535 Fire Error", str(e))
# # # #             self.data_logger.log_error("DG535", str(e))
# # # #             return

# # # #         # Wait for scopes to acquire
# # # #         time.sleep(0.5)

# # # #         # -------------------------------------------
# # # #         # 5. CAPTURE waveforms
# # # #         # -------------------------------------------
# # # #         self.set_status("yellow", "Capturing waveforms...")

# # # #         if self.rigol1_connected:
# # # #             (t1, v1), (t2, v2) = self.rigol1.wait_and_capture()
# # # #             self.scope_window.update_r1(t1, v1, t2, v2)
# # # #             self.data_logger.log_scope_capture(1, len(t1), len(t2))

# # # #         if self.rigol2_connected:
# # # #             (t1, v1), (t2, v2) = self.rigol2.wait_and_capture()
# # # #             self.scope_window.update_r2(t1, v1, t2, v2)
# # # #             self.data_logger.log_scope_capture(2, len(t1), len(t2))

# # # #         if self.rigol3_connected:
# # # #             (t1, v1), (t2, v2) = self.rigol3.wait_and_capture()
# # # #             self.scope_window.update_r3(t1, v1, t2, v2)
# # # #             self.data_logger.log_scope_capture(3, len(t1), len(t2))

# # # #         # Log master capture event
# # # #         self.data_logger.log_scope_all_capture()

# # # #         self.set_status("green", "Capture complete")
# # # #         self.log("[CAPTURE] Done.")


        
# # # #     def _capture_error(self, msg):
# # # #         self.set_status("red", "Capture error")
# # # #         self.log(f"[CAPTURE ERROR] {msg}")
# # # #         self.error_popup("Capture Error", msg)

# # # #     def _capture_log(self, msg):
# # # #         self.log("[CAPTURE] " + msg)
# # # #         self.set_status("yellow", msg)

# # # #     def _plot_capture(self, index, data):
# # # #         (t1, v1), (t2, v2) = data

# # # #         if index == 0:
# # # #             # p = self.scope_plots.plot1
# # # #             p = self.scope_window.plot1
# # # #         elif index == 1:
# # # #             p = self.scope_window.plot2
# # # #         else:
# # # #             p = self.scope_window.plot3

# # # #         # p.plot(t1, v1, pen="r")
# # # #         # p.plot(t2, v2, pen="b")
# # # #         if index == 0:
# # # #             self.scope_window.update_r1(t1, v1, t2, v2)
# # # #         elif index == 1:
# # # #             self.scope_window.update_r2(t1, v1, t2, v2)
# # # #         elif index == 2:
# # # #             self.scope_window.update_r3(t1, v1, t2, v2)


# # # #     def on_r1_single(self):
# # # #         try:
# # # #             if self.rigol1_connected:
# # # #                 self.rigol1.arm()
# # # #                 self.log("[Rigol1] Set to SINGLE")
# # # #                 self.set_status("green", "Rigol1 SINGLE")
# # # #             else:
# # # #                 self.error_popup("Rigol1", "Not connected.")
# # # #         except Exception as e:
# # # #             self.error_popup("Rigol1 Error", str(e))

# # # #     def on_r2_single(self):
# # # #         try:
# # # #             if self.rigol2_connected:
# # # #                 self.rigol2.arm()
# # # #                 self.log("[Rigol2] Set to SINGLE")
# # # #                 self.set_status("green", "Rigol2 SINGLE")
# # # #             else:
# # # #                 self.error_popup("Rigol2", "Not connected.")
# # # #         except Exception as e:
# # # #             self.error_popup("Rigol2 Error", str(e))

# # # #     def on_r3_single(self):
# # # #         try:
# # # #             if self.rigol3_connected:
# # # #                 self.rigol3.arm()
# # # #                 self.log("[Rigol3] Set to SINGLE")
# # # #                 self.set_status("green", "Rigol3 SINGLE")
# # # #             else:
# # # #                 self.error_popup("Rigol3", "Not connected.")
# # # #         except Exception as e:
# # # #             self.error_popup("Rigol3 Error", str(e))



# # # #     # ------------------------------------------------------------------
# # # #     #  Arduino / SF6 Handlers
# # # #     # ------------------------------------------------------------------

# # # #     def on_arduino_connect(self):
# # # #         sf6_panel = self.sf6_window.sf6_panel
# # # #         port = sf6_panel.port_list.currentText()
# # # #         if port == "No COM ports":
# # # #             self.error_popup("Arduino", "No COM ports found.")
# # # #             return
# # # #         try:
# # # #             # ensure previous stream is stopped cleanly
# # # #             if hasattr(self, "arduino_stream") and self.arduino_stream:
# # # #                 self.arduino_stream.stop()
# # # #                 self.arduino_stream = None
# # # #             self.set_status("yellow", f"Connecting Arduino on {port}...")
# # # #             self.arduino.connect(port)
# # # #             save_memory("Arduino_COM", port)

# # # #             self.set_status("green", "Arduino connected")
# # # #             self.log(f"[Arduino] Connected on {port}")
# # # #             sf6_panel.lamp.set_status("green", "Connected")

# # # #             self.arduino_stream = ArduinoStreamWorker(self.arduino)
# # # #             self.arduino_stream.data_signal.connect(self.on_analog_data)
# # # #             self.arduino_stream.error_signal.connect(lambda msg: self.log(f"[Arduino Stream ERROR] {msg}"))
# # # #             self.arduino_stream.start()

# # # #         except Exception as e:
# # # #             self.set_status("red", "Arduino connection failed")
# # # #             self.log(f"[Arduino ERROR] {e}")
# # # #             sf6_panel.lamp.set_status("red", "Error")
# # # #             self.error_popup("Arduino Error", str(e))
# # # #     def on_analog_data(self, ch0, ch1, ch2):
# # # #         def mA_to_psi(mA):
# # # #             if mA < 4:
# # # #                 return 0
# # # #             if mA > 20:
# # # #                 return 200
# # # #             return (mA - 4.0) * 12.5

# # # #         psi0 = mA_to_psi(ch0)
# # # #         psi1 = mA_to_psi(ch1)
# # # #         psi2 = mA_to_psi(ch2)

# # # #         # Log Arduino data
# # # #         try:
# # # #             self.data_logger.log_arduino_psi(psi0, psi1, psi2)
# # # #         except Exception as e:
# # # #             self.log(f"[DataLogger ERROR] Failed to log Arduino data: {e}")

# # # #         sf6_panel = self.sf6_window.sf6_panel
# # # #         sf6_panel.ai_ch0.update_value(psi0)
# # # #         sf6_panel.ai_ch1.update_value(psi1)
# # # #         sf6_panel.ai_ch2.update_value(psi2)


# # # #     def on_sf6_switch_changed(self, index: int, state: int):
# # # #         """index = 0..7, mapping to channels 0..7 like your MATLAB app."""
# # # #         try:
# # # #             if state:  # checked
# # # #                 cmd = f"on {index}"
# # # #             else:
# # # #                 cmd = f"off {index}"
# # # #             self.arduino.send(cmd)
# # # #             self.data_logger.log_arduino_switch(index, state)
# # # #             self.log(f"[Arduino] {cmd}")
# # # #         except Exception as e:
# # # #             self.log(f"[Arduino ERROR] {e}")
# # # #             self.data_logger.log_error("Arduino", str(e))
# # # #             self.error_popup("Arduino Send Error", str(e))


# # # #     # ------------------------------------------------------------------
# # # #     #  WJ HV POWER SUPPLY HANDLERS
# # # #     # ------------------------------------------------------------------


# # # #     # def on_wj_connect(self):
# # # #     #     try:
# # # #     #         port = "COM6"
# # # #     #         self.set_status("yellow", f"Connecting WJ on {port}...")
# # # #     #         self.wj.connect(port)

# # # #     #         save_memory("WJ_COM", port)

# # # #     #         self.set_status("green", "WJ Connected")
# # # #     #         self.log("[WJ] Connected on " + port)
# # # #     #     except Exception as e:
# # # #     #         self.set_status("red", "WJ connection failed")
# # # #     #         self.error_popup("WJ HV Supply", str(e))
# # # #     def on_wj_connect(self, index, port_override=None):
# # # #         row = self.wj_panel.rows[index]
# # # #         port = port_override or row.port_combo.currentText()

# # # #         # keep main panel combo in sync if override was used
# # # #         if port_override:
# # # #             row.port_combo.setCurrentText(port)

# # # #         if port == "No COM ports":
# # # #             self.log(f"[WJ{index+1}] No ports available")
# # # #             row.lamp.set_status("red", "No Ports")
# # # #             return

# # # #         try:
# # # #             self.log(f"[WJ{index+1}] Connecting on {port}...")
# # # #             self.wj_units[index].connect(port)
# # # #             save_memory(f"WJ{index+1}_COM", port)
# # # #             row.lamp.set_status("green", "Connected")
# # # #         except Exception as e:
# # # #             self.log(f"[WJ{index+1} ERROR] {e}")
# # # #             row.lamp.set_status("red", "Error")



# # # #     def on_arduino_disconnect(self):
# # # #         try:
# # # #             if hasattr(self, "arduino_stream"):
# # # #                 self.arduino_stream.stop()
# # # #                 self.arduino_stream = None
# # # #             self.arduino.close()
# # # #         except:
# # # #             pass

# # # #         sf6_panel = self.sf6_window.sf6_panel
# # # #         sf6_panel.lamp.set_status("red", "Disconnected")
# # # #         self.log("[Arduino] Disconnected")



# # # #     # def on_wj_hv_on(self):
# # # #     #     try:
# # # #     #         resp = self.wj.hv_on_pulse()
# # # #     #         self.log(f"[WJ] HV ON → {resp}")
# # # #     #         self.set_status("green", "HV ENABLED")
# # # #     #     except Exception as e:
# # # #     #         self.error_popup("WJ HV ON Error", str(e))


# # # #     def on_wj_hv_on(self):
# # # #         for i, wj in enumerate(self.wj_units):
# # # #             try:
# # # #                 resp = wj.hv_on_pulse()
# # # #                 self.data_logger.log_wj_command(i+1, "HV_ON")
# # # #                 self.log(f"[WJ{i+1}] HV ON → {resp}")
# # # #             except Exception as e:
# # # #                 self.log(f"[WJ{i+1} ERROR] {e}")
# # # #                 self.data_logger.log_error(f"WJ{i+1}", str(e))

# # # #     # def on_wj_hv_off(self):
# # # #     #     try:
# # # #     #         resp = self.wj.hv_off_pulse()
# # # #     #         self.log(f"[WJ] HV OFF → {resp}")
# # # #     #         self.set_status("yellow", "HV DISABLED")
# # # #     #     except Exception as e:
# # # #     #         self.error_popup("WJ HV OFF Error", str(e))
# # # #     def on_wj_hv_off(self):
# # # #         for i, wj in enumerate(self.wj_units):
# # # #             try:
# # # #                 resp = wj.hv_off_pulse()
# # # #                 self.data_logger.log_wj_command(i+1, "HV_OFF")
# # # #                 self.log(f"[WJ{i+1}] HV OFF → {resp}")
# # # #             except Exception as e:
# # # #                 self.log(f"[WJ{i+1} ERROR] {e}")
# # # #                 self.data_logger.log_error(f"WJ{i+1}", str(e))



# # # #     # def on_wj_reset(self):
# # # #     #     try:
# # # #     #         resp = self.wj.reset_pulse()
# # # #     #         self.log(f"[WJ] RESET → {resp}")
# # # #     #         self.set_status("yellow", "WJ Reset")
# # # #     #     except Exception as e:
# # # #     #         self.error_popup("WJ Reset Error", str(e))
# # # #     def on_wj_reset(self):
# # # #         for i, wj in enumerate(self.wj_units):
# # # #             try:
# # # #                 wj.reset_pulse()
# # # #                 self.data_logger.log_wj_command(i+1, "RESET")
# # # #                 self.log(f"[WJ{i+1}] Reset OK")
# # # #             except Exception as e:
# # # #                 self.log(f"[WJ{i+1} ERROR] {e}")
# # # #                 self.data_logger.log_error(f"WJ{i+1}", str(e))

# # # #     # def on_wj_set_voltage(self):
# # # #     #     try:
# # # #     #         kv = self.wj_panel.voltage.value()
# # # #     #         ma = self.wj_panel.current.value()
# # # #     #         resp = self.wj.set_program(kv, ma)
# # # #     #         self.log(f"[WJ] Set V={kv} kV I={ma} mA → {resp}")
# # # #     #         self.set_status("green", "WJ Program Set")
# # # #     #     except Exception as e:
# # # #     #         self.error_popup("WJ Voltage Error", str(e))
# # # #     def on_wj_set_voltage(self, kv=None, ma=None):
# # # #         if kv is None:
# # # #             kv = self.wj_panel.voltage.value()
# # # #         if ma is None:
# # # #             ma = self.wj_panel.current.value()

# # # #         for i, wj in enumerate(self.wj_units):
# # # #             try:
# # # #                 resp = wj.set_program(kv, ma)
# # # #                 self.data_logger.log_wj_command(i+1, "SET_PROGRAM", f"{kv}kV_{ma}mA")
# # # #                 self.log(f"[WJ{i+1}] Set → {kv} kV, {ma} mA ({resp})")
# # # #             except Exception as e:
# # # #                 self.log(f"[WJ{i+1} ERROR] {e}")
# # # #                 self.data_logger.log_error(f"WJ{i+1}", str(e))


# # # #     # def on_wj_disconnect(self):
# # # #     #     try:
# # # #     #         self.wj.close()
# # # #     #     except:
# # # #     #         pass
# # # #     #     self.wj_panel.lamp.set_status("red", "Disconnected")
# # # #     #     self.log("[WJ] Disconnected")
# # # #     def on_wj_disconnect(self, index):
# # # #         try:
# # # #             self.wj_units[index].close()
# # # #         except:
# # # #             pass

# # # #         self.wj_panel.rows[index].lamp.set_status("red", "Disconnected")
# # # #         self.log(f"[WJ{index+1}] Disconnected")


# # # #     # def on_wj_read(self):
# # # #     #     try:
# # # #     #         data = self.wj.query()
# # # #     #         self.log(f"[WJ] Readback: {data}")

# # # #     #         if data.get("type") != "R":
# # # #     #             self.wj_panel.label_status.setText("No R packet")
# # # #     #             return

# # # #     #         kv = data["kv"]
# # # #     #         ma = data["ma"]
# # # #     #         hv = data["hv_on"]
# # # #     #         fault = data["fault"]

# # # #     #         self.wj_panel.label_status.setText(
# # # #     #             f"{kv:.2f} kV | {ma:.3f} mA | HV={'ON' if hv else 'OFF'} | Fault={'YES' if fault else 'NO'}"
# # # #     #         )

# # # #     #     except Exception as e:
# # # #     #         self.error_popup("WJ Read Error", str(e))
# # # #     def on_wj_read(self):
# # # #         """Read back status from all WJ units and update each row in the panel."""
# # # #         for i, wj in enumerate(self.wj_units):

# # # #             try:
# # # #                 data = wj.query()
# # # #                 self.log(f"[WJ{i+1}] Readback: {data}")

# # # #                 # Get the label in the corresponding row
# # # #                 row = self.wj_panel.rows[i]

# # # #                 # No R packet?
# # # #                 if data.get("type") != "R":
# # # #                     row.label_status.setText("No R packet")
# # # #                     continue

# # # #                 # Parse values
# # # #                 kv = data.get("kv", 0.0)
# # # #                 ma = data.get("ma", 0.0)
# # # #                 hv = data.get("hv_on", False)
# # # #                 fault = data.get("fault", False)

# # # #                 # Log WJ voltage/current data
# # # #                 try:
# # # #                     self.data_logger.log_wj_voltage(i+1, kv, ma, hv, fault)
# # # #                 except Exception as e:
# # # #                     self.log(f"[DataLogger ERROR] Failed to log WJ{i+1} data: {e}")

# # # #                 # Update label for this WJ
# # # #                 row.label_status.setText(
# # # #                     f"{kv:.2f} kV | {ma:.3f} mA | "
# # # #                     f"HV={'ON' if hv else 'OFF'} | "
# # # #                     f"Fault={'YES' if fault else 'NO'}"
# # # #                 )

# # # #             except Exception as e:
# # # #                 self.log(f"[WJ{i+1} ERROR] {e}")
# # # #                 self.data_logger.log_error(f"WJ{i+1}", str(e))
# # # #                 row = self.wj_panel.rows[i]
# # # #                 row.label_status.setText("Read Error")




# # # #     def on_open_scope_window(self):
# # # #         self.scope_window.show()
# # # #         self.scope_window.raise_()
# # # #         self.scope_window.activateWindow()

# # # #     def closeEvent(self, event):
# # # #         """Handle main window close event - close all child windows"""
# # # #         # Stop WJ worker threads
# # # #         if hasattr(self, 'wj_workers'):
# # # #             for worker in self.wj_workers:
# # # #                 if worker.isRunning():
# # # #                     worker.stop()

# # # #         # Close all child windows
# # # #         if hasattr(self, 'scope_window') and self.scope_window:
# # # #             self.scope_window.close()

# # # #         if hasattr(self, 'sf6_window') and self.sf6_window:
# # # #             self.sf6_window.close()

# # # #         # Close data logger
# # # #         if hasattr(self, 'data_logger') and self.data_logger:
# # # #             self.data_logger.close()

# # # #         # Accept the close event
# # # #         event.accept()


# gui/main_window.py
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QMessageBox, QPushButton, QSizePolicy, QGridLayout,
)
from PyQt6.QtCore import QThread, Qt

import time

from gui.dg535_panel import DG535Panel
from gui.bnc575_panel import BNC575Panel
from gui.rigol_panel import RigolPanel
from gui.sf6_window import SF6Window
from gui.wj_panel import WJPanel
from gui.scope_plot_window import ScopePlotWindow
from gui.wj_plot_window import WJPlotWindow

from utils.logger import LogPanel
from utils.status_lamp import StatusLamp
from utils.serial_tools import list_serial_ports
from utils.capture_single_worker import CaptureSingleWorker
from utils.connect_memory import load_memory, save_memory
from utils.arduino_stream_worker import ArduinoStreamWorker
from utils.data_logger import DataLogger

from instruments.dg535 import DG535Controller
from instruments.bnc575 import BNC575Controller, SystemMode, TriggerMode, TriggerEdge
from instruments.rigol import RigolScope
from instruments.arduino import ArduinoController
from instruments.wj import WJPowerSupply


class ScopeDelayMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Scope + Delay + SF6 Control")
        self.setGeometry(100, 100, 1700, 900)
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

        self.wj_panel.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed
        )

        self.arduino = ArduinoController()
        
        self.rigol1_connected = False
        self.rigol2_connected = False
        self.rigol3_connected = False

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout()
        central.setLayout(main_layout)

        # Remove tabs - just use main layout for Scope + Delay controls
        self.build_scope_controls(main_layout)
        self.refresh_wj_ports()

        # Create SF6 window as separate top-level window (now includes WJ plots)
        self.sf6_window = SF6Window()

        # Attempt auto-connect
        self.auto_connect_all()
        # Populate COM list initially
        self.refresh_arduino_ports()

        # Connect SF6 window controls
        self.connect_sf6_window()

        # Create scope plot window
        self.scope_window = ScopePlotWindow(parent=self)

        # Start WJ reader threads and connect to SF6 window plot
        self.start_wj_readers()

        # Position and show all windows on startup
        self.position_and_show_windows()

        # Log the data file location
        self.log(f"[DATA LOGGER] Saving to: {self.data_logger.get_log_file_path()}")

        # Write a test log entry to verify logging is working
        self.data_logger.log_info("SYSTEM", "GUI started successfully")

        
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
        self.wj_max_points = 500

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
                elif unit_index == 1:
                    self.sf6_window.kv2_gauge.update_value(kv)
                    self.sf6_window.ma2_gauge.update_value(ma)
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

            # Rolling window for unit 1
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

            # Rolling window for unit 2
            if len(self.wj_t2_buf) > self.wj_max_points:
                self.wj_t2_buf = self.wj_t2_buf[-self.wj_max_points:]
                self.wj_kv2_buf = self.wj_kv2_buf[-self.wj_max_points:]
                self.wj_ma2_buf = self.wj_ma2_buf[-self.wj_max_points:]

            # Update curves for unit 2
            self.sf6_window.kv2_curve.setData(self.wj_t2_buf, self.wj_kv2_buf)
            self.sf6_window.ma2_curve.setData(self.wj_t2_buf, self.wj_ma2_buf)

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
        mid_geo = middle_screen.geometry()
        self.move(mid_geo.x() + 50, mid_geo.y() + 50)

        # SF6 window on left screen
        self.sf6_window.setScreen(left_screen)
        self.sf6_window.move(left_screen.geometry().topLeft())
        self.sf6_window.showMaximized()

        # Scope window on right screen
        self.scope_window.setScreen(right_screen)
        self.scope_window.move(right_screen.geometry().topLeft())
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

        # --------------------------------
        # GRID LAYOUT (2x2)
        # --------------------------------
        grid = QGridLayout()
        grid.addWidget(self.dg_panel, 0, 0)
        grid.addWidget(self.bnc_panel, 0, 1)
        grid.addWidget(self.rigol_panel, 1, 0)
        grid.addWidget(self.wj_panel, 1, 1)

        # --------------------------------
        # Left column containing grid + status + logs + button
        # --------------------------------
        left_column = QVBoxLayout()
        left_column.addLayout(grid)

        self.status_lamp = StatusLamp()
        self.log_panel = LogPanel()

        left_column.addWidget(self.status_lamp)
        left_column.addWidget(self.log_panel)

        self.btn_open_scope = QPushButton("Open Scope Display Window")
        left_column.addWidget(self.btn_open_scope)
        self.btn_open_scope.clicked.connect(self.on_open_scope_window)

        left_column.addStretch()

        layout.addLayout(left_column, 1)

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
        self.wj_panel.btn_set_v.clicked.connect(self.on_wj_set_voltage)
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

        # ------------------------------
        # DG535
        # ------------------------------
        try:
            port = self.conn.get("DG535_COM", "COM4")
            self.dg.connect(port=port, gpib_addr=15)
            save_memory("DG535_COM", port)
            self.log(f"[DG535] Connected on {port}")
            self.dg_panel.lamp.set_status("green", "Connected")
        except Exception as e:
            self.log(f"[DG535] NOT CONNECTED: {e}")
            self.dg_panel.lamp.set_status("red", "Not Connected")

        # ------------------------------
        # BNC575
        # ------------------------------
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
        # Arduino / SF6
        # ------------------------------
        try:
            port = self.conn.get("Arduino_COM", "COM8")
            self.arduino.connect(port)
            save_memory("Arduino_COM", port)
            self.log(f"[Arduino] Connected on {port}")
            self.sf6_window.sf6_panel.lamp.set_status("green", "Connected")

            # Start Arduino stream worker for continuous data reading
            self.arduino_stream = ArduinoStreamWorker(self.arduino)
            self.arduino_stream.data_signal.connect(self.on_analog_data)
            self.arduino_stream.error_signal.connect(lambda msg: self.log(f"[Arduino Stream ERROR] {msg}"))
            self.arduino_stream.start()
            self.log("[Arduino] Stream worker started")

        except Exception as e:
            self.log(f"[Arduino] NOT CONNECTED: {e}")
            self.sf6_window.sf6_panel.lamp.set_status("red", "Not Connected")

        # ------------------------------
        # WJ HIGH VOLTAGE SUPPLIES
        # ------------------------------
        default_wj_ports = ["COM6", "COM11"]
        for i, wj in enumerate(self.wj_units):
            try:
                port = self.conn.get(f"WJ{i+1}_COM", default_wj_ports[i])
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
        sf6_panel = self.sf6_window.sf6_panel

        # connect Arduino + switches
        sf6_panel.btn_connect.clicked.connect(self.on_arduino_connect)
        sf6_panel.btn_disconnect.clicked.connect(self.on_arduino_disconnect)

        sf6_output_map = {
            0: 0, 1: 4, 2: 1, 3: 5, 4: 2, 5: 6, 6: 3, 7: 7,
        }

        for gui_i, sw in enumerate(sf6_panel.switches):
            physical_do = sf6_output_map[gui_i]
            sw.stateChanged.connect(lambda on, do=physical_do:
                        self.on_sf6_switch_changed(do, 1 if on else 0))

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

        # If Arduino connected during auto-connect:
        if hasattr(self.arduino, "serial") and self.arduino.serial:
            sf6_panel.lamp.set_status("green", "Connected")
        else:
            sf6_panel.lamp.set_status("red", "Not Connected")


    def on_export_csv(self):
        import csv
        from datetime import datetime

        def export_scope_csv(scope, prefix):
            """Export current waveform data from scope to CSV."""
            (t1, v1), (t2, v2) = scope.capture_two_channels()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{prefix}_{timestamp}.csv"

            with open(filename, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["time_s", "ch1_v", "ch2_v"])
                for i in range(len(t1)):
                    writer.writerow([t1[i], v1[i], v2[i] if i < len(v2) else ""])
            return filename

        try:
            saved_files = []

            if self.rigol1_connected:
                f = export_scope_csv(self.rigol1, "rigol1")
                saved_files.append(f)

            if self.rigol2_connected:
                f = export_scope_csv(self.rigol2, "rigol2")
                saved_files.append(f)

            if self.rigol3_connected:
                f = export_scope_csv(self.rigol3, "rigol3")
                saved_files.append(f)

            if not saved_files:
                self.error_popup("No Data", "No scopes are connected.")
                return

            msg = "Saved:\n" + "\n".join(saved_files)
            self.log(msg)
            self.set_status("green", "Waveforms exported")

        except Exception as e:
            self.error_popup("CSV Export Error", str(e))
            self.log(f"[CSV ERROR] {e}")


    # ------------------------------------------------------------------
    #  Helpers
    # ------------------------------------------------------------------
    def log(self, msg: str):
        self.log_panel.log(msg)

    def set_status(self, color: str, text: str):
        self.status_lamp.set_status(color, text)

    def error_popup(self, title: str, text: str):
        QMessageBox.critical(self, title, text)

    def refresh_arduino_ports(self):
        ports = list_serial_ports()
        sf6_panel = self.sf6_window.sf6_panel
        sf6_panel.port_list.clear()
        if not ports:
            sf6_panel.port_list.addItem("No COM ports")
        else:
            sf6_panel.port_list.addItems(ports)


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
        except Exception as e:
            self.set_status("red", "DG535 connection failed")
            self.log(f"[DG535 ERROR] {e}")
            self.error_popup("DG535 Error", str(e))

    def on_dg_fire(self):
        try:
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

    def _capture_single_scope(self, rigol, plot_widget, name):
        try:
            plot_widget.clear()

            self.set_status("yellow", f"Capturing {name}...")
            self.log(f"[{name}] Preparing for capture...")

            rigol.stop()
            rigol.single()
            time.sleep(0.2)

            (t1, v1), (t2, v2) = rigol.wait_and_capture()

            plot_widget.plot(t1, v1, pen="r")
            plot_widget.plot(t2, v2, pen="b")

            self.set_status("green", f"{name} captured")
            self.log(f"[{name}] Capture complete.")

        except Exception as e:
            self.error_popup(f"{name} Capture Error", str(e))
            self.log(f"[{name} ERROR] {e}")


    def on_capture_r1(self):
        if not self.rigol1_connected:
            self.error_popup("Rigol #1", "Not connected.")
            return
        self.start_single_capture(self.rigol1, self.scope_window.plot1, "Rigol #1")


    def on_capture_r2(self):
        if not self.rigol2_connected:
            self.error_popup("Rigol #2", "Not connected.")
            return
        self.start_single_capture(self.rigol2, self.scope_window.plot2, "Rigol #2")


    def on_capture_r3(self):
        if not self.rigol3_connected:
            self.error_popup("Rigol #3", "Not connected.")
            return
        self.start_single_capture(self.rigol3, self.scope_window.plot3, "Rigol #3")

    def start_single_capture(self, rigol, plot_widget, name):
        self.set_status("yellow", f"Capturing {name}...")
        self.log(f"[{name}] capture started...")

        # The new CaptureSingleWorker handles arming internally via wait_and_capture
        self.single_worker = CaptureSingleWorker(rigol, name, timeout=300.0)
        self.single_worker.finished.connect(lambda ch1, ch2, nm: self.on_single_capture_finished(ch1, ch2, plot_widget, nm))
        self.single_worker.error.connect(lambda msg, nm: self.on_single_capture_error(msg, nm))
        self.single_worker.start()

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


    def on_single_capture_finished(self, ch1, ch2, plot_widget, name):
        (t1, v1) = ch1
        (t2, v2) = ch2

        # Log scope capture
        scope_id = 0
        if plot_widget == self.scope_window.plot1:
            self.scope_window.update_r1(t1, v1, t2, v2)
            scope_id = 1
        elif plot_widget == self.scope_window.plot2:
            self.scope_window.update_r2(t1, v1, t2, v2)
            scope_id = 2
        elif plot_widget == self.scope_window.plot3:
            self.scope_window.update_r3(t1, v1, t2, v2)
            scope_id = 3

        self.data_logger.log_scope_capture(scope_id, len(t1), len(t2))

        self.set_status("green", f"{name} captured")
        self.log(f"[{name}] capture complete.")

    def on_single_capture_error(self, msg, name):
        self.set_status("red", f"{name} error")
        self.error_popup(f"{name} Capture Error", msg)
        self.log(f"[{name} ERROR] {msg}")


    def on_capture_all_scopes(self):
        self.set_status("yellow", "Preparing for capture...")
        self.log("[CAPTURE] Starting threaded capture...")

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

        # 5. CAPTURE waveforms
        self.set_status("yellow", "Capturing waveforms...")

        if self.rigol1_connected:
            (t1, v1), (t2, v2) = self.rigol1.wait_and_capture()
            self.scope_window.update_r1(t1, v1, t2, v2)
            self.data_logger.log_scope_capture(1, len(t1), len(t2))

        if self.rigol2_connected:
            (t1, v1), (t2, v2) = self.rigol2.wait_and_capture()
            self.scope_window.update_r2(t1, v1, t2, v2)
            self.data_logger.log_scope_capture(2, len(t1), len(t2))

        if self.rigol3_connected:
            (t1, v1), (t2, v2) = self.rigol3.wait_and_capture()
            self.scope_window.update_r3(t1, v1, t2, v2)
            self.data_logger.log_scope_capture(3, len(t1), len(t2))

        self.data_logger.log_scope_all_capture()

        self.set_status("green", "Capture complete")
        self.log("[CAPTURE] Done.")


    def _capture_error(self, msg):
        self.set_status("red", "Capture error")
        self.log(f"[CAPTURE ERROR] {msg}")
        self.error_popup("Capture Error", msg)

    def _capture_log(self, msg):
        self.log("[CAPTURE] " + msg)
        self.set_status("yellow", msg)

    def _plot_capture(self, index, data):
        (t1, v1), (t2, v2) = data

        if index == 0:
            p = self.scope_window.plot1
        elif index == 1:
            p = self.scope_window.plot2
        else:
            p = self.scope_window.plot3

        if index == 0:
            self.scope_window.update_r1(t1, v1, t2, v2)
        elif index == 1:
            self.scope_window.update_r2(t1, v1, t2, v2)
        elif index == 2:
            self.scope_window.update_r3(t1, v1, t2, v2)


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
    #  Arduino / SF6 Handlers
    # ------------------------------------------------------------------
    def on_arduino_connect(self):
        sf6_panel = self.sf6_window.sf6_panel
        port = sf6_panel.port_list.currentText()
        if port == "No COM ports":
            self.error_popup("Arduino", "No COM ports found.")
            return
        try:
            if hasattr(self, "arduino_stream") and self.arduino_stream:
                self.arduino_stream.stop()
                self.arduino_stream = None
            self.set_status("yellow", f"Connecting Arduino on {port}...")
            self.arduino.connect(port)
            save_memory("Arduino_COM", port)

            self.set_status("green", "Arduino connected")
            self.log(f"[Arduino] Connected on {port}")
            sf6_panel.lamp.set_status("green", "Connected")

            self.arduino_stream = ArduinoStreamWorker(self.arduino)
            self.arduino_stream.data_signal.connect(self.on_analog_data)
            self.arduino_stream.error_signal.connect(lambda msg: self.log(f"[Arduino Stream ERROR] {msg}"))
            self.arduino_stream.start()

            # Auto-close Marx1 Supply (DO0) and Marx1 Return (DO4) on connect
            try:
                self.arduino.set_digital_output(0, 1)  # Marx1 Supply ON (closed)
                self.arduino.set_digital_output(4, 1)  # Marx1 Return ON (closed)
                sf6_panel.switches[0].setChecked(True)  # Update GUI switch
                sf6_panel.switches[1].setChecked(True)  # Update GUI switch
                self.log("[Arduino] Auto-closed Marx1 Supply and Marx1 Return")
            except Exception as e:
                self.log(f"[Arduino] Failed to auto-close Marx1 valves: {e}")

        except Exception as e:
            self.set_status("red", "Arduino connection failed")
            self.log(f"[Arduino ERROR] {e}")
            sf6_panel.lamp.set_status("red", "Error")
            self.error_popup("Arduino Error", str(e))

    def on_analog_data(self, ch0, ch1, ch2):
        def mA_to_psi(mA):
            if mA < 4:
                return 0
            if mA > 20:
                return 200
            return (mA - 4.0) * 12.5

        psi0 = mA_to_psi(ch0)
        psi1 = mA_to_psi(ch1)
        psi2 = mA_to_psi(ch2)

        try:
            self.data_logger.log_arduino_psi(psi0, psi1, psi2)
        except Exception as e:
            self.log(f"[DataLogger ERROR] Failed to log Arduino data: {e}")

        sf6_panel = self.sf6_window.sf6_panel
        sf6_panel.ai_ch0.update_value(psi0)
        sf6_panel.ai_ch1.update_value(psi1)
        sf6_panel.ai_ch2.update_value(psi2)


    def on_sf6_switch_changed(self, index: int, state: int):
        try:
            if state:
                cmd = f"on {index}"
            else:
                cmd = f"off {index}"
            self.arduino.send(cmd)
            self.data_logger.log_arduino_switch(index, state)
            self.log(f"[Arduino] {cmd}")
        except Exception as e:
            self.log(f"[Arduino ERROR] {e}")
            self.data_logger.log_error("Arduino", str(e))
            self.error_popup("Arduino Send Error", str(e))


    # ------------------------------------------------------------------
    #  WJ HV POWER SUPPLY HANDLERS
    # ------------------------------------------------------------------
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


    def on_arduino_disconnect(self):
        try:
            if hasattr(self, "arduino_stream"):
                self.arduino_stream.stop()
                self.arduino_stream = None
            self.arduino.close()
        except:
            pass

        sf6_panel = self.sf6_window.sf6_panel
        sf6_panel.lamp.set_status("red", "Disconnected")
        self.log("[Arduino] Disconnected")


    def on_wj_hv_on(self):
        for i, wj in enumerate(self.wj_units):
            try:
                resp = wj.hv_on_pulse()
                self.data_logger.log_wj_command(i+1, "HV_ON")
                self.log(f"[WJ{i+1}] HV ON → {resp}")
            except Exception as e:
                self.log(f"[WJ{i+1} ERROR] {e}")
                self.data_logger.log_error(f"WJ{i+1}", str(e))

    def on_wj_hv_off(self):
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
        if ma is None:
            ma = self.wj_panel.current.value()

        for i, wj in enumerate(self.wj_units):
            try:
                resp = wj.set_program(kv, ma)
                self.data_logger.log_wj_command(i+1, "SET_PROGRAM", f"{kv}kV_{ma}mA")
                self.log(f"[WJ{i+1}] Set → {kv} kV, {ma} mA ({resp})")
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
        for i, wj in enumerate(self.wj_units):
            try:
                data = wj.query()
                self.log(f"[WJ{i+1}] Readback: {data}")

                row = self.wj_panel.rows[i]

                if data.get("type") != "R":
                    row.label_status.setText("No R packet")
                    continue

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


    def on_open_scope_window(self):
        self.scope_window.show()
        self.scope_window.raise_()
        self.scope_window.activateWindow()

    def closeEvent(self, event):
        if hasattr(self, 'wj_workers'):
            for worker in self.wj_workers:
                if worker.isRunning():
                    worker.stop()

        if hasattr(self, 'scope_window') and self.scope_window:
            self.scope_window.close()

        if hasattr(self, 'sf6_window') and self.sf6_window:
            self.sf6_window.close()

        if hasattr(self, 'data_logger') and self.data_logger:
            self.data_logger.close()

        event.accept()
