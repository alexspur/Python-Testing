# from PyQt6.QtWidgets import (
#     QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton,
#     QFormLayout, QDoubleSpinBox, QButtonGroup, QGridLayout
# )
# from utils.status_lamp import StatusLamp
# from PyQt6.QtWidgets import QComboBox, QLabel
# from PyQt6.QtWidgets import QPushButton

# class BNC575Panel(QGroupBox):
#     def __init__(self):
#         super().__init__("BNC575 Control")

#         layout = QVBoxLayout()
#         self.setLayout(layout)
#         self.lamp = StatusLamp(size=14)
#         layout.addWidget(self.lamp)

#         # --------------------------- Buttons ---------------------------
#         row = QHBoxLayout()
#         self.btn_connect = QPushButton("Connect BNC575")
#         self.btn_fire = QPushButton("Fire Pulse")
#         self.btn_disconnect = QPushButton("Disconnect")
#         layout.addWidget(self.btn_disconnect)
#         row.addWidget(self.btn_connect)
#         row.addWidget(self.btn_fire)
#         layout.addLayout(row)

#         # ----------------------- Improved Value Entry with Unit Buttons -----------------------------
#         # Create spinboxes with unit selectors for each channel
#         grid = QGridLayout()
#         grid.setSpacing(8)

#         # Headers
#         grid.addWidget(QLabel("<b>Parameter</b>"), 0, 0)
#         grid.addWidget(QLabel("<b>Value</b>"), 0, 1)
#         grid.addWidget(QLabel("<b>Units</b>"), 0, 2)

#         row_idx = 1

#         # Channel A
#         self.widthA, self.widthA_units = self._create_value_with_units("Width A", 1.0, "μs")
#         grid.addWidget(QLabel("Width A:"), row_idx, 0)
#         grid.addWidget(self.widthA, row_idx, 1)
#         grid.addLayout(self.widthA_units, row_idx, 2)
#         row_idx += 1

#         self.delayA, self.delayA_units = self._create_value_with_units("Delay A", 0.0, "μs")
#         grid.addWidget(QLabel("Delay A:"), row_idx, 0)
#         grid.addWidget(self.delayA, row_idx, 1)
#         grid.addLayout(self.delayA_units, row_idx, 2)
#         row_idx += 1

#         # Channel B
#         self.widthB, self.widthB_units = self._create_value_with_units("Width B", 1.0, "μs")
#         grid.addWidget(QLabel("Width B:"), row_idx, 0)
#         grid.addWidget(self.widthB, row_idx, 1)
#         grid.addLayout(self.widthB_units, row_idx, 2)
#         row_idx += 1

#         self.delayB, self.delayB_units = self._create_value_with_units("Delay B", 0.0, "μs")
#         grid.addWidget(QLabel("Delay B:"), row_idx, 0)
#         grid.addWidget(self.delayB, row_idx, 1)
#         grid.addLayout(self.delayB_units, row_idx, 2)
#         row_idx += 1

#         # Channel C
#         self.widthC, self.widthC_units = self._create_value_with_units("Width C", 40.0, "μs")
#         grid.addWidget(QLabel("Width C:"), row_idx, 0)
#         grid.addWidget(self.widthC, row_idx, 1)
#         grid.addLayout(self.widthC_units, row_idx, 2)
#         row_idx += 1

#         self.delayC, self.delayC_units = self._create_value_with_units("Delay C", 0.0, "μs")
#         grid.addWidget(QLabel("Delay C:"), row_idx, 0)
#         grid.addWidget(self.delayC, row_idx, 1)
#         grid.addLayout(self.delayC_units, row_idx, 2)
#         row_idx += 1

#         # Channel D
#         self.widthD, self.widthD_units = self._create_value_with_units("Width D", 40.0, "μs")
#         grid.addWidget(QLabel("Width D:"), row_idx, 0)
#         grid.addWidget(self.widthD, row_idx, 1)
#         grid.addLayout(self.widthD_units, row_idx, 2)
#         row_idx += 1

#         self.delayD, self.delayD_units = self._create_value_with_units("Delay D", 0.0, "μs")
#         grid.addWidget(QLabel("Delay D:"), row_idx, 0)
#         grid.addWidget(self.delayD, row_idx, 1)
#         grid.addLayout(self.delayD_units, row_idx, 2)

#         layout.addLayout(grid)

#         # --------------------------- Channel Enable Toggles ----------------
#         enable_row = QHBoxLayout()
#         self.btn_en_a = QPushButton("CHA Enabled")
#         self.btn_en_a.setCheckable(True)
#         self.btn_en_a.setChecked(True)
#         self.btn_en_a.setStyleSheet("QPushButton:checked { background-color: #4CAF50; color: white; font-weight: bold; }")

#         self.btn_en_b = QPushButton("CHB Enabled")
#         self.btn_en_b.setCheckable(True)
#         self.btn_en_b.setChecked(True)
#         self.btn_en_b.setStyleSheet("QPushButton:checked { background-color: #4CAF50; color: white; font-weight: bold; }")

#         self.btn_en_c = QPushButton("CHC Enabled")
#         self.btn_en_c.setCheckable(True)
#         self.btn_en_c.setChecked(True)
#         self.btn_en_c.setStyleSheet("QPushButton:checked { background-color: #4CAF50; color: white; font-weight: bold; }")

#         self.btn_en_d = QPushButton("CHD Enabled")
#         self.btn_en_d.setCheckable(True)
#         self.btn_en_d.setChecked(True)
#         self.btn_en_d.setStyleSheet("QPushButton:checked { background-color: #4CAF50; color: white; font-weight: bold; }")

#         enable_row.addWidget(self.btn_en_a)
#         enable_row.addWidget(self.btn_en_b)
#         enable_row.addWidget(self.btn_en_c)
#         enable_row.addWidget(self.btn_en_d)
#         layout.addLayout(enable_row)

#         # Trigger enable toggle
#         trig_row = QHBoxLayout()
#         self.btn_en_trig = QPushButton("Trigger Enabled")
#         self.btn_en_trig.setCheckable(True)
#         self.btn_en_trig.setChecked(True)
#         self.btn_en_trig.setStyleSheet("QPushButton:checked { background-color: #4CAF50; color: white; font-weight: bold; }")
#         trig_row.addWidget(self.btn_en_trig)
#         layout.addLayout(trig_row)

#         # --------------------------- Apply / Read / Arm ----------------
#         row2 = QHBoxLayout()
#         self.btn_apply = QPushButton("Apply Settings")
#         self.btn_read  = QPushButton("Read Settings")
#         self.btn_arm   = QPushButton("Arm (EXT TRIG)")
#         row2.addWidget(self.btn_apply)
#         row2.addWidget(self.btn_read)
#         row2.addWidget(self.btn_arm)

#         layout.addLayout(row2)

#         # --- Trigger Controls ---
#         self.trig_source = QComboBox()
#         self.trig_source.addItems(["EXT", "INT"])
#         grid.addWidget(QLabel("Trigger Source:"), row_idx + 1, 0)
#         grid.addWidget(self.trig_source, row_idx + 1, 1)

#         self.trig_slope = QComboBox()
#         self.trig_slope.addItems(["RIS", "FALL"])
#         grid.addWidget(QLabel("Trigger Slope:"), row_idx + 2, 0)
#         grid.addWidget(self.trig_slope, row_idx + 2, 1)

#         self.trig_level = QDoubleSpinBox()
#         self.trig_level.setDecimals(3)
#         self.trig_level.setRange(0.0, 5.0)
#         self.trig_level.setValue(2.50)
#         grid.addWidget(QLabel("Trigger Level (V):"), row_idx + 3, 0)
#         grid.addWidget(self.trig_level, row_idx + 3, 1)

#         self.btn_apply_trigger = QPushButton("Apply Trigger Settings")
#         layout.addWidget(self.btn_apply_trigger)

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
#     def get_widthA(self):
#         return self.get_value_in_seconds(self.widthA, self.widthA_units)

#     def get_delayA(self):
#         return self.get_value_in_seconds(self.delayA, self.delayA_units)

#     def get_widthB(self):
#         return self.get_value_in_seconds(self.widthB, self.widthB_units)

#     def get_delayB(self):
#         return self.get_value_in_seconds(self.delayB, self.delayB_units)

#     def get_widthC(self):
#         return self.get_value_in_seconds(self.widthC, self.widthC_units)

#     def get_delayC(self):
#         return self.get_value_in_seconds(self.delayC, self.delayC_units)

#     def get_widthD(self):
#         return self.get_value_in_seconds(self.widthD, self.widthD_units)

#     def get_delayD(self):
#         return self.get_value_in_seconds(self.delayD, self.delayD_units)
"""
BNC 575 Series Digital Delay/Pulse Generator GUI Panel
Based on BNC 575 Series Operating Manual Version 5.6

This panel provides a comprehensive interface for controlling the BNC575,
with backward compatibility for existing code that uses simple getter methods.

Features:
- Tabbed interface: System, Channels, Trigger/Gate, Store/Recall
- Unit selectors for time (s/ms/µs/ns/ps) and frequency (Hz/kHz/MHz)
- Support for 2, 4, or 8 channel models
- Backward compatible get_delayA(), get_widthA(), etc. methods

Author: Generated based on BNC 575 Manual
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QComboBox, QTabWidget,
    QCheckBox, QSpinBox, QDoubleSpinBox, QFrame, QScrollArea,
    QSizePolicy, QMessageBox, QStatusBar
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPalette
from typing import Optional, Dict, Callable
from enum import Enum


class TimeUnit(Enum):
    """Time units with conversion factors to seconds"""
    SECONDS = ("s", 1.0)
    MILLISECONDS = ("ms", 1e-3)
    MICROSECONDS = ("µs", 1e-6)
    NANOSECONDS = ("ns", 1e-9)
    PICOSECONDS = ("ps", 1e-12)
    
    def __init__(self, symbol: str, factor: float):
        self.symbol = symbol
        self.factor = factor


class FreqUnit(Enum):
    """Frequency units with conversion factors to Hz"""
    HZ = ("Hz", 1.0)
    KHZ = ("kHz", 1e3)
    MHZ = ("MHz", 1e6)
    
    def __init__(self, symbol: str, factor: float):
        self.symbol = symbol
        self.factor = factor


class ChannelWidget(QWidget):
    """Widget for configuring a single channel"""
    
    settingsChanged = pyqtSignal(str)  # Emits channel name when settings change
    
    def __init__(self, channel_name: str, parent=None):
        super().__init__(parent)
        self.channel_name = channel_name
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)
        
        # Header with enable checkbox
        header = QHBoxLayout()
        self.enable_check = QCheckBox(f"Channel {self.channel_name} Enabled")
        self.enable_check.setStyleSheet("font-weight: bold; font-size: 11pt;")
        header.addWidget(self.enable_check)
        header.addStretch()
        layout.addLayout(header)
        
        # Timing section
        timing_group = QGroupBox("Timing")
        timing_layout = QGridLayout(timing_group)
        timing_layout.setSpacing(4)
        
        # Delay
        timing_layout.addWidget(QLabel("Delay:"), 0, 0)
        self.delay_edit = QLineEdit("0")
        self.delay_edit.setMaximumWidth(120)
        timing_layout.addWidget(self.delay_edit, 0, 1)
        self.delay_unit = QComboBox()
        for unit in TimeUnit:
            self.delay_unit.addItem(unit.symbol, unit)
        self.delay_unit.setCurrentText("µs")
        timing_layout.addWidget(self.delay_unit, 0, 2)
        
        # Width
        timing_layout.addWidget(QLabel("Width:"), 1, 0)
        self.width_edit = QLineEdit("100")
        self.width_edit.setMaximumWidth(120)
        timing_layout.addWidget(self.width_edit, 1, 1)
        self.width_unit = QComboBox()
        for unit in TimeUnit:
            self.width_unit.addItem(unit.symbol, unit)
        self.width_unit.setCurrentText("ns")
        timing_layout.addWidget(self.width_unit, 1, 2)
        
        # Sync source
        timing_layout.addWidget(QLabel("Sync:"), 2, 0)
        self.sync_combo = QComboBox()
        self.sync_combo.addItems(["T0", "CHA", "CHB", "CHC", "CHD", "CHE", "CHF", "CHG", "CHH"])
        timing_layout.addWidget(self.sync_combo, 2, 1, 1, 2)
        
        layout.addWidget(timing_group)
        
        # Output section
        output_group = QGroupBox("Output")
        output_layout = QGridLayout(output_group)
        output_layout.setSpacing(4)
        
        # Mode
        output_layout.addWidget(QLabel("Mode:"), 0, 0)
        self.output_mode = QComboBox()
        self.output_mode.addItems(["TTL", "Adjustable"])
        output_layout.addWidget(self.output_mode, 0, 1)
        
        # Polarity
        output_layout.addWidget(QLabel("Polarity:"), 0, 2)
        self.polarity_combo = QComboBox()
        self.polarity_combo.addItems(["Normal (High)", "Inverted (Low)"])
        output_layout.addWidget(self.polarity_combo, 0, 3)
        
        # Amplitude (for adjustable mode)
        output_layout.addWidget(QLabel("Amplitude:"), 1, 0)
        self.amplitude_spin = QDoubleSpinBox()
        self.amplitude_spin.setRange(2.0, 20.0)
        self.amplitude_spin.setValue(4.0)
        self.amplitude_spin.setSuffix(" V")
        self.amplitude_spin.setDecimals(2)
        output_layout.addWidget(self.amplitude_spin, 1, 1)
        
        layout.addWidget(output_group)
        
        # Channel mode section
        mode_group = QGroupBox("Channel Mode")
        mode_layout = QGridLayout(mode_group)
        mode_layout.setSpacing(4)
        
        mode_layout.addWidget(QLabel("Mode:"), 0, 0)
        self.channel_mode = QComboBox()
        self.channel_mode.addItems(["Normal", "Single Shot", "Burst", "Duty Cycle"])
        mode_layout.addWidget(self.channel_mode, 0, 1)
        
        # Burst count
        mode_layout.addWidget(QLabel("Burst:"), 0, 2)
        self.burst_spin = QSpinBox()
        self.burst_spin.setRange(1, 9999999)
        self.burst_spin.setValue(1)
        mode_layout.addWidget(self.burst_spin, 0, 3)
        
        # Duty cycle counts
        mode_layout.addWidget(QLabel("On:"), 1, 0)
        self.on_spin = QSpinBox()
        self.on_spin.setRange(1, 9999999)
        self.on_spin.setValue(1)
        mode_layout.addWidget(self.on_spin, 1, 1)
        
        mode_layout.addWidget(QLabel("Off:"), 1, 2)
        self.off_spin = QSpinBox()
        self.off_spin.setRange(1, 9999999)
        self.off_spin.setValue(1)
        mode_layout.addWidget(self.off_spin, 1, 3)
        
        # Wait count
        mode_layout.addWidget(QLabel("Wait:"), 2, 0)
        self.wait_spin = QSpinBox()
        self.wait_spin.setRange(0, 9999999)
        self.wait_spin.setValue(0)
        mode_layout.addWidget(self.wait_spin, 2, 1)
        
        layout.addWidget(mode_group)
        
        # Connect signals
        self.enable_check.stateChanged.connect(lambda: self.settingsChanged.emit(self.channel_name))
        self.delay_edit.editingFinished.connect(lambda: self.settingsChanged.emit(self.channel_name))
        self.width_edit.editingFinished.connect(lambda: self.settingsChanged.emit(self.channel_name))
    
    def get_delay_seconds(self) -> float:
        """Get delay value in seconds"""
        try:
            value = float(self.delay_edit.text())
            unit = self.delay_unit.currentData()
            return value * unit.factor
        except (ValueError, AttributeError):
            return 0.0
    
    def set_delay_seconds(self, seconds: float):
        """Set delay from seconds value"""
        unit = self.delay_unit.currentData()
        value = seconds / unit.factor
        self.delay_edit.setText(f"{value:.6g}")
    
    def get_width_seconds(self) -> float:
        """Get width value in seconds"""
        try:
            value = float(self.width_edit.text())
            unit = self.width_unit.currentData()
            return value * unit.factor
        except (ValueError, AttributeError):
            return 100e-9
    
    def set_width_seconds(self, seconds: float):
        """Set width from seconds value"""
        unit = self.width_unit.currentData()
        value = seconds / unit.factor
        self.width_edit.setText(f"{value:.6g}")
    
    def is_enabled(self) -> bool:
        """Check if channel is enabled"""
        return self.enable_check.isChecked()
    
    def set_enabled(self, enabled: bool):
        """Set channel enabled state"""
        self.enable_check.setChecked(enabled)


class BNC575Panel(QWidget):
    """
    Main GUI panel for BNC 575 Series Digital Delay/Pulse Generator
    
    Provides tabbed interface with:
    - System tab: Mode, period/frequency, trigger settings
    - Channels tab: Individual channel configuration
    - Trigger/Gate tab: External input configuration
    - Store/Recall tab: Configuration memory management
    
    Backward compatible methods:
    - get_delayA(), get_delayB(), etc. (returns seconds)
    - get_widthA(), get_widthB(), etc. (returns seconds)
    """
    
    # Signals for main window integration
    connectRequested = pyqtSignal()
    disconnectRequested = pyqtSignal()
    runRequested = pyqtSignal()
    stopRequested = pyqtSignal()
    triggerRequested = pyqtSignal()
    applySystemRequested = pyqtSignal()
    applyChannelsRequested = pyqtSignal()
    applyTriggerRequested = pyqtSignal()
    storeRequested = pyqtSignal(int, str)  # location, label
    recallRequested = pyqtSignal(int)  # location
    
    def __init__(self, parent=None, num_channels: int = 8):
        super().__init__(parent)
        self.num_channels = min(8, max(2, num_channels))
        self.channel_widgets: Dict[str, ChannelWidget] = {}
        self._setup_ui()
    
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(6, 6, 6, 6)
        
        # Title and connection
        title_layout = QHBoxLayout()
        title = QLabel("BNC 575 Digital Delay/Pulse Generator")
        title.setStyleSheet("font-size: 14pt; font-weight: bold;")
        title_layout.addWidget(title)
        title_layout.addStretch()
        
        # Connection controls
        self.port_edit = QLineEdit("COM1")
        self.port_edit.setMaximumWidth(80)
        title_layout.addWidget(QLabel("Port:"))
        title_layout.addWidget(self.port_edit)
        
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["115200", "57600", "38400", "19200", "9600", "4800"])
        self.baud_combo.setMaximumWidth(80)
        title_layout.addWidget(QLabel("Baud:"))
        title_layout.addWidget(self.baud_combo)
        
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.connectRequested.emit)
        title_layout.addWidget(self.connect_btn)
        
        main_layout.addLayout(title_layout)
        
        # Run/Stop controls
        control_layout = QHBoxLayout()
        
        self.run_btn = QPushButton("▶ RUN")
        self.run_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 8px 16px;")
        self.run_btn.clicked.connect(self.runRequested.emit)
        control_layout.addWidget(self.run_btn)
        
        self.stop_btn = QPushButton("■ STOP")
        self.stop_btn.setStyleSheet("background-color: #f44336; color: white; font-weight: bold; padding: 8px 16px;")
        self.stop_btn.clicked.connect(self.stopRequested.emit)
        control_layout.addWidget(self.stop_btn)
        
        self.trigger_btn = QPushButton("⚡ TRIGGER")
        self.trigger_btn.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold; padding: 8px 16px;")
        self.trigger_btn.clicked.connect(self.triggerRequested.emit)
        control_layout.addWidget(self.trigger_btn)
        
        self.arm_btn = QPushButton("ARM")
        self.arm_btn.setStyleSheet("padding: 8px 16px;")
        control_layout.addWidget(self.arm_btn)
        
        control_layout.addStretch()
        
        # Status indicator
        self.status_label = QLabel("● Disconnected")
        self.status_label.setStyleSheet("color: gray; font-weight: bold;")
        control_layout.addWidget(self.status_label)
        
        main_layout.addLayout(control_layout)
        
        # Tab widget
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # Create tabs
        self._create_system_tab()
        self._create_channels_tab()
        self._create_trigger_gate_tab()
        self._create_store_recall_tab()
    
    def _create_system_tab(self):
        """Create System configuration tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)
        
        # System Mode
        mode_group = QGroupBox("System Mode")
        mode_layout = QGridLayout(mode_group)
        
        mode_layout.addWidget(QLabel("Mode:"), 0, 0)
        self.system_mode = QComboBox()
        self.system_mode.addItems(["Continuous", "Single Shot", "Burst", "Duty Cycle"])
        mode_layout.addWidget(self.system_mode, 0, 1)
        
        mode_layout.addWidget(QLabel("Burst Count:"), 0, 2)
        self.sys_burst_spin = QSpinBox()
        self.sys_burst_spin.setRange(1, 9999999)
        self.sys_burst_spin.setValue(1)
        mode_layout.addWidget(self.sys_burst_spin, 0, 3)
        
        mode_layout.addWidget(QLabel("On Count:"), 1, 0)
        self.sys_on_spin = QSpinBox()
        self.sys_on_spin.setRange(1, 9999999)
        self.sys_on_spin.setValue(1)
        mode_layout.addWidget(self.sys_on_spin, 1, 1)
        
        mode_layout.addWidget(QLabel("Off Count:"), 1, 2)
        self.sys_off_spin = QSpinBox()
        self.sys_off_spin.setRange(1, 9999999)
        self.sys_off_spin.setValue(1)
        mode_layout.addWidget(self.sys_off_spin, 1, 3)
        
        layout.addWidget(mode_group)
        
        # Rate/Period
        rate_group = QGroupBox("Rate / Period")
        rate_layout = QGridLayout(rate_group)
        
        rate_layout.addWidget(QLabel("Period:"), 0, 0)
        self.period_edit = QLineEdit("1")
        self.period_edit.setMaximumWidth(120)
        rate_layout.addWidget(self.period_edit, 0, 1)
        self.period_unit = QComboBox()
        for unit in TimeUnit:
            self.period_unit.addItem(unit.symbol, unit)
        self.period_unit.setCurrentText("ms")
        rate_layout.addWidget(self.period_unit, 0, 2)
        
        rate_layout.addWidget(QLabel("Frequency:"), 1, 0)
        self.freq_edit = QLineEdit("1000")
        self.freq_edit.setMaximumWidth(120)
        rate_layout.addWidget(self.freq_edit, 1, 1)
        self.freq_unit = QComboBox()
        for unit in FreqUnit:
            self.freq_unit.addItem(unit.symbol, unit)
        self.freq_unit.setCurrentText("Hz")
        rate_layout.addWidget(self.freq_unit, 1, 2)
        
        # Sync period and frequency
        self.period_edit.editingFinished.connect(self._period_changed)
        self.freq_edit.editingFinished.connect(self._freq_changed)
        
        layout.addWidget(rate_group)
        
        # Clock source
        clock_group = QGroupBox("Clock Source")
        clock_layout = QGridLayout(clock_group)
        
        clock_layout.addWidget(QLabel("Source:"), 0, 0)
        self.clock_source = QComboBox()
        self.clock_source.addItems(["System", "Ext 10MHz", "Ext 20MHz", "Ext 25MHz",
                                    "Ext 40MHz", "Ext 50MHz", "Ext 80MHz", "Ext 100MHz"])
        clock_layout.addWidget(self.clock_source, 0, 1)
        
        clock_layout.addWidget(QLabel("Ref Out:"), 0, 2)
        self.ref_output = QComboBox()
        self.ref_output.addItems(["T0 Pulse", "100MHz", "50MHz", "33MHz", "25MHz",
                                  "20MHz", "16MHz", "14MHz", "12MHz", "11MHz", "10MHz"])
        clock_layout.addWidget(self.ref_output, 0, 3)
        
        layout.addWidget(clock_group)
        
        # Apply button
        apply_layout = QHBoxLayout()
        apply_layout.addStretch()
        apply_btn = QPushButton("Apply System Settings")
        apply_btn.clicked.connect(self.applySystemRequested.emit)
        apply_layout.addWidget(apply_btn)
        layout.addLayout(apply_layout)
        
        layout.addStretch()
        self.tabs.addTab(tab, "System")
    
    def _create_channels_tab(self):
        """Create Channels configuration tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Channel sub-tabs
        channel_tabs = QTabWidget()
        
        channel_names = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'][:self.num_channels]
        
        for name in channel_names:
            channel_widget = ChannelWidget(name)
            self.channel_widgets[name] = channel_widget
            
            # Wrap in scroll area for smaller screens
            scroll = QScrollArea()
            scroll.setWidget(channel_widget)
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            
            channel_tabs.addTab(scroll, f"Ch {name}")
        
        layout.addWidget(channel_tabs)
        
        # Apply button
        apply_layout = QHBoxLayout()
        apply_layout.addStretch()
        
        enable_all_btn = QPushButton("Enable All")
        enable_all_btn.clicked.connect(self._enable_all_channels)
        apply_layout.addWidget(enable_all_btn)
        
        disable_all_btn = QPushButton("Disable All")
        disable_all_btn.clicked.connect(self._disable_all_channels)
        apply_layout.addWidget(disable_all_btn)
        
        apply_btn = QPushButton("Apply Channel Settings")
        apply_btn.clicked.connect(self.applyChannelsRequested.emit)
        apply_layout.addWidget(apply_btn)
        
        layout.addLayout(apply_layout)
        
        self.tabs.addTab(tab, "Channels")
    
    def _create_trigger_gate_tab(self):
        """Create Trigger/Gate configuration tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Trigger section
        trig_group = QGroupBox("Trigger Input")
        trig_layout = QGridLayout(trig_group)
        
        trig_layout.addWidget(QLabel("Mode:"), 0, 0)
        self.trig_mode = QComboBox()
        self.trig_mode.addItems(["Disabled", "Triggered", "Dual Trigger"])
        trig_layout.addWidget(self.trig_mode, 0, 1)
        
        trig_layout.addWidget(QLabel("Edge:"), 0, 2)
        self.trig_edge = QComboBox()
        self.trig_edge.addItems(["Rising", "Falling"])
        trig_layout.addWidget(self.trig_edge, 0, 3)
        
        trig_layout.addWidget(QLabel("Level:"), 1, 0)
        self.trig_level = QDoubleSpinBox()
        self.trig_level.setRange(0.20, 15.0)
        self.trig_level.setValue(2.5)
        self.trig_level.setSuffix(" V")
        self.trig_level.setDecimals(2)
        trig_layout.addWidget(self.trig_level, 1, 1)
        
        layout.addWidget(trig_group)
        
        # Gate section
        gate_group = QGroupBox("Gate Input")
        gate_layout = QGridLayout(gate_group)
        
        gate_layout.addWidget(QLabel("Mode:"), 0, 0)
        self.gate_mode = QComboBox()
        self.gate_mode.addItems(["Disabled", "Pulse Inhibit", "Output Inhibit", "Per Channel"])
        gate_layout.addWidget(self.gate_mode, 0, 1)
        
        gate_layout.addWidget(QLabel("Logic:"), 0, 2)
        self.gate_logic = QComboBox()
        self.gate_logic.addItems(["Active High", "Active Low"])
        gate_layout.addWidget(self.gate_logic, 0, 3)
        
        gate_layout.addWidget(QLabel("Level:"), 1, 0)
        self.gate_level = QDoubleSpinBox()
        self.gate_level.setRange(0.20, 15.0)
        self.gate_level.setValue(2.5)
        self.gate_level.setSuffix(" V")
        self.gate_level.setDecimals(2)
        gate_layout.addWidget(self.gate_level, 1, 1)
        
        layout.addWidget(gate_group)
        
        # Apply button
        apply_layout = QHBoxLayout()
        apply_layout.addStretch()
        apply_btn = QPushButton("Apply Trigger/Gate Settings")
        apply_btn.clicked.connect(self.applyTriggerRequested.emit)
        apply_layout.addWidget(apply_btn)
        layout.addLayout(apply_layout)
        
        layout.addStretch()
        self.tabs.addTab(tab, "Trigger/Gate")
    
    def _create_store_recall_tab(self):
        """Create Store/Recall configuration tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Store section
        store_group = QGroupBox("Store Configuration")
        store_layout = QGridLayout(store_group)
        
        store_layout.addWidget(QLabel("Location:"), 0, 0)
        self.store_location = QSpinBox()
        self.store_location.setRange(1, 12)
        self.store_location.setValue(1)
        store_layout.addWidget(self.store_location, 0, 1)
        
        store_layout.addWidget(QLabel("Label:"), 0, 2)
        self.store_label = QLineEdit()
        self.store_label.setMaxLength(14)
        self.store_label.setPlaceholderText("Optional (14 chars max)")
        store_layout.addWidget(self.store_label, 0, 3)
        
        store_btn = QPushButton("Store")
        store_btn.clicked.connect(self._on_store_clicked)
        store_layout.addWidget(store_btn, 0, 4)
        
        layout.addWidget(store_group)
        
        # Recall section
        recall_group = QGroupBox("Recall Configuration")
        recall_layout = QGridLayout(recall_group)
        
        recall_layout.addWidget(QLabel("Location:"), 0, 0)
        self.recall_location = QSpinBox()
        self.recall_location.setRange(0, 12)
        self.recall_location.setValue(0)
        recall_layout.addWidget(self.recall_location, 0, 1)
        
        recall_layout.addWidget(QLabel("(0 = Factory Default)"), 0, 2)
        
        recall_btn = QPushButton("Recall")
        recall_btn.clicked.connect(self._on_recall_clicked)
        recall_layout.addWidget(recall_btn, 0, 3)
        
        layout.addWidget(recall_group)
        
        # Quick recall buttons
        quick_group = QGroupBox("Quick Recall")
        quick_layout = QGridLayout(quick_group)
        
        for i in range(13):
            row = i // 5
            col = i % 5
            btn = QPushButton(f"{i}" if i > 0 else "Default")
            btn.clicked.connect(lambda checked, loc=i: self.recallRequested.emit(loc))
            quick_layout.addWidget(btn, row, col)
        
        layout.addWidget(quick_group)
        
        layout.addStretch()
        self.tabs.addTab(tab, "Store/Recall")
    
    # ========== Private Methods ==========
    
    def _period_changed(self):
        """Update frequency when period changes"""
        try:
            value = float(self.period_edit.text())
            unit = self.period_unit.currentData()
            period_s = value * unit.factor
            if period_s > 0:
                freq_hz = 1.0 / period_s
                freq_unit = self.freq_unit.currentData()
                self.freq_edit.setText(f"{freq_hz / freq_unit.factor:.6g}")
        except (ValueError, ZeroDivisionError):
            pass
    
    def _freq_changed(self):
        """Update period when frequency changes"""
        try:
            value = float(self.freq_edit.text())
            unit = self.freq_unit.currentData()
            freq_hz = value * unit.factor
            if freq_hz > 0:
                period_s = 1.0 / freq_hz
                period_unit = self.period_unit.currentData()
                self.period_edit.setText(f"{period_s / period_unit.factor:.6g}")
        except (ValueError, ZeroDivisionError):
            pass
    
    def _enable_all_channels(self):
        """Enable all channels"""
        for widget in self.channel_widgets.values():
            widget.set_enabled(True)
    
    def _disable_all_channels(self):
        """Disable all channels"""
        for widget in self.channel_widgets.values():
            widget.set_enabled(False)
    
    def _on_store_clicked(self):
        """Handle store button click"""
        location = self.store_location.value()
        label = self.store_label.text()
        self.storeRequested.emit(location, label)
    
    def _on_recall_clicked(self):
        """Handle recall button click"""
        location = self.recall_location.value()
        self.recallRequested.emit(location)
    
    # ========== Public Interface ==========
    
    def set_connected(self, connected: bool):
        """Update UI to reflect connection state"""
        if connected:
            self.status_label.setText("● Connected")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
            self.connect_btn.setText("Disconnect")
        else:
            self.status_label.setText("● Disconnected")
            self.status_label.setStyleSheet("color: gray; font-weight: bold;")
            self.connect_btn.setText("Connect")
    
    def set_running(self, running: bool):
        """Update UI to reflect running state"""
        if running:
            self.status_label.setText("● Running")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.status_label.setText("● Stopped")
            self.status_label.setStyleSheet("color: orange; font-weight: bold;")
    
    def get_port(self) -> str:
        """Get selected port"""
        return self.port_edit.text()
    
    def get_baudrate(self) -> int:
        """Get selected baud rate"""
        return int(self.baud_combo.currentText())
    
    def get_period_seconds(self) -> float:
        """Get T0 period in seconds"""
        try:
            value = float(self.period_edit.text())
            unit = self.period_unit.currentData()
            return value * unit.factor
        except (ValueError, AttributeError):
            return 0.001
    
    def get_frequency_hz(self) -> float:
        """Get frequency in Hz"""
        try:
            value = float(self.freq_edit.text())
            unit = self.freq_unit.currentData()
            return value * unit.factor
        except (ValueError, AttributeError):
            return 1000.0
    
    def get_system_mode(self) -> str:
        """Get system mode string"""
        return self.system_mode.currentText()
    
    def get_trigger_mode(self) -> str:
        """Get trigger mode string"""
        return self.trig_mode.currentText()
    
    def get_trigger_level(self) -> float:
        """Get trigger level in volts"""
        return self.trig_level.value()
    
    def get_trigger_edge(self) -> str:
        """Get trigger edge string"""
        return self.trig_edge.currentText()
    
    def get_gate_mode(self) -> str:
        """Get gate mode string"""
        return self.gate_mode.currentText()
    
    def get_gate_level(self) -> float:
        """Get gate level in volts"""
        return self.gate_level.value()
    
    def get_gate_logic(self) -> str:
        """Get gate logic string"""
        return self.gate_logic.currentText()
    
    # ========== Backward Compatible Channel Access Methods ==========
    
    def get_delayA(self) -> float:
        """Get Channel A delay in seconds (backward compatible)"""
        if 'A' in self.channel_widgets:
            return self.channel_widgets['A'].get_delay_seconds()
        return 0.0
    
    def get_delayB(self) -> float:
        """Get Channel B delay in seconds (backward compatible)"""
        if 'B' in self.channel_widgets:
            return self.channel_widgets['B'].get_delay_seconds()
        return 0.0
    
    def get_delayC(self) -> float:
        """Get Channel C delay in seconds (backward compatible)"""
        if 'C' in self.channel_widgets:
            return self.channel_widgets['C'].get_delay_seconds()
        return 0.0
    
    def get_delayD(self) -> float:
        """Get Channel D delay in seconds (backward compatible)"""
        if 'D' in self.channel_widgets:
            return self.channel_widgets['D'].get_delay_seconds()
        return 0.0
    
    def get_delayE(self) -> float:
        """Get Channel E delay in seconds"""
        if 'E' in self.channel_widgets:
            return self.channel_widgets['E'].get_delay_seconds()
        return 0.0
    
    def get_delayF(self) -> float:
        """Get Channel F delay in seconds"""
        if 'F' in self.channel_widgets:
            return self.channel_widgets['F'].get_delay_seconds()
        return 0.0
    
    def get_delayG(self) -> float:
        """Get Channel G delay in seconds"""
        if 'G' in self.channel_widgets:
            return self.channel_widgets['G'].get_delay_seconds()
        return 0.0
    
    def get_delayH(self) -> float:
        """Get Channel H delay in seconds"""
        if 'H' in self.channel_widgets:
            return self.channel_widgets['H'].get_delay_seconds()
        return 0.0
    
    def get_widthA(self) -> float:
        """Get Channel A width in seconds (backward compatible)"""
        if 'A' in self.channel_widgets:
            return self.channel_widgets['A'].get_width_seconds()
        return 100e-9
    
    def get_widthB(self) -> float:
        """Get Channel B width in seconds (backward compatible)"""
        if 'B' in self.channel_widgets:
            return self.channel_widgets['B'].get_width_seconds()
        return 100e-9
    
    def get_widthC(self) -> float:
        """Get Channel C width in seconds (backward compatible)"""
        if 'C' in self.channel_widgets:
            return self.channel_widgets['C'].get_width_seconds()
        return 100e-9
    
    def get_widthD(self) -> float:
        """Get Channel D width in seconds (backward compatible)"""
        if 'D' in self.channel_widgets:
            return self.channel_widgets['D'].get_width_seconds()
        return 100e-9
    
    def get_widthE(self) -> float:
        """Get Channel E width in seconds"""
        if 'E' in self.channel_widgets:
            return self.channel_widgets['E'].get_width_seconds()
        return 100e-9
    
    def get_widthF(self) -> float:
        """Get Channel F width in seconds"""
        if 'F' in self.channel_widgets:
            return self.channel_widgets['F'].get_width_seconds()
        return 100e-9
    
    def get_widthG(self) -> float:
        """Get Channel G width in seconds"""
        if 'G' in self.channel_widgets:
            return self.channel_widgets['G'].get_width_seconds()
        return 100e-9
    
    def get_widthH(self) -> float:
        """Get Channel H width in seconds"""
        if 'H' in self.channel_widgets:
            return self.channel_widgets['H'].get_width_seconds()
        return 100e-9
    
    def get_channel_enabled(self, channel: str) -> bool:
        """Get channel enabled state"""
        if channel in self.channel_widgets:
            return self.channel_widgets[channel].is_enabled()
        return False
    
    def set_channel_enabled(self, channel: str, enabled: bool):
        """Set channel enabled state"""
        if channel in self.channel_widgets:
            self.channel_widgets[channel].set_enabled(enabled)
    
    def get_channel_delay(self, channel: str) -> float:
        """Get channel delay in seconds"""
        if channel in self.channel_widgets:
            return self.channel_widgets[channel].get_delay_seconds()
        return 0.0
    
    def set_channel_delay(self, channel: str, delay: float):
        """Set channel delay in seconds"""
        if channel in self.channel_widgets:
            self.channel_widgets[channel].set_delay_seconds(delay)
    
    def get_channel_width(self, channel: str) -> float:
        """Get channel width in seconds"""
        if channel in self.channel_widgets:
            return self.channel_widgets[channel].get_width_seconds()
        return 100e-9
    
    def set_channel_width(self, channel: str, width: float):
        """Set channel width in seconds"""
        if channel in self.channel_widgets:
            self.channel_widgets[channel].set_width_seconds(width)


# Example usage
if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    
    # Create panel (8-channel version)
    panel = BNC575Panel(num_channels=8)
    panel.setWindowTitle("BNC 575 Control Panel")
    panel.resize(700, 600)
    panel.show()
    
    # Demonstrate backward compatible methods
    print("Testing backward compatible methods:")
    print(f"  get_delayA(): {panel.get_delayA()}")
    print(f"  get_widthA(): {panel.get_widthA()}")
    print(f"  get_period_seconds(): {panel.get_period_seconds()}")
    print(f"  get_frequency_hz(): {panel.get_frequency_hz()}")
    
    sys.exit(app.exec())
