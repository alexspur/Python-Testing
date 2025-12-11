# gui/wj_panel.py


# from PyQt6.QtWidgets import (
#     QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton,
#     QLabel, QDoubleSpinBox, QFormLayout
# )
# from utils.status_lamp import StatusLamp

# # class WJPanel(QGroupBox):
# #     def __init__(self):
# class WJPanel(QGroupBox):
#     def __init__(self, num_units=1):
#         super().__init__("WJ High-Voltage Supplies")
#         self.num_units = num_units
#         # super().__init__("WJ HV Power Supply")

#         layout = QVBoxLayout()
#         self.setLayout(layout)

#         # ------------------- CONNECT -------------------
#         row = QHBoxLayout()
#         # self.btn_connect = QPushButton("Connect (COM6)")
#         self.btn_connect = QPushButton("Connect")
#         self.btn_disconnect = QPushButton("Disconnect")
#         layout.addWidget(self.btn_disconnect)
#         row.addWidget(self.btn_connect)
#         layout.addLayout(row)
#         self.lamp = StatusLamp(size=14)
#         layout.addWidget(self.lamp)

#         # ------------------- SETPOINTS -------------------
#         form = QFormLayout()
#         self.voltage = QDoubleSpinBox()
#         self.voltage.setRange(0, 200)  # kV
#         self.voltage.setDecimals(3)

#         self.current = QDoubleSpinBox()
#         self.current.setRange(0, 20)   # mA or A depending on rating
#         self.current.setDecimals(3)

#         form.addRow("Voltage (kV):", self.voltage)
#         form.addRow("Current (mA):", self.current)
#         layout.addLayout(form)

#         # ------------------- COMMAND BUTTONS -------------------
#         row2 = QHBoxLayout()
#         self.btn_set_v = QPushButton("Set Voltage")
#         self.btn_set_i = QPushButton("Set Current")
#         row2.addWidget(self.btn_set_v)
#         row2.addWidget(self.btn_set_i)
#         layout.addLayout(row2)

#         row3 = QHBoxLayout()
#         self.btn_hv_on  = QPushButton("HV ON")
#         self.btn_hv_off = QPushButton("HV OFF")
#         self.btn_reset  = QPushButton("Reset")
#         row3.addWidget(self.btn_hv_on)
#         row3.addWidget(self.btn_hv_off)
#         row3.addWidget(self.btn_reset)
#         layout.addLayout(row3)

#         # ------------------- READBACK -------------------
#         self.btn_read = QPushButton("Readback Status")
#         layout.addWidget(self.btn_read)

#         self.label_status = QLabel("Status: ---")
#         layout.addWidget(self.label_status)

#         # ------------------- LIVE PLOT WINDOW -------------------
#         self.btn_open_plot = QPushButton("Open WJ Live Plot")
#         layout.addWidget(self.btn_open_plot)

#         self.rows = []

#         for i in range(self.num_units):
#             row = self.make_supply_row(i)
#             layout.addLayout(row)
#             self.rows.append(row)
        
#     def make_supply_row(self, index):
#         row = QHBoxLayout()

#         label = QLabel(f"WJ #{index+1}")
#         connect = QPushButton("Connect")
#         disconnect = QPushButton("Disconnect")
#         lamp = StatusLamp(size=14)

#         # Save to list so main_window can access
#         row.label = label
#         row.connect = connect
#         row.disconnect = disconnect
#         row.lamp = lamp

#         row.addWidget(label)
#         row.addWidget(connect)
#         row.addWidget(disconnect)
#         row.addWidget(lamp)
#         return row



# gui/wj_panel.py


from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QDoubleSpinBox, QFormLayout,
    QComboBox
)

# from PyQt6.QtWidgets import (
#     QGroupBox, QVBoxLayout, QGridLayout, QLabel, QPushButton, QComboBox, QHBoxLayout, QDoubleSpinBox
# )
from utils.status_lamp import StatusLamp


from utils.status_lamp import StatusLamp

class WJPanel(QGroupBox):
    def __init__(self, num_units=2):
        super().__init__("WJ High Voltage Supplies")

        self.rows = []   # store each WJ row so main_window can access
        layout = QVBoxLayout()
        self.setLayout(layout)

        # ─────────────────────────────────────────────
        # PROGRAM SETTINGS (shared for all units)
        # ─────────────────────────────────────────────
        prog_row = QHBoxLayout()
        prog_row.addWidget(QLabel("Set Voltage (kV):"))
        self.voltage = QDoubleSpinBox()
        self.voltage.setRange(0, 100)
        self.voltage.setDecimals(2)
        self.voltage.setValue(50.0)   # default 50 kV
        prog_row.addWidget(self.voltage)

        prog_row.addWidget(QLabel("Set Current (mA):"))
        self.current = QDoubleSpinBox()
        self.current.setRange(0, 6)
        self.current.setDecimals(2)
        self.current.setValue(2.0)    # default 2 mA
        prog_row.addWidget(self.current)

        self.btn_set_v = QPushButton("Apply Program")
        prog_row.addWidget(self.btn_set_v)

        layout.addLayout(prog_row)

        # ─────────────────────────────────────────────
        # ACTION BUTTONS (apply to ALL units)
        # ─────────────────────────────────────────────
        ctrl_row = QHBoxLayout()
        self.btn_hv_on  = QPushButton("HV ON (ALL)")
        self.btn_hv_off = QPushButton("HV OFF (ALL)")
        self.btn_reset  = QPushButton("RESET (ALL)")
        self.btn_read   = QPushButton("READBACK")

        ctrl_row.addWidget(self.btn_hv_on)
        ctrl_row.addWidget(self.btn_hv_off)
        ctrl_row.addWidget(self.btn_reset)
        ctrl_row.addWidget(self.btn_read)

        layout.addLayout(ctrl_row)

        # ─────────────────────────────────────────────
        # INDIVIDUAL WJ UNIT ROWS
        # ─────────────────────────────────────────────
        grid = QGridLayout()

        for i in range(num_units):
            row = WJRow(i)
            self.rows.append(row)

            grid.addWidget(row.label,        i, 0)
            grid.addWidget(row.port_combo,   i, 1)
            grid.addWidget(row.connect,      i, 2)
            grid.addWidget(row.disconnect,   i, 3)
            grid.addWidget(row.lamp,         i, 4)
            grid.addWidget(row.label_status, i, 5)

        layout.addLayout(grid)
        # ─────────────────────────────────────────────
        # OPTIONAL: Live plot button
        # ─────────────────────────────────────────────
        self.btn_open_plot = QPushButton("Open WJ Live Plot")
        layout.addWidget(self.btn_open_plot)


class WJRow:
    """Represents one row in the WJPanel."""
    def __init__(self, index):
        self.index = index

        # Custom labels for each power supply
        labels = ["Negative Power Supply", "Positive Power Supply"]
        self.label = QLabel(labels[index] if index < len(labels) else f"WJ Power Supply #{index+1}")

        # ⭐ COM PORT DROPDOWN
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(100)

        self.connect = QPushButton("Connect")
        self.disconnect = QPushButton("Disconnect")

        self.lamp = StatusLamp(size=14)

        self.label_status = QLabel("Not Connected")
