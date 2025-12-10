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

Designed to work with main_window.py and provide full device control.

Features:
- 4 channel timing configuration (A, B, C, D) with unit selectors
- System mode selection (Continuous, Single Shot, Burst, Duty Cycle)
- Trigger configuration (INT/EXT, level, edge)
- Gate configuration
- Period/Frequency control
- Channel enable/disable
- Store/Recall configurations
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QComboBox, QDoubleSpinBox,
    QSpinBox, QCheckBox, QTabWidget, QFrame, QSizePolicy,
    QButtonGroup, QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from typing import Optional

# Try to import StatusLamp from utils
try:
    from utils.status_lamp import StatusLamp
except ImportError:
    class StatusLamp(QLabel):
        def __init__(self):
            super().__init__("●")
            self.setStyleSheet("font-size: 14pt;")
        def set_status(self, color: str, text: str):
            colors = {"green": "#00ff00", "red": "#ff0000", "yellow": "#ffff00", "gray": "#888888"}
            self.setStyleSheet(f"color: {colors.get(color, '#888888')}; font-size: 14pt;")
            self.setToolTip(text)


class UnitSelector(QWidget):
    """Time unit selector with buttons"""
    
    unitChanged = pyqtSignal()
    
    # Units: (label, multiplier to seconds)
    UNITS = [
        ("s", 1.0),
        ("ms", 1e-3),
        ("µs", 1e-6),
        ("ns", 1e-9),
    ]
    
    def __init__(self, default_unit: str = "µs", parent=None):
        super().__init__(parent)
        self._multiplier = 1e-6
        self._setup_ui(default_unit)
    
    def _setup_ui(self, default_unit: str):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        
        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)
        
        for i, (label, mult) in enumerate(self.UNITS):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedSize(28, 22)
            btn.setStyleSheet("""
                QPushButton { 
                    padding: 1px; 
                    font-size: 8pt;
                    border: 1px solid #888;
                    border-radius: 2px;
                }
                QPushButton:checked { 
                    background-color: #4CAF50; 
                    color: white;
                    border: 1px solid #388E3C;
                }
            """)
            btn.clicked.connect(lambda checked, m=mult: self._on_click(m))
            self.btn_group.addButton(btn, i)
            layout.addWidget(btn)
            
            if label == default_unit:
                btn.setChecked(True)
                self._multiplier = mult
    
    def _on_click(self, mult: float):
        self._multiplier = mult
        self.unitChanged.emit()
    
    def get_multiplier(self) -> float:
        return self._multiplier
    
    def set_unit(self, unit: str):
        """Set unit by name"""
        for i, (label, mult) in enumerate(self.UNITS):
            if label == unit:
                btn = self.btn_group.button(i)
                if btn:
                    btn.setChecked(True)
                    self._multiplier = mult
                break


class FreqUnitSelector(QWidget):
    """Frequency unit selector"""
    
    unitChanged = pyqtSignal()
    
    UNITS = [
        ("Hz", 1.0),
        ("kHz", 1e3),
        ("MHz", 1e6),
    ]
    
    def __init__(self, default_unit: str = "Hz", parent=None):
        super().__init__(parent)
        self._multiplier = 1.0
        self._setup_ui(default_unit)
    
    def _setup_ui(self, default_unit: str):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        
        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)
        
        for i, (label, mult) in enumerate(self.UNITS):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedSize(32, 22)
            btn.setStyleSheet("""
                QPushButton { padding: 1px; font-size: 8pt; border: 1px solid #888; border-radius: 2px; }
                QPushButton:checked { background-color: #2196F3; color: white; border: 1px solid #1976D2; }
            """)
            btn.clicked.connect(lambda checked, m=mult: self._on_click(m))
            self.btn_group.addButton(btn, i)
            layout.addWidget(btn)
            
            if label == default_unit:
                btn.setChecked(True)
                self._multiplier = mult
    
    def _on_click(self, mult: float):
        self._multiplier = mult
        self.unitChanged.emit()
    
    def get_multiplier(self) -> float:
        return self._multiplier


class BNC575Panel(QWidget):
    """
    Complete GUI Panel for BNC 575 Pulse Generator
    
    Provides:
    - Direct widget access: widthA, delayA, widthB, delayB, etc.
    - get_widthA(), get_delayA() etc. methods returning seconds
    - Trigger/gate configuration
    - System mode and period control
    - Channel enable toggles
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(4)
        main_layout.setContentsMargins(4, 4, 4, 4)
        
        # ========== HEADER ==========
        header = QHBoxLayout()
        title = QLabel("BNC 575 Pulse Generator")
        title.setStyleSheet("font-weight: bold; font-size: 11pt;")
        header.addWidget(title)
        header.addStretch()
        self.lamp = StatusLamp()
        self.lamp.set_status("red", "Not Connected")
        header.addWidget(self.lamp)
        main_layout.addLayout(header)
        
        # ========== CONNECTION BUTTONS ==========
        conn_layout = QHBoxLayout()
        self.btn_connect = QPushButton("Connect")
        self.btn_disconnect = QPushButton("Disconnect")
        self.btn_fire = QPushButton("Fire (INT)")
        self.btn_fire.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold;")
        conn_layout.addWidget(self.btn_connect)
        conn_layout.addWidget(self.btn_disconnect)
        conn_layout.addWidget(self.btn_fire)
        conn_layout.addStretch()
        main_layout.addLayout(conn_layout)
        
        # ========== TABS ==========
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # Create tabs
        self._create_timing_tab()
        self._create_system_tab()
        self._create_trigger_tab()
        self._create_advanced_tab()
    
    def _create_timing_tab(self):
        """Channel timing configuration"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(4)
        
        # Channel timing group
        timing_group = QGroupBox("Channel Timing (Width / Delay)")
        timing_layout = QGridLayout(timing_group)
        timing_layout.setSpacing(4)
        
        # Headers
        timing_layout.addWidget(QLabel("Ch"), 0, 0)
        timing_layout.addWidget(QLabel("Width"), 0, 1)
        timing_layout.addWidget(QLabel("Unit"), 0, 2)
        timing_layout.addWidget(QLabel("Delay"), 0, 4)
        timing_layout.addWidget(QLabel("Unit"), 0, 5)
        timing_layout.addWidget(QLabel("En"), 0, 7)
        
        # Channel A
        timing_layout.addWidget(QLabel("A:"), 1, 0)
        self.widthA = QDoubleSpinBox()
        self.widthA.setRange(0, 999999)
        self.widthA.setDecimals(3)
        self.widthA.setValue(1.0)
        self.widthA.setFixedWidth(80)
        timing_layout.addWidget(self.widthA, 1, 1)
        self.widthA_unit = UnitSelector("µs")
        timing_layout.addWidget(self.widthA_unit, 1, 2)
        timing_layout.addWidget(QLabel(""), 1, 3)  # spacer
        self.delayA = QDoubleSpinBox()
        self.delayA.setRange(-999999, 999999)
        self.delayA.setDecimals(3)
        self.delayA.setValue(0.0)
        self.delayA.setFixedWidth(80)
        timing_layout.addWidget(self.delayA, 1, 4)
        self.delayA_unit = UnitSelector("µs")
        timing_layout.addWidget(self.delayA_unit, 1, 5)
        timing_layout.addWidget(QLabel(""), 1, 6)  # spacer
        self.btn_en_a = QPushButton("A")
        self.btn_en_a.setCheckable(True)
        self.btn_en_a.setChecked(True)
        self.btn_en_a.setFixedWidth(30)
        self._style_enable_btn(self.btn_en_a)
        timing_layout.addWidget(self.btn_en_a, 1, 7)
        
        # Channel B
        timing_layout.addWidget(QLabel("B:"), 2, 0)
        self.widthB = QDoubleSpinBox()
        self.widthB.setRange(0, 999999)
        self.widthB.setDecimals(3)
        self.widthB.setValue(1.0)
        self.widthB.setFixedWidth(80)
        timing_layout.addWidget(self.widthB, 2, 1)
        self.widthB_unit = UnitSelector("µs")
        timing_layout.addWidget(self.widthB_unit, 2, 2)
        self.delayB = QDoubleSpinBox()
        self.delayB.setRange(-999999, 999999)
        self.delayB.setDecimals(3)
        self.delayB.setValue(0.0)
        self.delayB.setFixedWidth(80)
        timing_layout.addWidget(self.delayB, 2, 4)
        self.delayB_unit = UnitSelector("µs")
        timing_layout.addWidget(self.delayB_unit, 2, 5)
        self.btn_en_b = QPushButton("B")
        self.btn_en_b.setCheckable(True)
        self.btn_en_b.setChecked(True)
        self.btn_en_b.setFixedWidth(30)
        self._style_enable_btn(self.btn_en_b)
        timing_layout.addWidget(self.btn_en_b, 2, 7)
        
        # Channel C
        timing_layout.addWidget(QLabel("C:"), 3, 0)
        self.widthC = QDoubleSpinBox()
        self.widthC.setRange(0, 999999)
        self.widthC.setDecimals(3)
        self.widthC.setValue(40.0)
        self.widthC.setFixedWidth(80)
        timing_layout.addWidget(self.widthC, 3, 1)
        self.widthC_unit = UnitSelector("µs")
        timing_layout.addWidget(self.widthC_unit, 3, 2)
        self.delayC = QDoubleSpinBox()
        self.delayC.setRange(-999999, 999999)
        self.delayC.setDecimals(3)
        self.delayC.setValue(0.0)
        self.delayC.setFixedWidth(80)
        timing_layout.addWidget(self.delayC, 3, 4)
        self.delayC_unit = UnitSelector("µs")
        timing_layout.addWidget(self.delayC_unit, 3, 5)
        self.btn_en_c = QPushButton("C")
        self.btn_en_c.setCheckable(True)
        self.btn_en_c.setChecked(True)
        self.btn_en_c.setFixedWidth(30)
        self._style_enable_btn(self.btn_en_c)
        timing_layout.addWidget(self.btn_en_c, 3, 7)
        
        # Channel D
        timing_layout.addWidget(QLabel("D:"), 4, 0)
        self.widthD = QDoubleSpinBox()
        self.widthD.setRange(0, 999999)
        self.widthD.setDecimals(3)
        self.widthD.setValue(40.0)
        self.widthD.setFixedWidth(80)
        timing_layout.addWidget(self.widthD, 4, 1)
        self.widthD_unit = UnitSelector("µs")
        timing_layout.addWidget(self.widthD_unit, 4, 2)
        self.delayD = QDoubleSpinBox()
        self.delayD.setRange(-999999, 999999)
        self.delayD.setDecimals(3)
        self.delayD.setValue(0.0)
        self.delayD.setFixedWidth(80)
        timing_layout.addWidget(self.delayD, 4, 4)
        self.delayD_unit = UnitSelector("µs")
        timing_layout.addWidget(self.delayD_unit, 4, 5)
        self.btn_en_d = QPushButton("D")
        self.btn_en_d.setCheckable(True)
        self.btn_en_d.setChecked(True)
        self.btn_en_d.setFixedWidth(30)
        self._style_enable_btn(self.btn_en_d)
        timing_layout.addWidget(self.btn_en_d, 4, 7)
        
        layout.addWidget(timing_group)
        
        # Apply/Read buttons
        btn_layout = QHBoxLayout()
        self.btn_apply = QPushButton("Apply Settings")
        self.btn_apply.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 6px;")
        self.btn_read = QPushButton("Read Settings")
        self.btn_read.setStyleSheet("padding: 6px;")
        btn_layout.addWidget(self.btn_apply)
        btn_layout.addWidget(self.btn_read)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        layout.addStretch()
        self.tabs.addTab(tab, "Timing")
    
    def _create_system_tab(self):
        """System mode and rate configuration"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # System Mode
        mode_group = QGroupBox("System Mode")
        mode_layout = QGridLayout(mode_group)
        
        mode_layout.addWidget(QLabel("Mode:"), 0, 0)
        self.system_mode = QComboBox()
        self.system_mode.addItems(["Continuous", "Single Shot", "Burst", "Duty Cycle"])
        mode_layout.addWidget(self.system_mode, 0, 1)
        
        mode_layout.addWidget(QLabel("Burst Count:"), 0, 2)
        self.burst_count = QSpinBox()
        self.burst_count.setRange(1, 9999999)
        self.burst_count.setValue(1)
        mode_layout.addWidget(self.burst_count, 0, 3)
        
        mode_layout.addWidget(QLabel("On Count:"), 1, 0)
        self.on_count = QSpinBox()
        self.on_count.setRange(1, 9999999)
        self.on_count.setValue(1)
        mode_layout.addWidget(self.on_count, 1, 1)
        
        mode_layout.addWidget(QLabel("Off Count:"), 1, 2)
        self.off_count = QSpinBox()
        self.off_count.setRange(1, 9999999)
        self.off_count.setValue(1)
        mode_layout.addWidget(self.off_count, 1, 3)
        
        layout.addWidget(mode_group)
        
        # Rate/Period
        rate_group = QGroupBox("Rate / Period (T₀)")
        rate_layout = QGridLayout(rate_group)
        
        rate_layout.addWidget(QLabel("Period:"), 0, 0)
        self.period = QDoubleSpinBox()
        self.period.setRange(0.0001, 999999)
        self.period.setDecimals(4)
        self.period.setValue(1.0)
        self.period.setFixedWidth(100)
        rate_layout.addWidget(self.period, 0, 1)
        self.period_unit = UnitSelector("ms")
        rate_layout.addWidget(self.period_unit, 0, 2)
        
        rate_layout.addWidget(QLabel("Frequency:"), 1, 0)
        self.frequency = QDoubleSpinBox()
        self.frequency.setRange(0.0001, 20000000)
        self.frequency.setDecimals(2)
        self.frequency.setValue(1000.0)
        self.frequency.setFixedWidth(100)
        rate_layout.addWidget(self.frequency, 1, 1)
        self.freq_unit = FreqUnitSelector("Hz")
        rate_layout.addWidget(self.freq_unit, 1, 2)
        
        # Sync period/freq
        self.period.valueChanged.connect(self._period_changed)
        self.frequency.valueChanged.connect(self._freq_changed)
        self.period_unit.unitChanged.connect(self._period_changed)
        self.freq_unit.unitChanged.connect(self._freq_changed)
        
        layout.addWidget(rate_group)
        
        # Clock source
        clock_group = QGroupBox("Clock Source")
        clock_layout = QHBoxLayout(clock_group)
        clock_layout.addWidget(QLabel("Source:"))
        self.clock_source = QComboBox()
        self.clock_source.addItems(["System", "Ext 10MHz", "Ext 20MHz", "Ext 25MHz",
                                    "Ext 40MHz", "Ext 50MHz", "Ext 80MHz", "Ext 100MHz"])
        clock_layout.addWidget(self.clock_source)
        clock_layout.addStretch()
        layout.addWidget(clock_group)
        
        # Apply button
        self.btn_apply_system = QPushButton("Apply System Settings")
        self.btn_apply_system.setStyleSheet("background-color: #2196F3; color: white; padding: 6px;")
        layout.addWidget(self.btn_apply_system)
        
        layout.addStretch()
        self.tabs.addTab(tab, "System")
    
    def _create_trigger_tab(self):
        """Trigger and gate configuration"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Trigger
        trig_group = QGroupBox("Trigger Configuration")
        trig_layout = QGridLayout(trig_group)
        
        trig_layout.addWidget(QLabel("Source:"), 0, 0)
        self.trig_source = QComboBox()
        self.trig_source.addItems(["INT", "EXT"])
        trig_layout.addWidget(self.trig_source, 0, 1)
        
        trig_layout.addWidget(QLabel("Slope:"), 0, 2)
        self.trig_slope = QComboBox()
        self.trig_slope.addItems(["POS", "NEG"])
        trig_layout.addWidget(self.trig_slope, 0, 3)
        
        trig_layout.addWidget(QLabel("Level:"), 1, 0)
        self.trig_level = QDoubleSpinBox()
        self.trig_level.setRange(0.20, 15.0)
        self.trig_level.setValue(2.5)
        self.trig_level.setSuffix(" V")
        self.trig_level.setDecimals(2)
        trig_layout.addWidget(self.trig_level, 1, 1)
        
        # Enable trigger checkbox
        self.btn_en_trig = QPushButton("Enable Ext Trigger")
        self.btn_en_trig.setCheckable(True)
        self.btn_en_trig.setStyleSheet("""
            QPushButton { padding: 6px; }
            QPushButton:checked { background-color: #9C27B0; color: white; }
        """)
        trig_layout.addWidget(self.btn_en_trig, 1, 2, 1, 2)
        
        layout.addWidget(trig_group)
        
        # Trigger buttons
        trig_btn_layout = QHBoxLayout()
        self.btn_apply_trigger = QPushButton("Apply Trigger Settings")
        self.btn_arm = QPushButton("Arm (EXT TRIG)")
        self.btn_arm.setStyleSheet("background-color: #9C27B0; color: white; padding: 6px;")
        trig_btn_layout.addWidget(self.btn_apply_trigger)
        trig_btn_layout.addWidget(self.btn_arm)
        trig_btn_layout.addStretch()
        layout.addLayout(trig_btn_layout)
        
        # Gate
        gate_group = QGroupBox("Gate Configuration")
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
        gate_layout.addWidget(self.gate_level, 1, 1)
        
        layout.addWidget(gate_group)
        
        layout.addStretch()
        self.tabs.addTab(tab, "Trigger/Gate")
    
    def _create_advanced_tab(self):
        """Advanced settings: polarity, sync, store/recall"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Polarity
        pol_group = QGroupBox("Channel Polarity")
        pol_layout = QGridLayout(pol_group)
        
        for i, ch in enumerate(['A', 'B', 'C', 'D']):
            pol_layout.addWidget(QLabel(f"Ch {ch}:"), 0, i*2)
            combo = QComboBox()
            combo.addItems(["Normal", "Inverted"])
            setattr(self, f'polarity_{ch}', combo)
            pol_layout.addWidget(combo, 0, i*2+1)
        
        layout.addWidget(pol_group)
        
        # Sync source
        sync_group = QGroupBox("Channel Sync Source")
        sync_layout = QGridLayout(sync_group)
        
        for i, ch in enumerate(['A', 'B', 'C', 'D']):
            sync_layout.addWidget(QLabel(f"Ch {ch}:"), 0, i*2)
            combo = QComboBox()
            combo.addItems(["T0", "CHA", "CHB", "CHC", "CHD"])
            setattr(self, f'sync_{ch}', combo)
            sync_layout.addWidget(combo, 0, i*2+1)
        
        layout.addWidget(sync_group)
        
        # Output mode
        output_group = QGroupBox("Output Mode / Amplitude")
        output_layout = QGridLayout(output_group)
        
        for i, ch in enumerate(['A', 'B', 'C', 'D']):
            output_layout.addWidget(QLabel(f"Ch {ch}:"), i, 0)
            mode_combo = QComboBox()
            mode_combo.addItems(["TTL", "Adjustable"])
            setattr(self, f'output_mode_{ch}', mode_combo)
            output_layout.addWidget(mode_combo, i, 1)
            
            amp_spin = QDoubleSpinBox()
            amp_spin.setRange(2.0, 20.0)
            amp_spin.setValue(4.0)
            amp_spin.setSuffix(" V")
            amp_spin.setEnabled(False)  # Only for adjustable
            setattr(self, f'amplitude_{ch}', amp_spin)
            output_layout.addWidget(amp_spin, i, 2)
            
            # Connect to enable/disable amplitude
            mode_combo.currentTextChanged.connect(
                lambda text, spin=amp_spin: spin.setEnabled(text == "Adjustable")
            )
        
        layout.addWidget(output_group)
        
        # Store/Recall
        store_group = QGroupBox("Store / Recall Configuration")
        store_layout = QHBoxLayout(store_group)
        
        store_layout.addWidget(QLabel("Location:"))
        self.store_location = QSpinBox()
        self.store_location.setRange(1, 12)
        self.store_location.setValue(1)
        store_layout.addWidget(self.store_location)
        
        self.btn_store = QPushButton("Store")
        self.btn_recall = QPushButton("Recall")
        self.btn_factory = QPushButton("Factory Reset")
        self.btn_factory.setStyleSheet("background-color: #f44336; color: white;")
        
        store_layout.addWidget(self.btn_store)
        store_layout.addWidget(self.btn_recall)
        store_layout.addWidget(self.btn_factory)
        store_layout.addStretch()
        
        layout.addWidget(store_group)
        
        # Display settings
        disp_group = QGroupBox("Display Settings")
        disp_layout = QHBoxLayout(disp_group)
        
        disp_layout.addWidget(QLabel("Brightness:"))
        self.brightness = QSpinBox()
        self.brightness.setRange(0, 4)
        self.brightness.setValue(2)
        disp_layout.addWidget(self.brightness)
        
        self.display_enabled = QCheckBox("Display On")
        self.display_enabled.setChecked(True)
        disp_layout.addWidget(self.display_enabled)
        
        self.keylock = QCheckBox("Keylock")
        disp_layout.addWidget(self.keylock)
        
        disp_layout.addStretch()
        layout.addWidget(disp_group)
        
        layout.addStretch()
        self.tabs.addTab(tab, "Advanced")
    
    def _style_enable_btn(self, btn: QPushButton):
        """Style channel enable button"""
        btn.setStyleSheet("""
            QPushButton { 
                padding: 2px; 
                border: 1px solid #888;
                border-radius: 3px;
            }
            QPushButton:checked { 
                background-color: #4CAF50; 
                color: white;
                border: 1px solid #388E3C;
            }
        """)
    
    def _period_changed(self):
        """Update frequency when period changes"""
        try:
            period_s = self.period.value() * self.period_unit.get_multiplier()
            if period_s > 0:
                freq = 1.0 / period_s
                freq_mult = self.freq_unit.get_multiplier()
                self.frequency.blockSignals(True)
                self.frequency.setValue(freq / freq_mult)
                self.frequency.blockSignals(False)
        except:
            pass
    
    def _freq_changed(self):
        """Update period when frequency changes"""
        try:
            freq = self.frequency.value() * self.freq_unit.get_multiplier()
            if freq > 0:
                period = 1.0 / freq
                period_mult = self.period_unit.get_multiplier()
                self.period.blockSignals(True)
                self.period.setValue(period / period_mult)
                self.period.blockSignals(False)
        except:
            pass
    
    # ==================== GETTER METHODS (return seconds) ====================
    
    def get_widthA(self) -> float:
        """Get width A in seconds"""
        return self.widthA.value() * self.widthA_unit.get_multiplier()
    
    def get_delayA(self) -> float:
        """Get delay A in seconds"""
        return self.delayA.value() * self.delayA_unit.get_multiplier()
    
    def get_widthB(self) -> float:
        """Get width B in seconds"""
        return self.widthB.value() * self.widthB_unit.get_multiplier()
    
    def get_delayB(self) -> float:
        """Get delay B in seconds"""
        return self.delayB.value() * self.delayB_unit.get_multiplier()
    
    def get_widthC(self) -> float:
        """Get width C in seconds"""
        return self.widthC.value() * self.widthC_unit.get_multiplier()
    
    def get_delayC(self) -> float:
        """Get delay C in seconds"""
        return self.delayC.value() * self.delayC_unit.get_multiplier()
    
    def get_widthD(self) -> float:
        """Get width D in seconds"""
        return self.widthD.value() * self.widthD_unit.get_multiplier()
    
    def get_delayD(self) -> float:
        """Get delay D in seconds"""
        return self.delayD.value() * self.delayD_unit.get_multiplier()
    
    def get_period(self) -> float:
        """Get period in seconds"""
        return self.period.value() * self.period_unit.get_multiplier()
    
    def get_frequency(self) -> float:
        """Get frequency in Hz"""
        return self.frequency.value() * self.freq_unit.get_multiplier()
    
    # ==================== SETTER METHODS (accept seconds) ====================
    
    def set_widthA(self, seconds: float):
        """Set width A from seconds"""
        mult = self.widthA_unit.get_multiplier()
        self.widthA.setValue(seconds / mult)
    
    def set_delayA(self, seconds: float):
        """Set delay A from seconds"""
        mult = self.delayA_unit.get_multiplier()
        self.delayA.setValue(seconds / mult)
    
    def set_widthB(self, seconds: float):
        """Set width B from seconds"""
        mult = self.widthB_unit.get_multiplier()
        self.widthB.setValue(seconds / mult)
    
    def set_delayB(self, seconds: float):
        """Set delay B from seconds"""
        mult = self.delayB_unit.get_multiplier()
        self.delayB.setValue(seconds / mult)
    
    def set_widthC(self, seconds: float):
        """Set width C from seconds"""
        mult = self.widthC_unit.get_multiplier()
        self.widthC.setValue(seconds / mult)
    
    def set_delayC(self, seconds: float):
        """Set delay C from seconds"""
        mult = self.delayC_unit.get_multiplier()
        self.delayC.setValue(seconds / mult)
    
    def set_widthD(self, seconds: float):
        """Set width D from seconds"""
        mult = self.widthD_unit.get_multiplier()
        self.widthD.setValue(seconds / mult)
    
    def set_delayD(self, seconds: float):
        """Set delay D from seconds"""
        mult = self.delayD_unit.get_multiplier()
        self.delayD.setValue(seconds / mult)
    
    def set_period(self, seconds: float):
        """Set period from seconds"""
        mult = self.period_unit.get_multiplier()
        self.period.setValue(seconds / mult)
    
    # ==================== CHANNEL ENABLE STATE ====================
    
    def is_channel_enabled(self, channel: str) -> bool:
        """Check if channel is enabled"""
        ch = channel.upper().replace("CH", "")
        btn = getattr(self, f'btn_en_{ch.lower()}', None)
        return btn.isChecked() if btn else False
    
    def set_channel_enabled(self, channel: str, enabled: bool):
        """Set channel enabled state"""
        ch = channel.upper().replace("CH", "")
        btn = getattr(self, f'btn_en_{ch.lower()}', None)
        if btn:
            btn.setChecked(enabled)
    
    # ==================== TRIGGER SETTINGS ====================
    
    def get_trigger_source(self) -> str:
        """Get trigger source: INT or EXT"""
        return self.trig_source.currentText()
    
    def get_trigger_slope(self) -> str:
        """Get trigger slope: POS or NEG"""
        return self.trig_slope.currentText()
    
    def get_trigger_level(self) -> float:
        """Get trigger level in volts"""
        return self.trig_level.value()
    
    def is_trigger_enabled(self) -> bool:
        """Check if external trigger is enabled"""
        return self.btn_en_trig.isChecked()
    
    # ==================== SYSTEM MODE ====================
    
    def get_system_mode(self) -> str:
        """Get system mode"""
        modes = {
            "Continuous": "NORM",
            "Single Shot": "SING", 
            "Burst": "BURS",
            "Duty Cycle": "DCYC"
        }
        return modes.get(self.system_mode.currentText(), "NORM")
    
    def set_system_mode(self, mode: str):
        """Set system mode"""
        modes = {
            "NORM": "Continuous",
            "SING": "Single Shot",
            "BURS": "Burst",
            "DCYC": "Duty Cycle"
        }
        text = modes.get(mode.upper(), "Continuous")
        idx = self.system_mode.findText(text)
        if idx >= 0:
            self.system_mode.setCurrentIndex(idx)
    
    # ==================== STATUS ====================
    
    def set_connected(self, connected: bool, info: str = ""):
        """Update connection status"""
        if connected:
            self.lamp.set_status("green", f"Connected: {info}")
            self.btn_connect.setEnabled(False)
            self.btn_disconnect.setEnabled(True)
        else:
            self.lamp.set_status("red", "Not Connected")
            self.btn_connect.setEnabled(True)
            self.btn_disconnect.setEnabled(False)
    
    def set_running(self, running: bool):
        """Update running status"""
        if running:
            self.lamp.set_status("green", "Running")
        else:
            self.lamp.set_status("yellow", "Stopped")


# Test standalone
if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    panel = BNC575Panel()
    panel.setWindowTitle("BNC575 Panel Test")
    panel.resize(500, 600)
    panel.show()
    
    # Test getters
    print(f"Width A: {panel.get_widthA()}")
    print(f"Delay A: {panel.get_delayA()}")
    print(f"Period: {panel.get_period()}")
    print(f"Mode: {panel.get_system_mode()}")
    
    sys.exit(app.exec())
