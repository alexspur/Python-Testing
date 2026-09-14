from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QDoubleSpinBox,
)
from PyQt6.QtCore import Qt
from gui.gauge_widget import GaugeWidget
from utils.status_lamp import StatusLamp


class SF6Panel(QGroupBox):
    """SF6 dome pressure monitor, read from the Opta over Modbus TCP.

    Display only. main_window owns the PressureWorker thread, pushes results
    in through set_link_state / show_snapshot / show_calibration, and wires
    btn_connect, btn_disconnect, btn_set_full_scale and btn_zero_here.
    """

    _LINK_STATES = {
        # state: (lamp color, lamp text, connect button text)
        "down":       ("gray",   "Not connected", "Connect"),
        "connecting": ("yellow", "Connecting...", "Connect"),
        "up":         ("green",  "Connected",     "Reconnect"),
        "lost":       ("red",    "LINK LOST",     "Reconnect"),
    }
    _PSI_STYLE = "font-size:28px; font-weight:bold; color:black;"
    _PSI_FAULT_STYLE = "font-size:28px; font-weight:bold; color:#C62828;"
    _BANNER_STYLE = ("background-color:#C62828; color:white; font-weight:bold;"
                     " padding:6px; border-radius:4px;")
    _RECONNECT_STYLE = "background-color:#FB8C00; color:white; font-weight:bold;"

    def __init__(self, pressure_min=0, pressure_max=100):
        super().__init__("SF6 Dome Pressure")

        layout = QVBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setLayout(layout)

        # ─────────────────────────────────────────────
        # LINK
        # ─────────────────────────────────────────────
        link_row = QHBoxLayout()
        self.lbl_host = QLabel("Opta:")
        link_row.addWidget(self.lbl_host)
        self.lamp = StatusLamp(size=14)
        link_row.addWidget(self.lamp)
        self.btn_connect = QPushButton("Connect")
        link_row.addWidget(self.btn_connect)
        self.btn_disconnect = QPushButton("Disconnect")
        link_row.addWidget(self.btn_disconnect)
        link_row.addStretch()
        layout.addLayout(link_row)

        # ─────────────────────────────────────────────
        # READOUT
        # ─────────────────────────────────────────────
        # Gauge range is configurable from main.py
        # (PRESSURE_GAUGE_MIN_PSI / PRESSURE_GAUGE_MAX_PSI).
        readout = QHBoxLayout()
        readout.setSpacing(12)
        self.gauge = GaugeWidget(min_value=pressure_min, max_value=pressure_max, label="PSI", size=120)
        readout.addWidget(self.gauge)

        values = QVBoxLayout()
        self.lbl_psi = QLabel()
        values.addWidget(self.lbl_psi)
        self.lbl_detail = QLabel()
        values.addWidget(self.lbl_detail)
        values.addStretch()
        readout.addLayout(values)
        readout.addStretch()
        layout.addLayout(readout)

        # Sensor fault or lost link. Hidden while the reading is good.
        self.lbl_banner = QLabel()
        self.lbl_banner.setWordWrap(True)
        self.lbl_banner.setStyleSheet(self._BANNER_STYLE)
        self.lbl_banner.hide()
        layout.addWidget(self.lbl_banner)

        # ─────────────────────────────────────────────
        # CALIBRATION (holding registers, applied live)
        # ─────────────────────────────────────────────
        cal = QGroupBox("Calibration (live on the Opta, no reflash)")
        cal_grid = QGridLayout()
        cal.setLayout(cal_grid)

        cal_grid.addWidget(QLabel("Loaded full scale:"), 0, 0)
        self.lbl_cal_full_scale = QLabel("---")
        cal_grid.addWidget(self.lbl_cal_full_scale, 0, 1)
        cal_grid.addWidget(QLabel("Zero offset:"), 0, 2)
        self.lbl_cal_zero = QLabel("---")
        cal_grid.addWidget(self.lbl_cal_zero, 0, 3)
        cal_grid.addWidget(QLabel("Averaging:"), 0, 4)
        self.lbl_cal_avg = QLabel("---")
        cal_grid.addWidget(self.lbl_cal_avg, 0, 5)

        cal_grid.addWidget(QLabel("Full scale @ 10 V (psi):"), 1, 0)
        self.spin_full_scale = QDoubleSpinBox()
        self.spin_full_scale.setDecimals(1)
        self.spin_full_scale.setRange(0.1, 6553.5)   # holding register is psi x10
        self.spin_full_scale.setSingleStep(0.1)
        self.spin_full_scale.setValue(159.4)
        cal_grid.addWidget(self.spin_full_scale, 1, 1)
        self.btn_set_full_scale = QPushButton("Set Full Scale")
        cal_grid.addWidget(self.btn_set_full_scale, 1, 2)
        self.btn_zero_here = QPushButton("Zero Here")
        self.btn_zero_here.setToolTip("Take the present input as 0 psi. Vent the line first.")
        cal_grid.addWidget(self.btn_zero_here, 1, 3)

        note = QLabel("Held in Opta RAM only: resets to the firmware defaults "
                      "(159.4 psi, 0 mV) whenever the Opta reboots.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#666;")
        cal_grid.addWidget(note, 2, 0, 1, 6)
        layout.addWidget(cal)

        layout.addStretch(1)
        self.set_link_state("down")

    def set_host(self, where: str):
        self.lbl_host.setText(f"Opta {where}")

    def set_link_state(self, state: str, reason: str = ""):
        """state is one of down / connecting / up / lost."""
        color, lamp_text, connect_text = self._LINK_STATES[state]
        self.lamp.set_status(color, lamp_text)
        self.btn_connect.setText(connect_text)
        self.btn_connect.setEnabled(state != "connecting")
        self.btn_connect.setStyleSheet(self._RECONNECT_STYLE if state == "lost" else "")
        self.btn_disconnect.setEnabled(state == "up")
        self.btn_set_full_scale.setEnabled(state == "up")
        self.btn_zero_here.setEnabled(state == "up")

        if state != "up":
            self._clear_reading()
        if state == "lost":
            self._show_banner(
                f"LINK LOST: {reason}\nPressure is not being read. Check the "
                "fiber link and Opta power, then press Reconnect.")
        else:
            self.lbl_banner.hide()

    def show_snapshot(self, d: dict):
        self.lbl_detail.setText(
            f"I1: {d['volts']:.3f} V | counts: {d['counts']} | uptime: {d['uptime_s']} s")

        if d["under_range"] or d["over_range"]:
            # Never show a number for a dead or over-range sensor.
            self.gauge.show_text("FAULT")
            self.lbl_psi.setText("SENSOR FAULT")
            self.lbl_psi.setStyleSheet(self._PSI_FAULT_STYLE)
            if d["under_range"]:
                self._show_banner(
                    f"SENSOR FAULT: I1 below 100 mV ({d['volts']:.3f} V). Transducer "
                    "unpowered or signal wire off. Pressure reading is not valid.")
            else:
                self._show_banner(
                    f"SENSOR FAULT: I1 above 10.2 V ({d['volts']:.3f} V). Input over "
                    "range or miswired. Pressure reading is not valid.")
            return

        self.lbl_banner.hide()
        self.gauge.update_value(d["psi"])
        self.lbl_psi.setText(f"{d['psi']:.2f} psi")
        self.lbl_psi.setStyleSheet(self._PSI_STYLE)

    def show_calibration(self, cal: dict):
        self.lbl_cal_full_scale.setText(f"{cal['full_scale_psi']:.1f} psi")
        self.lbl_cal_zero.setText(f"{cal['zero_offset_mv']} mV")
        self.lbl_cal_avg.setText(f"{cal['avg_samples']} samples")
        self.spin_full_scale.setValue(cal["full_scale_psi"])

    def _clear_reading(self):
        self.gauge.show_text("---")
        self.lbl_psi.setText("--- psi")
        self.lbl_psi.setStyleSheet(self._PSI_STYLE)
        self.lbl_detail.setText("I1: --- V | counts: --- | uptime: --- s")

    def _show_banner(self, text: str):
        self.lbl_banner.setText(text)
        self.lbl_banner.show()
