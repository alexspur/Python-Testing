# # # gui/rigol_panel.py
# # from PyQt6.QtWidgets import (
# #     QWidget, QGroupBox, QGridLayout, QPushButton, QLabel
# # )
# # from utils.status_lamp import StatusLamp
# # class RigolPanel(QGroupBox):
# #     def __init__(self):
# #         super().__init__("Rigol Oscilloscopes")
# #         layout = QGridLayout()
# #         self.setLayout(layout)

# #         # ⭐ NEW: Status Lamp
# #         self.lamp = StatusLamp(size=14)
# #         layout.addWidget(self.lamp)


# #         # --- BUTTONS ---
# #         self.btn_r1 = QPushButton("Connect Rigol #1")
# #         self.btn_r2 = QPushButton("Connect Rigol #2")
# #         self.btn_r3 = QPushButton("Connect Rigol #3")

# #         # ⭐ NEW SINGLE-CAPTURE BUTTONS
# #         self.btn_r1_single = QPushButton("R1 SINGLE")
# #         self.btn_r2_single = QPushButton("R2 SINGLE")
# #         self.btn_r3_single = QPushButton("R3 SINGLE")


# #         self.btn_r1_capture = QPushButton("Capture R1")
# #         self.btn_r2_capture = QPushButton("Capture R2")
# #         self.btn_r3_capture = QPushButton("Capture R3")


# #         # Main capture all button
# #         self.btn_capture = QPushButton("Capture All Scopes")

# #         # --- LAYOUT ---
# #         layout.addWidget(QLabel("Rigol #1:"), 0, 0)
# #         layout.addWidget(self.btn_r1, 0, 1)
# #         layout.addWidget(self.btn_r1_single, 0, 2)

# #         layout.addWidget(QLabel("Rigol #2:"), 1, 0)
# #         layout.addWidget(self.btn_r2, 1, 1)
# #         layout.addWidget(self.btn_r2_single, 1, 2)

# #         layout.addWidget(QLabel("Rigol #3:"), 2, 0)
# #         layout.addWidget(self.btn_r3, 2, 1)
# #         layout.addWidget(self.btn_r3_single, 2, 2)


# #         layout.addWidget(self.btn_r1_capture, 0, 3)
# #         layout.addWidget(self.btn_r2_capture, 1, 3)
# #         layout.addWidget(self.btn_r3_capture, 2, 3)
# #         # ⭐ Status lamps for each Rigol
# #         self.lamp_r1 = StatusLamp(size=14)
# #         self.lamp_r2 = StatusLamp(size=14)
# #         self.lamp_r3 = StatusLamp(size=14)

# #         # layout.addWidget(self.lamp_r1)
# #         # layout.addWidget(self.lamp_r2)
# #         # layout.addWidget(self.lamp_r3)
# #         layout.addWidget(self.lamp_r1, 0, 4)
# #         layout.addWidget(self.lamp_r2, 1, 4)
# #         layout.addWidget(self.lamp_r3, 2, 4)




# #         self.btn_r1_disconnect = QPushButton("Disconnect R1")
# #         # layout.addWidget(self.btn_r1_disconnect)
# #         layout.addWidget(self.btn_r1_disconnect, 0, 5)

# #         self.btn_r2_disconnect = QPushButton("Disconnect R2")
# #         # layout.addWidget(self.btn_r2_disconnect)
# #         layout.addWidget(self.btn_r2_disconnect, 1, 5)

# #         self.btn_r3_disconnect = QPushButton("Disconnect R3")
# #         # layout.addWidget(self.btn_r3_disconnect)
# #         layout.addWidget(self.btn_r3_disconnect, 2, 5)

# #         # Capture all button
# #         layout.addWidget(self.btn_capture, 3, 0, 1, 3)

# #         self.btn_export = QPushButton("Export Waveforms to CSV")
# #         layout.addWidget(self.btn_export)

# # gui/rigol_panel.py
# # gui/rigol_panel.py
# from PyQt6.QtWidgets import (
#     QWidget, QGroupBox, QGridLayout, QPushButton, QLabel
# )
# from utils.status_lamp import StatusLamp


# class RigolPanel(QGroupBox):
#     def __init__(self, **kwargs):
#         super().__init__("Rigol Oscilloscopes")
#         layout = QGridLayout()
#         self.setLayout(layout)

#         # Status Lamp
#         self.lamp = StatusLamp(size=14)
#         layout.addWidget(self.lamp)

#         # --- BUTTONS ---
#         self.btn_r1 = QPushButton("Connect Rigol #1")
#         self.btn_r2 = QPushButton("Connect Rigol #2")
#         self.btn_r3 = QPushButton("Connect Rigol #3")

#         # SINGLE-CAPTURE BUTTONS
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

#         # Status lamps for each Rigol
#         self.lamp_r1 = StatusLamp(size=14)
#         self.lamp_r2 = StatusLamp(size=14)
#         self.lamp_r3 = StatusLamp(size=14)

#         layout.addWidget(self.lamp_r1, 0, 4)
#         layout.addWidget(self.lamp_r2, 1, 4)
#         layout.addWidget(self.lamp_r3, 2, 4)

#         self.btn_r1_disconnect = QPushButton("Disconnect R1")
#         layout.addWidget(self.btn_r1_disconnect, 0, 5)

#         self.btn_r2_disconnect = QPushButton("Disconnect R2")
#         layout.addWidget(self.btn_r2_disconnect, 1, 5)

#         self.btn_r3_disconnect = QPushButton("Disconnect R3")
#         layout.addWidget(self.btn_r3_disconnect, 2, 5)

#         # Capture all button
#         layout.addWidget(self.btn_capture, 3, 0, 1, 3)

#         self.btn_export = QPushButton("Export Waveforms to CSV")
#         layout.addWidget(self.btn_export)

"""
Rigol Oscilloscope Control Panel

UI panel for connecting to and controlling multiple Rigol oscilloscopes.
"""

from PyQt6.QtWidgets import (
    QGroupBox, QGridLayout, QPushButton, QLabel
)
from utils.accent_button import accent_button, CAPTURE_GREEN
from utils.status_lamp import StatusLamp


class RigolPanel(QGroupBox):
    def __init__(self, **kwargs):
        super().__init__("Rigol Oscilloscopes")
        layout = QGridLayout()
        self.setLayout(layout)

        # --- BUTTONS ---
        # Each row is already labelled "Rigol #N:", so repeating the scope
        # number on every button only makes the panel wider than the window.
        self.btn_r1 = QPushButton("Connect")
        self.btn_r2 = QPushButton("Connect")
        self.btn_r3 = QPushButton("Connect")

        # SINGLE-CAPTURE BUTTONS
        self.btn_r1_single = QPushButton("SINGLE")
        self.btn_r2_single = QPushButton("SINGLE")
        self.btn_r3_single = QPushButton("SINGLE")

        # Read what is already in the scope's memory. These never send
        # :SINGle: arming discards the previous acquisition, so a read that
        # re-armed would destroy the shot it was meant to retrieve.
        self.btn_r1_capture = QPushButton("Read R1")
        self.btn_r2_capture = QPushButton("Read R2")
        self.btn_r3_capture = QPushButton("Read R3")
        for _btn in (self.btn_r1_capture, self.btn_r2_capture, self.btn_r3_capture):
            _btn.setToolTip("Read the last acquisition from this scope. "
                            "Does not re-arm, so it cannot discard the shot.")

        # Main capture all button
        self.btn_capture = QPushButton("Capture All")
        accent_button(self.btn_capture, CAPTURE_GREEN,
                      "Arm all three scopes for the next shot.")

        # --- LAYOUT ---
        layout.addWidget(QLabel("Rigol #1:"), 0, 0)
        layout.addWidget(self.btn_r1, 0, 1)
        layout.addWidget(self.btn_r1_single, 0, 2)

        layout.addWidget(QLabel("Rigol #2:"), 1, 0)
        layout.addWidget(self.btn_r2, 1, 1)
        layout.addWidget(self.btn_r2_single, 1, 2)

        layout.addWidget(QLabel("Rigol #3:"), 2, 0)
        layout.addWidget(self.btn_r3, 2, 1)
        layout.addWidget(self.btn_r3_single, 2, 2)

        layout.addWidget(self.btn_r1_capture, 0, 3)
        layout.addWidget(self.btn_r2_capture, 1, 3)
        layout.addWidget(self.btn_r3_capture, 2, 3)

        # Status lamps for each Rigol
        self.lamp_r1 = StatusLamp(size=14)
        self.lamp_r2 = StatusLamp(size=14)
        self.lamp_r3 = StatusLamp(size=14)

        layout.addWidget(self.lamp_r1, 0, 4)
        layout.addWidget(self.lamp_r2, 1, 4)
        layout.addWidget(self.lamp_r3, 2, 4)

        self.btn_r1_disconnect = QPushButton("Disconnect")
        layout.addWidget(self.btn_r1_disconnect, 0, 5)

        self.btn_r2_disconnect = QPushButton("Disconnect")
        layout.addWidget(self.btn_r2_disconnect, 1, 5)

        self.btn_r3_disconnect = QPushButton("Disconnect")
        layout.addWidget(self.btn_r3_disconnect, 2, 5)

        # Capture all button
        layout.addWidget(self.btn_capture, 3, 0, 1, 3)

        self.btn_export = QPushButton("Export CSV")
        self.btn_export.setToolTip("Export the captured waveforms to CSV.")
        layout.addWidget(self.btn_export)
