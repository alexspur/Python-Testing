# gui/dg535_panel.py
"""
DG535 Control Panel GUI

Full-featured GUI panel for Stanford Research DG535 Digital Delay/Pulse Generator.
Provides access to all major device functions as available on the physical front panel.

BACKWARD COMPATIBLE: Maintains get_delayA(), get_widthA() etc. methods for existing code.

Layout notes:
- Each tab's content lives in a QScrollArea, so the panel can be short without
  the group boxes overlapping/squishing — content scrolls instead.
- Time/frequency units are compact QComboBox dropdowns (not rows of buttons),
  which keeps each row narrow and the panel short.
"""

from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton,
    QLabel, QDoubleSpinBox, QComboBox, QTabWidget, QWidget,
    QButtonGroup, QFormLayout, QSpinBox, QFrame, QScrollArea,
)
from PyQt6.QtCore import Qt
from utils.status_lamp import StatusLamp


# Unit -> multiplier (to seconds / to Hz)
_TIME_UNITS = [("s", 1.0), ("ms", 1e-3), ("μs", 1e-6), ("ns", 1e-9), ("ps", 1e-12)]
_FREQ_UNITS = [("Hz", 1.0), ("kHz", 1e3), ("MHz", 1e6)]


class DG535Panel(QGroupBox):
    """
    Complete control panel for DG535 Digital Delay Generator.

    Organized into tabs (each scrollable):
    - Trigger: Trigger mode and settings
    - Delays: Channel A, B, C, D delay/width settings
    - Outputs: Output configuration for each channel
    - Store/Recall: Save and load configurations
    """

    def __init__(self):
        super().__init__("DG535 Digital Delay Generator")

        layout = QVBoxLayout()
        self.setLayout(layout)

        # Connection status indicator
        status_row = QHBoxLayout()
        self.lamp = StatusLamp(size=14)
        status_row.addWidget(self.lamp)
        status_row.addStretch()
        layout.addLayout(status_row)

        # Connection buttons
        conn_row = QHBoxLayout()
        self.btn_connect = QPushButton("Connect DG535")
        self.btn_disconnect = QPushButton("Disconnect")
        self.btn_clear = QPushButton("Clear/Reset")
        conn_row.addWidget(self.btn_connect)
        conn_row.addWidget(self.btn_disconnect)
        conn_row.addWidget(self.btn_clear)
        layout.addLayout(conn_row)

        # Tab widget for organized controls
        self.tabs = QTabWidget()
        # Modest minimum so the tab area stays usable; overflow scrolls.
        self.tabs.setMinimumHeight(230)
        layout.addWidget(self.tabs)

        # Create individual tabs
        self._create_trigger_tab()
        self._create_delays_tab()
        self._create_outputs_tab()
        self._create_store_recall_tab()

        # Quick action buttons at bottom
        action_row = QHBoxLayout()
        self.btn_fire = QPushButton("🔥 Fire Single Shot")
        self.btn_fire.setStyleSheet("font-size: 14px; font-weight: bold; padding: 8px;")
        self.btn_apply_all = QPushButton("Apply All Settings")
        self.btn_read_all = QPushButton("Read All Settings")
        action_row.addWidget(self.btn_fire)
        action_row.addWidget(self.btn_apply_all)
        action_row.addWidget(self.btn_read_all)
        layout.addLayout(action_row)

        # Status readout
        self.status_label = QLabel("Status: Not connected")
        self.status_label.setStyleSheet("font-style: italic; color: #666;")
        layout.addWidget(self.status_label)

    # =========================================================================
    # Small builder helpers
    # =========================================================================
    def _add_scroll_tab(self, inner: QWidget, title: str):
        """Wrap a tab's content widget in a scroll area and add it as a tab."""
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        sa.setWidget(inner)
        self.tabs.addTab(sa, title)

    def _make_time_field(self, default_value=0.0, default_unit="μs"):
        """Return (spinbox, unit_combo) for a time value. Combo data = seconds multiplier."""
        spin = QDoubleSpinBox()
        spin.setDecimals(6)
        spin.setRange(0, 999999999)
        spin.setValue(default_value)
        spin.setMaximumWidth(120)

        combo = QComboBox()
        for name, mult in _TIME_UNITS:
            combo.addItem(name, mult)
        idx = combo.findText(default_unit)
        combo.setCurrentIndex(idx if idx >= 0 else 2)
        combo.setMaximumWidth(70)
        return spin, combo

    def _make_freq_field(self, default_value=10000.0, default_unit="Hz"):
        """Return (spinbox, unit_combo) for a frequency value. Combo data = Hz multiplier."""
        spin = QDoubleSpinBox()
        spin.setDecimals(3)
        spin.setRange(0, 999999999)
        spin.setValue(default_value)
        spin.setMaximumWidth(120)

        combo = QComboBox()
        for name, mult in _FREQ_UNITS:
            combo.addItem(name, mult)
        idx = combo.findText(default_unit)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.setMaximumWidth(70)
        return spin, combo

    @staticmethod
    def _value_in_seconds(spin: QDoubleSpinBox, combo: QComboBox) -> float:
        mult = combo.currentData()
        return spin.value() * (mult if mult is not None else 1e-6)

    @staticmethod
    def _value_in_hz(spin: QDoubleSpinBox, combo: QComboBox) -> float:
        mult = combo.currentData()
        return spin.value() * (mult if mult is not None else 1.0)

    # =========================================================================
    # Tabs
    # =========================================================================
    def _create_trigger_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()
        tab.setLayout(layout)

        # Trigger Mode Selection
        mode_group = QGroupBox("Trigger Mode")
        mode_layout = QHBoxLayout()
        mode_group.setLayout(mode_layout)

        self.trig_mode_group = QButtonGroup(self)
        self.trig_mode_group.setExclusive(True)

        modes = [("Internal", 0), ("External", 1), ("Single-Shot", 2),
                 ("Burst", 3), ("Line", 4)]
        self.trig_mode_buttons = {}

        for name, mode_id in modes:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton { padding: 6px 12px; }
                QPushButton:checked {
                    background-color: #2196F3;
                    color: white;
                    font-weight: bold;
                }
            """)
            self.trig_mode_group.addButton(btn, mode_id)
            self.trig_mode_buttons[mode_id] = btn
            mode_layout.addWidget(btn)

        self.trig_mode_buttons[2].setChecked(True)  # Default Single-Shot
        layout.addWidget(mode_group)

        # Internal Trigger Settings
        internal_group = QGroupBox("Internal Trigger")
        internal_layout = QFormLayout()
        internal_group.setLayout(internal_layout)

        self.internal_rate, self.internal_rate_combo = self._make_freq_field(10000.0, "Hz")
        rate_row = QHBoxLayout()
        rate_row.addWidget(self.internal_rate)
        rate_row.addWidget(self.internal_rate_combo)
        rate_row.addStretch()
        internal_layout.addRow("Rate:", rate_row)
        layout.addWidget(internal_group)

        # External Trigger Settings
        external_group = QGroupBox("External Trigger")
        external_layout = QFormLayout()
        external_group.setLayout(external_layout)

        self.ext_threshold = QDoubleSpinBox()
        self.ext_threshold.setRange(-2.56, 2.56)
        self.ext_threshold.setDecimals(2)
        self.ext_threshold.setValue(1.0)
        self.ext_threshold.setSuffix(" V")
        external_layout.addRow("Threshold:", self.ext_threshold)

        self.ext_slope = QComboBox()
        self.ext_slope.addItems(["Rising Edge", "Falling Edge"])
        external_layout.addRow("Slope:", self.ext_slope)

        self.ext_impedance = QComboBox()
        self.ext_impedance.addItems(["High-Z (1MΩ)", "50Ω"])
        external_layout.addRow("Impedance:", self.ext_impedance)
        layout.addWidget(external_group)

        # Burst Settings
        burst_group = QGroupBox("Burst Mode")
        burst_layout = QFormLayout()
        burst_group.setLayout(burst_layout)

        self.burst_rate, self.burst_rate_combo = self._make_freq_field(10000.0, "Hz")
        burst_rate_row = QHBoxLayout()
        burst_rate_row.addWidget(self.burst_rate)
        burst_rate_row.addWidget(self.burst_rate_combo)
        burst_rate_row.addStretch()
        burst_layout.addRow("Burst Rate:", burst_rate_row)

        self.burst_count = QSpinBox()
        self.burst_count.setRange(2, 32766)
        self.burst_count.setValue(10)
        burst_layout.addRow("Pulses/Burst:", self.burst_count)

        self.burst_period = QSpinBox()
        self.burst_period.setRange(4, 32767)
        self.burst_period.setValue(20)
        burst_layout.addRow("Periods/Burst:", self.burst_period)
        layout.addWidget(burst_group)

        self.btn_apply_trigger = QPushButton("Apply Trigger Settings")
        layout.addWidget(self.btn_apply_trigger)
        layout.addStretch()

        self._add_scroll_tab(tab, "Trigger")

    def _create_delays_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()
        tab.setLayout(layout)

        ref_options = ["T0", "A", "B", "C", "D"]
        self.delay_widgets = {}

        for ch_name, ch_id in [("A", 2), ("B", 3), ("C", 5), ("D", 6)]:
            group = QGroupBox(f"Channel {ch_name}")
            group_layout = QGridLayout()
            group.setLayout(group_layout)

            # Reference selector
            group_layout.addWidget(QLabel("Reference:"), 0, 0)
            ref_combo = QComboBox()
            ref_combo.addItems(ref_options)
            ref_combo.setCurrentText("T0")
            group_layout.addWidget(ref_combo, 0, 1)

            # Delay value + unit dropdown
            delay_spin, delay_combo = self._make_time_field(0.0, "μs")
            group_layout.addWidget(QLabel("Delay:"), 1, 0)
            group_layout.addWidget(delay_spin, 1, 1)
            group_layout.addWidget(delay_combo, 1, 2)

            # Width value + unit dropdown
            width_spin, width_combo = self._make_time_field(1.0, "μs")
            group_layout.addWidget(QLabel("Width:"), 2, 0)
            group_layout.addWidget(width_spin, 2, 1)
            group_layout.addWidget(width_combo, 2, 2)

            group_layout.setColumnStretch(3, 1)

            self.delay_widgets[ch_name] = {
                "id": ch_id,
                "reference": ref_combo,
                "delay": delay_spin,
                "delay_combo": delay_combo,
                "width": width_spin,
                "width_combo": width_combo,
            }
            layout.addWidget(group)

        self.btn_apply_delays = QPushButton("Apply All Delays")
        layout.addWidget(self.btn_apply_delays)
        layout.addStretch()

        self._add_scroll_tab(tab, "Delays")

    def _create_outputs_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()
        tab.setLayout(layout)

        self.output_widgets = {}
        channels = [("T0", 1), ("A", 2), ("B", 3), ("AB/-AB", 4),
                    ("C", 5), ("D", 6), ("CD/-CD", 7)]

        grid = QGridLayout()
        headers = ["Channel", "Mode", "Polarity", "Load", "Amplitude", "Offset"]
        for col, header in enumerate(headers):
            lbl = QLabel(f"<b>{header}</b>")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(lbl, 0, col)

        for row, (ch_name, ch_id) in enumerate(channels, start=1):
            grid.addWidget(QLabel(ch_name), row, 0)

            mode_combo = QComboBox()
            mode_combo.addItems(["TTL", "NIM", "ECL", "VAR"])
            grid.addWidget(mode_combo, row, 1)

            pol_combo = QComboBox()
            pol_combo.addItems(["Normal", "Inverted"])
            grid.addWidget(pol_combo, row, 2)

            load_combo = QComboBox()
            load_combo.addItems(["High-Z", "50Ω"])
            grid.addWidget(load_combo, row, 3)

            amp_spin = QDoubleSpinBox()
            amp_spin.setRange(-4.0, 4.0)
            amp_spin.setDecimals(2)
            amp_spin.setValue(4.0)
            amp_spin.setSuffix(" V")
            grid.addWidget(amp_spin, row, 4)

            off_spin = QDoubleSpinBox()
            off_spin.setRange(-3.0, 4.0)
            off_spin.setDecimals(2)
            off_spin.setValue(0.0)
            off_spin.setSuffix(" V")
            grid.addWidget(off_spin, row, 5)

            self.output_widgets[ch_name] = {
                "id": ch_id,
                "mode": mode_combo,
                "polarity": pol_combo,
                "load": load_combo,
                "amplitude": amp_spin,
                "offset": off_spin,
            }

        layout.addLayout(grid)
        self.btn_apply_outputs = QPushButton("Apply All Output Settings")
        layout.addWidget(self.btn_apply_outputs)
        layout.addStretch()

        self._add_scroll_tab(tab, "Outputs")

    def _create_store_recall_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()
        tab.setLayout(layout)

        store_group = QGroupBox("Store Settings")
        store_layout = QHBoxLayout()
        store_group.setLayout(store_layout)
        self.store_location = QSpinBox()
        self.store_location.setRange(1, 9)
        self.store_location.setValue(1)
        store_layout.addWidget(QLabel("Location (1-9):"))
        store_layout.addWidget(self.store_location)
        self.btn_store = QPushButton("Store")
        store_layout.addWidget(self.btn_store)
        layout.addWidget(store_group)

        recall_group = QGroupBox("Recall Settings")
        recall_layout = QHBoxLayout()
        recall_group.setLayout(recall_layout)
        self.recall_location = QSpinBox()
        self.recall_location.setRange(0, 9)
        self.recall_location.setValue(0)
        recall_layout.addWidget(QLabel("Location (0=defaults, 1-9):"))
        recall_layout.addWidget(self.recall_location)
        self.btn_recall = QPushButton("Recall")
        recall_layout.addWidget(self.btn_recall)
        layout.addWidget(recall_group)

        defaults_group = QGroupBox("Quick Actions")
        defaults_layout = QVBoxLayout()
        defaults_group.setLayout(defaults_layout)
        self.btn_recall_defaults = QPushButton("Recall Factory Defaults (Location 0)")
        defaults_layout.addWidget(self.btn_recall_defaults)
        layout.addWidget(defaults_group)

        status_group = QGroupBox("Instrument Status")
        status_layout = QVBoxLayout()
        status_group.setLayout(status_layout)
        self.btn_read_status = QPushButton("Read Status")
        status_layout.addWidget(self.btn_read_status)
        self.error_status_label = QLabel("Error Status: ---")
        self.inst_status_label = QLabel("Instrument Status: ---")
        status_layout.addWidget(self.error_status_label)
        status_layout.addWidget(self.inst_status_label)
        layout.addWidget(status_group)

        layout.addStretch()
        self._add_scroll_tab(tab, "Store/Recall")

    # =========================================================================
    # BACKWARD COMPATIBLE API - matches existing main_window.py usage
    # =========================================================================
    def get_delayA(self) -> float:
        w = self.delay_widgets["A"]
        return self._value_in_seconds(w["delay"], w["delay_combo"])

    def get_widthA(self) -> float:
        w = self.delay_widgets["A"]
        return self._value_in_seconds(w["width"], w["width_combo"])

    def get_delayB(self) -> float:
        w = self.delay_widgets["B"]
        return self._value_in_seconds(w["delay"], w["delay_combo"])

    def get_widthB(self) -> float:
        w = self.delay_widgets["B"]
        return self._value_in_seconds(w["width"], w["width_combo"])

    def get_delayC(self) -> float:
        w = self.delay_widgets["C"]
        return self._value_in_seconds(w["delay"], w["delay_combo"])

    def get_widthC(self) -> float:
        w = self.delay_widgets["C"]
        return self._value_in_seconds(w["width"], w["width_combo"])

    def get_delayD(self) -> float:
        w = self.delay_widgets["D"]
        return self._value_in_seconds(w["delay"], w["delay_combo"])

    def get_widthD(self) -> float:
        w = self.delay_widgets["D"]
        return self._value_in_seconds(w["width"], w["width_combo"])

    # =========================================================================
    # Extended functionality
    # =========================================================================
    def get_trigger_mode(self) -> int:
        return self.trig_mode_group.checkedId()

    def get_internal_rate(self) -> float:
        return self._value_in_hz(self.internal_rate, self.internal_rate_combo)

    def get_burst_rate(self) -> float:
        return self._value_in_hz(self.burst_rate, self.burst_rate_combo)

    def get_delay_with_reference(self, channel: str) -> tuple:
        """Return (reference_channel_name, delay_seconds) for a channel."""
        w = self.delay_widgets[channel]
        ref = w["reference"].currentText()
        delay = self._value_in_seconds(w["delay"], w["delay_combo"])
        return ref, delay

    def get_output_config(self, channel_name: str) -> dict:
        w = self.output_widgets.get(channel_name)
        if not w:
            return {}
        mode_map = {"TTL": 0, "NIM": 1, "ECL": 2, "VAR": 3}
        pol_map = {"Normal": 1, "Inverted": 0}
        load_map = {"High-Z": 1, "50Ω": 0}
        return {
            "id": w["id"],
            "mode": mode_map.get(w["mode"].currentText(), 0),
            "polarity": pol_map.get(w["polarity"].currentText(), 1),
            "load": load_map.get(w["load"].currentText(), 1),
            "amplitude": w["amplitude"].value(),
            "offset": w["offset"].value(),
        }

    def set_status(self, text: str):
        self.status_label.setText(f"Status: {text}")

    def set_error_status(self, value: int):
        bits = []
        if value & 0x40:
            bits.append("Recall corrupt")
        if value & 0x20:
            bits.append("Delay range")
        if value & 0x10:
            bits.append("Delay linkage")
        if value & 0x08:
            bits.append("Wrong mode")
        if value & 0x04:
            bits.append("Value range")
        if value & 0x02:
            bits.append("Param count")
        if value & 0x01:
            bits.append("Unknown cmd")
        text = ", ".join(bits) if bits else "OK"
        self.error_status_label.setText(f"Error Status: {value} ({text})")

    def set_instrument_status(self, value: int):
        bits = []
        if value & 0x80:
            bits.append("Memory corrupt")
        if value & 0x40:
            bits.append("Service req")
        if value & 0x10:
            bits.append("Rate error")
        if value & 0x08:
            bits.append("PLL unlock")
        if value & 0x04:
            bits.append("Triggered")
        if value & 0x02:
            bits.append("Busy")
        if value & 0x01:
            bits.append("Cmd error")
        text = ", ".join(bits) if bits else "Idle"
        self.inst_status_label.setText(f"Instrument Status: {value} ({text})")
