# from PyQt6.QtWidgets import QWidget, QVBoxLayout
# from PyQt6.QtCore import QTimer
# import pyqtgraph as pg


# class WJPlotWindow(QWidget):
#     def __init__(self, wj_driver):
#         super().__init__()
#         self.setWindowTitle("WJ HV Supply – Live V/I Plot")
#         self.resize(700, 400)

#         self.wj = wj_driver
#         self.t = 0
#         self.history_t = []
#         self.history_v = []
#         self.history_i = []

#         layout = QVBoxLayout()
#         self.setLayout(layout)

#         # Voltage plot
#         self.plot_v = pg.PlotWidget()
#         self.plot_v.setLabel("left", "Voltage", units="kV")
#         self.plot_v.setLabel("bottom", "Time", units="s")
#         self.curve_v = self.plot_v.plot([], [], pen=pg.mkPen("y", width=2))
#         layout.addWidget(self.plot_v)

#         # Current plot
#         self.plot_i = pg.PlotWidget()
#         self.plot_i.setLabel("left", "Current", units="mA")
#         self.plot_i.setLabel("bottom", "Time", units="s")
#         self.curve_i = self.plot_i.plot([], [], pen=pg.mkPen("c", width=2))
#         layout.addWidget(self.plot_i)

#         # Timer (10 Hz)
#         self.timer = QTimer()
#         self.timer.timeout.connect(self.update_data)
#         self.timer.start(100)

#     def update_data(self):
#         data = self.wj.query()
#         if data.get("type") != "R":
#             return

#         kv = data["kv"]
#         ma = data["ma"]

#         self.t += 0.1
#         self.history_t.append(self.t)
#         self.history_v.append(kv)
#         self.history_i.append(ma)

#         # Keep last ~60 seconds
#         if len(self.history_t) > 600:
#             self.history_t = self.history_t[-600:]
#             self.history_v = self.history_v[-600:]
#             self.history_i = self.history_i[-600:]

#         self.curve_v.setData(self.history_t, self.history_v)
#         self.curve_i.setData(self.history_t, self.history_i)
# from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton
# from PyQt6.QtCore import QThread, pyqtSignal, QObject, QTimer
# import pyqtgraph as pg
# import time


# # ----------------------------------------------------------------------
# # Worker thread: polls WJ without blocking GUI
# # ----------------------------------------------------------------------
# class WJReaderThread(QThread):
#     new_data = pyqtSignal(float, float, float)   # time, kV, mA

#     def __init__(self, wj, poll_interval=0.2):
#         super().__init__()
#         self.wj = wj
#         self.poll_interval = poll_interval
#         self.running = True
#         self.t0 = time.time()

#     def run(self):
#         while self.running:
#             try:
#                 data = self.wj.query()
#                 if data.get("type") == "R":
#                     kv = data["kv"]
#                     ma = data["ma"]
#                     t = time.time() - self.t0
#                     self.new_data.emit(t, kv, ma)
#             except Exception:
#                 pass
#             self.msleep(int(self.poll_interval * 1000))

#     def stop(self):
#         self.running = False
#         self.wait()


# # ----------------------------------------------------------------------
# # WJPlotWindow - fast rolling plot with no GUI lag
# # ----------------------------------------------------------------------
# class WJPlotWindow(QWidget):
#     def __init__(self, wj):
#         super().__init__()
#         self.setWindowTitle("WJ Live Voltage / Current Monitor")
#         self.resize(800, 500)

#         layout = QVBoxLayout()
#         self.setLayout(layout)

#         # Pyqtgraph plot
#         self.plot_widget = pg.PlotWidget()
#         layout.addWidget(self.plot_widget)

#         self.plot_widget.showGrid(x=True, y=True)

#         self.plot_widget.addLegend()

#         self.kv_curve = self.plot_widget.plot(
#             pen=pg.mkPen('y', width=2),
#             name="kV"
#         )

#         self.ma_curve = self.plot_widget.plot(
#             pen=pg.mkPen('c', width=2),
#             name="mA"
# )


#         # Rolling buffers
#         self.max_points = 500
#         self.time_buffer = []
#         self.kv_buffer = []
#         self.ma_buffer = []

#         # Start polling thread
#         self.worker = WJReaderThread(wj)
#         self.worker.new_data.connect(self.update_plot_fast)
#         self.worker.start()

#         # Close handler
#         self.destroyed.connect(self.on_close)

#     # ------------------------------------------------------------------
#     # Fastest possible plot update (no GUI freeze)
#     # ------------------------------------------------------------------
#     def update_plot_fast(self, t, kv, ma):

#         self.time_buffer.append(t)
#         self.kv_buffer.append(kv)
#         self.ma_buffer.append(ma)

#         # rolling window
#         if len(self.time_buffer) > self.max_points:
#             self.time_buffer = self.time_buffer[-self.max_points:]
#             self.kv_buffer = self.kv_buffer[-self.max_points:]
#             self.ma_buffer = self.ma_buffer[-self.max_points:]

#         # Efficient redraw
#         self.kv_curve.setData(self.time_buffer, self.kv_buffer)
#         self.ma_curve.setData(self.time_buffer, self.ma_buffer)

#     # ------------------------------------------------------------------
#     # Stop thread on close
#     # ------------------------------------------------------------------
#     def on_close(self, *_):
#         if self.worker.isRunning():
#             self.worker.stop()
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QFont
import pyqtgraph as pg
import time
import csv
from datetime import datetime



# from PyQt6.QtCore import QThread, pyqtSignal
# import time

class WJReaderThread(QThread):
    new_data = pyqtSignal(float, float, float)   # time, kV, mA

    def __init__(self, wj, poll_interval=0.05):
        super().__init__()
        self.wj = wj
        self.poll_interval = poll_interval
        self.running = True
        self.t0 = time.time()

    def run(self):
        while self.running:
            try:
                data = self.wj.query()
                if data.get("type") == "R":
                    kv = data["kv"]
                    ma = data["ma"]
                    t = time.time() - self.t0
                    self.new_data.emit(t, kv, ma)
            except Exception:
                pass

            self.msleep(int(self.poll_interval * 1000))

    def stop(self):
        self.running = False
        self.wait()

class WJPlotWindow(QWidget):
    def __init__(self, wj_units, data_logger=None):
        """
        wj_units = [WJ1, WJ2]
        data_logger = DataLogger instance (optional)
        """
        super().__init__()
        self.setWindowTitle("WJ Live Voltage / Current Monitor (Both Units)")
        self.resize(900, 550)

        self.wj_units = wj_units   # list of WJPowerSupply objects
        self.data_logger = data_logger  # Optional data logger

        layout = QVBoxLayout()
        self.setLayout(layout)

        self.log_data = []   # List of tuples: (timestamp, wj_index, kv, ma)
        # Export button
        self.btn_export = QPushButton("Export CSV Log")
        layout.addWidget(self.btn_export)
        self.btn_export.clicked.connect(self.export_csv)
        # ─────────────────────────────────────────────
        # PLOT SETUP
        # ─────────────────────────────────────────────
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('w')   # ← WHITE BACKGROUND
        self.plot_widget.getPlotItem().setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self.plot_widget)
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_widget.addLegend()
        

        # 4 curves: WJ1 kV, WJ1 mA, WJ2 kV, WJ2 mA
        self.kv1_curve = self.plot_widget.plot(pen=pg.mkPen('y', width=2), name="WJ1 kV")
        self.ma1_curve = self.plot_widget.plot(pen=pg.mkPen('c', width=2), name="WJ1 mA")
        self.kv2_curve = self.plot_widget.plot(pen=pg.mkPen('r', width=2), name="WJ2 kV")
        self.ma2_curve = self.plot_widget.plot(pen=pg.mkPen('m', width=2), name="WJ2 mA")

        # Apply Times New Roman bold font
        self._apply_font_styling()

        # Buffers for rolling window
        self.max_points = 500
        self.t_buf = []

        self.kv1_buf = []
        self.ma1_buf = []
        self.kv2_buf = []
        self.ma2_buf = []

        # ─────────────────────────────────────────────
        # START WORKER THREADS FOR EACH WJ UNIT
        # ─────────────────────────────────────────────
        self.workers = []
        self.start_time = time.time()

        for idx, wj in enumerate(self.wj_units):
            worker = WJReaderThread(wj)
            worker.new_data.connect(lambda t, kv, ma, i=idx: self.handle_unit_data(i, t, kv, ma))
            worker.start()
            self.workers.append(worker)

        # Stop threads on close
        self.destroyed.connect(self.on_close)

    def _apply_font_styling(self):
        """Apply Times New Roman bold font to plot axes and labels"""
        font = QFont("Times New Roman", 12)
        font.setBold(True)

        # Apply font to axes
        self.plot_widget.getAxis('left').setStyle(tickFont=font)
        self.plot_widget.getAxis('bottom').setStyle(tickFont=font)

        # Apply font to axis labels
        self.plot_widget.setLabel('left', 'Voltage (kV) / Current (mA)', **{'font-size': '12pt', 'font-family': 'Times New Roman', 'font-weight': 'bold'})
        self.plot_widget.setLabel('bottom', 'Time (s)', **{'font-size': '12pt', 'font-family': 'Times New Roman', 'font-weight': 'bold'})

    # ---------------------------------------------------------
    # Incoming data handler for each unit
    # ---------------------------------------------------------
    def handle_unit_data(self, unit_index, t, kv, ma):

        # Normalize time to shared reference
        t = time.time() - self.start_time
        self.log_data.append((t, unit_index, kv, ma))

        # Log to main data logger if available
        if self.data_logger:
            # Note: we don't have HV status here, so we pass False
            # The main window's on_wj_read will log full status
            pass  # Already logged by main window's on_wj_read

        self.t_buf.append(t)

        # Unit 1
        if unit_index == 0:
            self.kv1_buf.append(kv)
            self.ma1_buf.append(ma)

        # Unit 2
        elif unit_index == 1:
            self.kv2_buf.append(kv)
            self.ma2_buf.append(ma)

        # Rolling window
        if len(self.t_buf) > self.max_points:
            self.t_buf = self.t_buf[-self.max_points:]
            self.kv1_buf = self.kv1_buf[-self.max_points:]
            self.ma1_buf = self.ma1_buf[-self.max_points:]
            self.kv2_buf = self.kv2_buf[-self.max_points:]
            self.ma2_buf = self.ma2_buf[-self.max_points:]

        # Update curves
        self.kv1_curve.setData(self.t_buf, self.kv1_buf)
        self.ma1_curve.setData(self.t_buf, self.ma1_buf)
        self.kv2_curve.setData(self.t_buf, self.kv2_buf)
        self.ma2_curve.setData(self.t_buf, self.ma2_buf)

    def export_csv(self):
        """Save time-stamped data for ALL WJ units into a CSV file."""
        if not self.log_data:
            print("No data to export.")
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"WJ_log_{ts}.csv"

        with open(filename, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp_sec", "wj_index", "kV", "mA"])

            for entry in self.log_data:
                writer.writerow(entry)

        print(f"Saved CSV log: {filename}")
    # ---------------------------------------------------------
    # Cleanup
    # ---------------------------------------------------------
    def on_close(self):
        for w in self.workers:
            if w.isRunning():
                w.stop()
