# from PyQt6.QtWidgets import (
#     QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton, QFormLayout, QDoubleSpinBox,
#     QGridLayout, QLabel, QButtonGroup
# )
# from utils.status_lamp import StatusLamp

# class DG535Panel(QGroupBox):
#     def __init__(self):
#         super().__init__("DG535 Control")

#         layout = QVBoxLayout()
#         self.setLayout(layout)

#         # ⭐ NEW: Status Lamp
#         self.lamp = StatusLamp(size=14)
#         layout.addWidget(self.lamp)

#         # Buttons
#         hl = QHBoxLayout()
#         self.btn_connect = QPushButton("Connect DG535")
#         self.btn_fire = QPushButton("Fire DG535")
#         self.btn_disconnect = QPushButton("Disconnect")
#         hl.addWidget(self.btn_connect)
#         hl.addWidget(self.btn_fire)
#         layout.addLayout(hl)
#         layout.addWidget(self.btn_disconnect)

#         # ----------------------- Improved Value Entry with Unit Buttons -----------------------------
#         grid = QGridLayout()
#         grid.setSpacing(8)

#         # Headers
#         grid.addWidget(QLabel("<b>Parameter</b>"), 0, 0)
#         grid.addWidget(QLabel("<b>Value</b>"), 0, 1)
#         grid.addWidget(QLabel("<b>Units</b>"), 0, 2)

#         row_idx = 1

#         # Delay A
#         self.delayA, self.delayA_units = self._create_value_with_units("Delay A", 0.0, "μs")
#         grid.addWidget(QLabel("Delay A:"), row_idx, 0)
#         grid.addWidget(self.delayA, row_idx, 1)
#         grid.addLayout(self.delayA_units, row_idx, 2)
#         row_idx += 1

#         # Width A
#         self.widthA, self.widthA_units = self._create_value_with_units("Width A", 1.0, "μs")
#         grid.addWidget(QLabel("Width A:"), row_idx, 0)
#         grid.addWidget(self.widthA, row_idx, 1)
#         grid.addLayout(self.widthA_units, row_idx, 2)
#         row_idx += 1

#         # Delay B
#         self.delayB, self.delayB_units = self._create_value_with_units("Delay B", 0.0, "μs")
#         grid.addWidget(QLabel("Delay B:"), row_idx, 0)
#         grid.addWidget(self.delayB, row_idx, 1)
#         grid.addLayout(self.delayB_units, row_idx, 2)
#         row_idx += 1

#         # Width B
#         self.widthB, self.widthB_units = self._create_value_with_units("Width B", 1.0, "μs")
#         grid.addWidget(QLabel("Width B:"), row_idx, 0)
#         grid.addWidget(self.widthB, row_idx, 1)
#         grid.addLayout(self.widthB_units, row_idx, 2)

#         layout.addLayout(grid)

#     def _create_value_with_units(self, name, default_value, default_unit):
#         """Create a spinbox with unit selector buttons (s, ms, μs, ns, ps)"""
#         # Spinbox for numeric value
#         spinbox = QDoubleSpinBox()
#         spinbox.setDecimals(3)
#         spinbox.setRange(0, 999999)
#         spinbox.setValue(default_value)
#         spinbox.setMaximumWidth(100)

#         # Unit buttons
#         units_layout = QHBoxLayout()
#         units_layout.setSpacing(2)

#         button_group = QButtonGroup(self)
#         button_group.setExclusive(True)

#         units = ["s", "ms", "μs", "ns", "ps"]
#         multipliers = {
#             "s": 1.0,
#             "ms": 1e-3,
#             "μs": 1e-6,
#             "ns": 1e-9,
#             "ps": 1e-12
#         }

#         buttons = {}
#         for unit in units:
#             btn = QPushButton(unit)
#             btn.setCheckable(True)
#             btn.setMaximumWidth(40)
#             btn.setStyleSheet("""
#                 QPushButton {
#                     padding: 2px;
#                     font-size: 10px;
#                 }
#                 QPushButton:checked {
#                     background-color: #2196F3;
#                     color: white;
#                     font-weight: bold;
#                 }
#             """)
#             button_group.addButton(btn)
#             units_layout.addWidget(btn)
#             buttons[unit] = btn

#             # Store multiplier as button property
#             btn.multiplier = multipliers[unit]

#         # Set default unit
#         buttons[default_unit].setChecked(True)

#         # Store button group and buttons for later access
#         units_layout.button_group = button_group
#         units_layout.buttons = buttons
#         units_layout.spinbox = spinbox

#         return spinbox, units_layout

#     def get_value_in_seconds(self, spinbox, units_layout):
#         """Convert spinbox value to seconds based on selected unit"""
#         value = spinbox.value()
#         checked_button = units_layout.button_group.checkedButton()
#         if checked_button:
#             return value * checked_button.multiplier
#         return value * 1e-6  # Default to microseconds if nothing checked

#     # Convenience methods to get values in seconds
#     def get_delayA(self):
#         return self.get_value_in_seconds(self.delayA, self.delayA_units)

#     def get_widthA(self):
#         return self.get_value_in_seconds(self.widthA, self.widthA_units)

#     def get_delayB(self):
#         return self.get_value_in_seconds(self.delayB, self.delayB_units)

#     def get_widthB(self):
#         return self.get_value_in_seconds(self.widthB, self.widthB_units)
# gui/dg535_panel.py
"""
DG535 Control Panel GUI

Full-featured GUI panel for Stanford Research DG535 Digital Delay/Pulse Generator.
Provides access to all major device functions as available on the physical front panel.

BACKWARD COMPATIBLE: Maintains get_delayA(), get_widthA() etc. methods for existing code.

Features:
- Connection control with status indicator
- Trigger mode selection (Internal, External, Single-Shot, Burst, Line)
- All delay channels (A, B, C, D) with reference linking
- Output configuration (mode, polarity, impedance, amplitude, offset)
- Store/Recall settings
- Status monitoring
"""

from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton,
    QLabel, QDoubleSpinBox, QComboBox, QTabWidget, QWidget,
    QButtonGroup, QFormLayout, QSpinBox, QFrame
)
from PyQt6.QtCore import Qt
from utils.status_lamp import StatusLamp


class DG535Panel(QGroupBox):
    """
    Complete control panel for DG535 Digital Delay Generator.

    Organized into tabs:
    - Trigger: Trigger mode and settings
    - Delays: Channel A, B, C, D delay settings
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

    def _create_trigger_tab(self):
        """Create the Trigger configuration tab."""
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
                QPushButton {
                    padding: 6px 12px;
                }
                QPushButton:checked {
                    background-color: #2196F3;
                    color: white;
                    font-weight: bold;
                }
            """)
            self.trig_mode_group.addButton(btn, mode_id)
            self.trig_mode_buttons[mode_id] = btn
            mode_layout.addWidget(btn)

        # Default to Single-Shot
        self.trig_mode_buttons[2].setChecked(True)
        layout.addWidget(mode_group)

        # Internal Trigger Settings
        internal_group = QGroupBox("Internal Trigger")
        internal_layout = QFormLayout()
        internal_group.setLayout(internal_layout)

        self.internal_rate, self.internal_rate_units = self._create_freq_with_units(
            "Rate", 10000.0, "Hz"
        )
        rate_row = QHBoxLayout()
        rate_row.addWidget(self.internal_rate)
        rate_row.addLayout(self.internal_rate_units)
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

        self.burst_rate, self.burst_rate_units = self._create_freq_with_units(
            "Burst Rate", 10000.0, "Hz"
        )
        burst_rate_row = QHBoxLayout()
        burst_rate_row.addWidget(self.burst_rate)
        burst_rate_row.addLayout(self.burst_rate_units)
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

        # Apply trigger settings button
        self.btn_apply_trigger = QPushButton("Apply Trigger Settings")
        layout.addWidget(self.btn_apply_trigger)

        layout.addStretch()
        self.tabs.addTab(tab, "Trigger")

    def _create_delays_tab(self):
        """Create the Delays configuration tab."""
        tab = QWidget()
        layout = QVBoxLayout()
        tab.setLayout(layout)

        # Reference channel options for linking
        ref_options = ["T0", "A", "B", "C", "D"]

        # Store delay widgets - these are the PRIMARY delay/width controls
        self.delay_widgets = {}

        for ch_name, ch_id in [("A", 2), ("B", 3), ("C", 5), ("D", 6)]:
            group = QGroupBox(f"Channel {ch_name}")
            group_layout = QGridLayout()
            group.setLayout(group_layout)

            # Reference selector
            ref_label = QLabel("Reference:")
            ref_combo = QComboBox()
            ref_combo.addItems(ref_options)
            ref_combo.setCurrentText("T0")

            group_layout.addWidget(ref_label, 0, 0)
            group_layout.addWidget(ref_combo, 0, 1)

            # Delay value with unit selector
            delay_label = QLabel("Delay:")
            delay_spin, delay_units = self._create_time_with_units(
                f"Delay {ch_name}", 0.0, "μs"
            )

            group_layout.addWidget(delay_label, 1, 0)
            group_layout.addWidget(delay_spin, 1, 1)
            group_layout.addLayout(delay_units, 1, 2)

            # Width value with unit selector (for pulse outputs)
            width_label = QLabel("Width:")
            width_spin, width_units = self._create_time_with_units(
                f"Width {ch_name}", 1.0, "μs"
            )

            group_layout.addWidget(width_label, 2, 0)
            group_layout.addWidget(width_spin, 2, 1)
            group_layout.addLayout(width_units, 2, 2)

            # Store widgets for access
            self.delay_widgets[ch_name] = {
                "id": ch_id,
                "reference": ref_combo,
                "delay": delay_spin,
                "delay_units": delay_units,
                "width": width_spin,
                "width_units": width_units,
            }

            layout.addWidget(group)

        # Apply delays button
        self.btn_apply_delays = QPushButton("Apply All Delays")
        layout.addWidget(self.btn_apply_delays)

        layout.addStretch()
        self.tabs.addTab(tab, "Delays")

    def _create_outputs_tab(self):
        """Create the Outputs configuration tab."""
        tab = QWidget()
        layout = QVBoxLayout()
        tab.setLayout(layout)

        # Output configuration for each channel
        self.output_widgets = {}

        channels = [("T0", 1), ("A", 2), ("B", 3), ("AB/-AB", 4),
                    ("C", 5), ("D", 6), ("CD/-CD", 7)]

        # Use a grid for compact layout
        grid = QGridLayout()

        # Headers
        headers = ["Channel", "Mode", "Polarity", "Load", "Amplitude", "Offset"]
        for col, header in enumerate(headers):
            lbl = QLabel(f"<b>{header}</b>")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(lbl, 0, col)

        for row, (ch_name, ch_id) in enumerate(channels, start=1):
            # Channel name
            grid.addWidget(QLabel(ch_name), row, 0)

            # Mode selector
            mode_combo = QComboBox()
            mode_combo.addItems(["TTL", "NIM", "ECL", "VAR"])
            grid.addWidget(mode_combo, row, 1)

            # Polarity selector
            pol_combo = QComboBox()
            pol_combo.addItems(["Normal", "Inverted"])
            grid.addWidget(pol_combo, row, 2)

            # Load impedance
            load_combo = QComboBox()
            load_combo.addItems(["High-Z", "50Ω"])
            grid.addWidget(load_combo, row, 3)

            # Amplitude (for VAR mode)
            amp_spin = QDoubleSpinBox()
            amp_spin.setRange(-4.0, 4.0)
            amp_spin.setDecimals(2)
            amp_spin.setValue(4.0)
            amp_spin.setSuffix(" V")
            grid.addWidget(amp_spin, row, 4)

            # Offset (for VAR mode)
            off_spin = QDoubleSpinBox()
            off_spin.setRange(-3.0, 4.0)
            off_spin.setDecimals(2)
            off_spin.setValue(0.0)
            off_spin.setSuffix(" V")
            grid.addWidget(off_spin, row, 5)

            # Store widgets
            self.output_widgets[ch_name] = {
                "id": ch_id,
                "mode": mode_combo,
                "polarity": pol_combo,
                "load": load_combo,
                "amplitude": amp_spin,
                "offset": off_spin,
            }

        layout.addLayout(grid)

        # Apply outputs button
        self.btn_apply_outputs = QPushButton("Apply All Output Settings")
        layout.addWidget(self.btn_apply_outputs)

        layout.addStretch()
        self.tabs.addTab(tab, "Outputs")

    def _create_store_recall_tab(self):
        """Create the Store/Recall settings tab."""
        tab = QWidget()
        layout = QVBoxLayout()
        tab.setLayout(layout)

        # Store section
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

        # Recall section
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

        # Quick buttons for factory defaults
        defaults_group = QGroupBox("Quick Actions")
        defaults_layout = QVBoxLayout()
        defaults_group.setLayout(defaults_layout)

        self.btn_recall_defaults = QPushButton("Recall Factory Defaults (Location 0)")
        defaults_layout.addWidget(self.btn_recall_defaults)

        layout.addWidget(defaults_group)

        # Status display
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
        self.tabs.addTab(tab, "Store/Recall")

    # =========================================================================
    # Unit Selector Creation Helpers
    # =========================================================================

    def _create_time_with_units(self, name, default_value, default_unit):
        """Create a spinbox with time unit selector buttons (s, ms, μs, ns, ps)."""
        spinbox = QDoubleSpinBox()
        spinbox.setDecimals(6)
        spinbox.setRange(0, 999999999)
        spinbox.setValue(default_value)
        spinbox.setMaximumWidth(120)

        units_layout = QHBoxLayout()
        units_layout.setSpacing(2)

        button_group = QButtonGroup(self)
        button_group.setExclusive(True)

        units = ["s", "ms", "μs", "ns", "ps"]
        multipliers = {
            "s": 1.0,
            "ms": 1e-3,
            "μs": 1e-6,
            "ns": 1e-9,
            "ps": 1e-12
        }

        buttons = {}
        for unit in units:
            btn = QPushButton(unit)
            btn.setCheckable(True)
            btn.setMaximumWidth(45)
            btn.setStyleSheet("""
                QPushButton {
                    padding: 2px;
                    font-size: 10px;
                }
                QPushButton:checked {
                    background-color: #2196F3;
                    color: white;
                    font-weight: bold;
                }
            """)
            button_group.addButton(btn)
            units_layout.addWidget(btn)
            buttons[unit] = btn
            btn.multiplier = multipliers[unit]

        # Set default unit
        if default_unit in buttons:
            buttons[default_unit].setChecked(True)

        # Store references for later access
        units_layout.button_group = button_group
        units_layout.buttons = buttons
        units_layout.spinbox = spinbox

        return spinbox, units_layout

    def _create_freq_with_units(self, name, default_value, default_unit):
        """Create a spinbox with frequency unit selector buttons (Hz, kHz, MHz)."""
        spinbox = QDoubleSpinBox()
        spinbox.setDecimals(3)
        spinbox.setRange(0, 999999999)
        spinbox.setValue(default_value)
        spinbox.setMaximumWidth(120)

        units_layout = QHBoxLayout()
        units_layout.setSpacing(2)

        button_group = QButtonGroup(self)
        button_group.setExclusive(True)

        units = ["Hz", "kHz", "MHz"]
        multipliers = {
            "Hz": 1.0,
            "kHz": 1e3,
            "MHz": 1e6
        }

        buttons = {}
        for unit in units:
            btn = QPushButton(unit)
            btn.setCheckable(True)
            btn.setMaximumWidth(45)
            btn.setStyleSheet("""
                QPushButton {
                    padding: 2px;
                    font-size: 10px;
                }
                QPushButton:checked {
                    background-color: #2196F3;
                    color: white;
                    font-weight: bold;
                }
            """)
            button_group.addButton(btn)
            units_layout.addWidget(btn)
            buttons[unit] = btn
            btn.multiplier = multipliers[unit]

        # Set default unit
        if default_unit in buttons:
            buttons[default_unit].setChecked(True)

        # Store references for later access
        units_layout.button_group = button_group
        units_layout.buttons = buttons
        units_layout.spinbox = spinbox

        return spinbox, units_layout

    def _get_value_in_seconds(self, spinbox, units_layout):
        """Convert spinbox value to seconds based on selected unit."""
        value = spinbox.value()
        checked_button = units_layout.button_group.checkedButton()
        if checked_button:
            return value * checked_button.multiplier
        return value * 1e-6  # Default to microseconds

    def _get_value_in_hz(self, spinbox, units_layout):
        """Convert spinbox value to Hz based on selected unit."""
        value = spinbox.value()
        checked_button = units_layout.button_group.checkedButton()
        if checked_button:
            return value * checked_button.multiplier
        return value  # Default to Hz

    # =========================================================================
    # BACKWARD COMPATIBLE API - These methods match your existing main_window.py
    # =========================================================================

    def get_delayA(self) -> float:
        """Get channel A delay in seconds. BACKWARD COMPATIBLE."""
        w = self.delay_widgets["A"]
        return self._get_value_in_seconds(w["delay"], w["delay_units"])

    def get_widthA(self) -> float:
        """Get channel A width in seconds. BACKWARD COMPATIBLE."""
        w = self.delay_widgets["A"]
        return self._get_value_in_seconds(w["width"], w["width_units"])

    def get_delayB(self) -> float:
        """Get channel B delay in seconds."""
        w = self.delay_widgets["B"]
        return self._get_value_in_seconds(w["delay"], w["delay_units"])

    def get_widthB(self) -> float:
        """Get channel B width in seconds."""
        w = self.delay_widgets["B"]
        return self._get_value_in_seconds(w["width"], w["width_units"])

    def get_delayC(self) -> float:
        """Get channel C delay in seconds."""
        w = self.delay_widgets["C"]
        return self._get_value_in_seconds(w["delay"], w["delay_units"])

    def get_widthC(self) -> float:
        """Get channel C width in seconds."""
        w = self.delay_widgets["C"]
        return self._get_value_in_seconds(w["width"], w["width_units"])

    def get_delayD(self) -> float:
        """Get channel D delay in seconds."""
        w = self.delay_widgets["D"]
        return self._get_value_in_seconds(w["delay"], w["delay_units"])

    def get_widthD(self) -> float:
        """Get channel D width in seconds."""
        w = self.delay_widgets["D"]
        return self._get_value_in_seconds(w["width"], w["width_units"])

    # =========================================================================
    # NEW API - Extended functionality
    # =========================================================================

    def get_trigger_mode(self) -> int:
        """Get selected trigger mode (0-4)."""
        return self.trig_mode_group.checkedId()

    def get_internal_rate(self) -> float:
        """Get internal trigger rate in Hz."""
        return self._get_value_in_hz(self.internal_rate, self.internal_rate_units)

    def get_burst_rate(self) -> float:
        """Get burst trigger rate in Hz."""
        return self._get_value_in_hz(self.burst_rate, self.burst_rate_units)

    def get_delay_with_reference(self, channel: str) -> tuple:
        """
        Return (reference_channel_name, delay_seconds) for a channel.
        
        Args:
            channel: "A", "B", "C", or "D"
            
        Returns:
            Tuple of (reference_name, delay_in_seconds)
        """
        w = self.delay_widgets[channel]
        ref = w["reference"].currentText()
        delay = self._get_value_in_seconds(w["delay"], w["delay_units"])
        return ref, delay

    def get_output_config(self, channel_name: str) -> dict:
        """Get output configuration for a channel."""
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
        """Update the status label."""
        self.status_label.setText(f"Status: {text}")

    def set_error_status(self, value: int):
        """Display error status byte."""
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
        """Display instrument status byte."""
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