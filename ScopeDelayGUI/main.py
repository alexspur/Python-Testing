from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont
from gui.main_window import ScopeDelayMainWindow
import sys


# ----------------------------------------------------------------------
# Auto-connect toggles. Set each to True/False (1/0 also work) to control
# which instruments the GUI tries to connect to on startup. Anything left
# out of this dict defaults to True. Example: to only auto-connect Rigol 1,
# set rigol2 and rigol3 (and whatever else you don't want) to False.
# ----------------------------------------------------------------------
AUTO_CONNECT = {
    "dg535":  True,   # DG535 delay generator
    "bnc575": True,   # BNC575 delay generator
    "opta":   True,   # Opta pressure monitor (Modbus TCP)
    "relay":  True,   # Numato relay module
    "wj1":    True,   # negative WJ supply
    "wj2":    True,   # positive WJ supply
    "rigol1": True,   # oscilloscope 1
    "rigol2": True,   # oscilloscope 2
    "rigol3": True,   # oscilloscope 3
}

# Opta pressure monitor on the point-to-point fiber Ethernet link. The PC NIC
# must be static on the same /24. The GUI polls it every OPTA_POLL_MS on a
# background thread.
OPTA_HOST = "192.168.10.20"
OPTA_PORT = 502
OPTA_POLL_MS = 200

# After a scope capture, the GUI waits this many seco nds, then automatically
# saves the captured waveform(s) to the session folder. Anything still unsaved
# is also flushed when the app closes. Set to 0 to disable the timed auto-save
# (the save-on-close safety net still runs).
AUTO_SAVE_DELAY_SEC = 10.0

# Dome pressure gauge scale (PSI) shown in the SF6 window. Adjust to match the
# current sensor range.
PRESSURE_GAUGE_MIN_PSI = 0.0
PRESSURE_GAUGE_MAX_PSI = 160.0

# Startup charge voltage (kV) preloaded into the "Set Voltage" box for the WJ
# power supplies. This is the kV that HV ON commands.
STARTUP_CHARGE_KV = 75.0


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Global font and color
    base_font = QFont("Times New Roman")
    base_font.setBold(True)
    app.setFont(base_font)
    app.setStyleSheet("""
        * {l
            font-family: 'Times New Roman';
            font-weight: bold;
            color: black;
        }
    """)

    window = ScopeDelayMainWindow(
        auto_connect=AUTO_CONNECT,
        auto_save_delay_sec=AUTO_SAVE_DELAY_SEC,
        pressure_gauge_min=PRESSURE_GAUGE_MIN_PSI,
        pressure_gauge_max=PRESSURE_GAUGE_MAX_PSI,
        startup_charge_kv=STARTUP_CHARGE_KV,
        opta_host=OPTA_HOST,
        opta_port=OPTA_PORT,
        opta_poll_ms=OPTA_POLL_MS,
    )
    window.show()

    sys.exit(app.exec())

