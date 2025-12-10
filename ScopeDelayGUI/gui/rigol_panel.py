# # gui/rigol_panel.py
# from PyQt6.QtWidgets import (
#     QWidget, QGroupBox, QGridLayout, QPushButton, QLabel
# )
# from utils.status_lamp import StatusLamp
# class RigolPanel(QGroupBox):
#     def __init__(self):
#         super().__init__("Rigol Oscilloscopes")
#         layout = QGridLayout()
#         self.setLayout(layout)

#         # ⭐ NEW: Status Lamp
#         self.lamp = StatusLamp(size=14)
#         layout.addWidget(self.lamp)


#         # --- BUTTONS ---
#         self.btn_r1 = QPushButton("Connect Rigol #1")
#         self.btn_r2 = QPushButton("Connect Rigol #2")
#         self.btn_r3 = QPushButton("Connect Rigol #3")

#         # ⭐ NEW SINGLE-CAPTURE BUTTONS
#         self.btn_r1_single = QPushButton("R1 SINGLE")
#         self.btn_r2_single = QPushButton("R2 SINGLE")
#         self.btn_r3_single = QPushButton("R3 SINGLE")


#         self.btn_r1_capture = QPushButton("Capture R1")
#         self.btn_r2_capture = QPushButton("Capture R2")
#         self.btn_r3_capture = QPushButton("Capture R3")


#         # Main capture all button
#         self.btn_capture = QPushButton("Capture All Scopes")

#         # --- LAYOUT ---
#         layout.addWidget(QLabel("Rigol #1:"), 0, 0)
#         layout.addWidget(self.btn_r1, 0, 1)
#         layout.addWidget(self.btn_r1_single, 0, 2)

#         layout.addWidget(QLabel("Rigol #2:"), 1, 0)
#         layout.addWidget(self.btn_r2, 1, 1)
#         layout.addWidget(self.btn_r2_single, 1, 2)

#         layout.addWidget(QLabel("Rigol #3:"), 2, 0)
#         layout.addWidget(self.btn_r3, 2, 1)
#         layout.addWidget(self.btn_r3_single, 2, 2)


#         layout.addWidget(self.btn_r1_capture, 0, 3)
#         layout.addWidget(self.btn_r2_capture, 1, 3)
#         layout.addWidget(self.btn_r3_capture, 2, 3)
#         # ⭐ Status lamps for each Rigol
#         self.lamp_r1 = StatusLamp(size=14)
#         self.lamp_r2 = StatusLamp(size=14)
#         self.lamp_r3 = StatusLamp(size=14)

#         # layout.addWidget(self.lamp_r1)
#         # layout.addWidget(self.lamp_r2)
#         # layout.addWidget(self.lamp_r3)
#         layout.addWidget(self.lamp_r1, 0, 4)
#         layout.addWidget(self.lamp_r2, 1, 4)
#         layout.addWidget(self.lamp_r3, 2, 4)




#         self.btn_r1_disconnect = QPushButton("Disconnect R1")
#         # layout.addWidget(self.btn_r1_disconnect)
#         layout.addWidget(self.btn_r1_disconnect, 0, 5)

#         self.btn_r2_disconnect = QPushButton("Disconnect R2")
#         # layout.addWidget(self.btn_r2_disconnect)
#         layout.addWidget(self.btn_r2_disconnect, 1, 5)

#         self.btn_r3_disconnect = QPushButton("Disconnect R3")
#         # layout.addWidget(self.btn_r3_disconnect)
#         layout.addWidget(self.btn_r3_disconnect, 2, 5)

#         # Capture all button
#         layout.addWidget(self.btn_capture, 3, 0, 1, 3)

#         self.btn_export = QPushButton("Export Waveforms to CSV")
#         layout.addWidget(self.btn_export)

# gui/rigol_panel.py
from PyQt6.QtWidgets import (
    QWidget, QGroupBox, QGridLayout, QPushButton, QLabel, QSpinBox, QHBoxLayout
)
from utils.status_lamp import StatusLamp


class RigolPanel(QGroupBox):
    """
    Control panel for Rigol DS7000 series oscilloscopes.
    Supports configurable channel count (1-4, default 4 for DS7504).
    """
    
    def __init__(self, default_channels: int = 4):
        super().__init__("Rigol Oscilloscopes")
        self.default_channels = min(4, max(1, default_channels))
        
        layout = QGridLayout()
        self.setLayout(layout)

        # Status Lamp
        self.lamp = StatusLamp(size=14)
        layout.addWidget(self.lamp, 0, 0)

        # Channel count selector
        ch_row = QHBoxLayout()
        ch_row.addWidget(QLabel("Channels:"))
        self.channel_spin = QSpinBox()
        self.channel_spin.setRange(1, 4)
        self.channel_spin.setValue(self.default_channels)
        self.channel_spin.setToolTip("Number of channels to capture (1-4)")
        ch_row.addWidget(self.channel_spin)
        ch_row.addStretch()
        
        # Add channel selector to layout
        ch_widget = QWidget()
        ch_widget.setLayout(ch_row)
        layout.addWidget(ch_widget, 0, 1, 1, 2)

        # Connect buttons
        self.btn_r1 = QPushButton("Connect Rigol #1")
        self.btn_r2 = QPushButton("Connect Rigol #2")
        self.btn_r3 = QPushButton("Connect Rigol #3")

        # SINGLE-CAPTURE BUTTONS
        self.btn_r1_single = QPushButton("R1 SINGLE")
        self.btn_r2_single = QPushButton("R2 SINGLE")
        self.btn_r3_single = QPushButton("R3 SINGLE")

        # Individual capture buttons
        self.btn_r1_capture = QPushButton("Capture R1")
        self.btn_r2_capture = QPushButton("Capture R2")
        self.btn_r3_capture = QPushButton("Capture R3")

        # Main capture all button
        self.btn_capture = QPushButton("Capture All Scopes")

        # Layout for Rigol #1
        layout.addWidget(QLabel("Rigol #1:"), 1, 0)
        layout.addWidget(self.btn_r1, 1, 1)
        layout.addWidget(self.btn_r1_single, 1, 2)
        layout.addWidget(self.btn_r1_capture, 1, 3)

        # Layout for Rigol #2
        layout.addWidget(QLabel("Rigol #2:"), 2, 0)
        layout.addWidget(self.btn_r2, 2, 1)
        layout.addWidget(self.btn_r2_single, 2, 2)
        layout.addWidget(self.btn_r2_capture, 2, 3)

        # Layout for Rigol #3
        layout.addWidget(QLabel("Rigol #3:"), 3, 0)
        layout.addWidget(self.btn_r3, 3, 1)
        layout.addWidget(self.btn_r3_single, 3, 2)
        layout.addWidget(self.btn_r3_capture, 3, 3)

        # Status lamps for each Rigol
        self.lamp_r1 = StatusLamp(size=14)
        self.lamp_r2 = StatusLamp(size=14)
        self.lamp_r3 = StatusLamp(size=14)

        layout.addWidget(self.lamp_r1, 1, 4)
        layout.addWidget(self.lamp_r2, 2, 4)
        layout.addWidget(self.lamp_r3, 3, 4)

        # Disconnect buttons
        self.btn_r1_disconnect = QPushButton("Disconnect R1")
        self.btn_r2_disconnect = QPushButton("Disconnect R2")
        self.btn_r3_disconnect = QPushButton("Disconnect R3")

        layout.addWidget(self.btn_r1_disconnect, 1, 5)
        layout.addWidget(self.btn_r2_disconnect, 2, 5)
        layout.addWidget(self.btn_r3_disconnect, 3, 5)

        # Capture all button
        layout.addWidget(self.btn_capture, 4, 0, 1, 3)

        # Export button
        self.btn_export = QPushButton("Export Waveforms to CSV")
        layout.addWidget(self.btn_export, 4, 3, 1, 3)
    
    def get_channel_count(self) -> int:
        """Get the currently selected channel count."""
        return self.channel_spin.value()
    
    def set_channel_count(self, count: int):
        """Set the channel count spinner value."""
        self.channel_spin.setValue(min(4, max(1, count)))
