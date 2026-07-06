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
    "mega":   True,   # Glassman / Marx Mega
    "relay":  True,   # Numato relay module
    "wj1":    True,   # negative WJ supply
    "wj2":    False,   # positive WJ supply
    "rigol1": True,   # oscilloscope 1
    "rigol2": True,   # oscilloscope 2
    "rigol3": True,   # oscilloscope 3
}

# Pressure (psi) the Mega is automatically commanded to once it connects on
# startup. Set to None to skip auto-setting the pressure.
STARTUP_PRESSURE_PSI = 50.0

# When HV ON is pressed, the dome is first raised to HV_ON_PRESSURE_PSI, then
# the GUI waits HV_ON_DELAY_SEC for it to settle before actually enabling HV.
HV_ON_PRESSURE_PSI = 20.0
HV_ON_DELAY_SEC = 3.0

# After a scope capture, the GUI waits this many seco nds, then automatically
# saves the captured waveform(s) to the session folder. Anything still unsaved
# is also flushed when the app closes. Set to 0 to disable the timed auto-save
# (the save-on-close safety net still runs).
AUTO_SAVE_DELAY_SEC = 10.0

# Default state of the "Pre-pressurize dome on HV ON" checkbox. True = HV ON
# raises the dome to HV_ON_PRESSURE_PSI and waits HV_ON_DELAY_SEC first; False =
# HV ON enables HV immediately. The checkbox can still be toggled at runtime.
PREPRESSURIZE_ON_HV_ON = False

# Dome pressure gauge scale (PSI) shown in the SF6 window. Adjust to match the
# current sensor/regulator range.
PRESSURE_GAUGE_MIN_PSI = 0.0
PRESSURE_GAUGE_MAX_PSI = 160.0

# Max value (PSI) the pressure setpoint spinbox accepts. The Mega firmware does
# the PSI->voltage calibration and hard-clamps at its own PSI_MAX_CMD (145),
# so keep this at or below that.
PRESSURE_CONTROL_MAX_PSI = 120.0

# Quick-set pressure preset buttons (PSI). Edit this list to change the buttons.
PRESSURE_PRESETS_PSI = [ 20, 30, 40, 50, 60, 70, 80, 90, 100, 110]

# Startup charge voltage (kV) preloaded into the "Set Voltage" box for BOTH
# power supplies (WJ + Glassman). This is the kV that HV ON commands to both.
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
        startup_pressure_psi=STARTUP_PRESSURE_PSI,
        hv_on_pressure_psi=HV_ON_PRESSURE_PSI,
        hv_on_delay_sec=HV_ON_DELAY_SEC,
        auto_save_delay_sec=AUTO_SAVE_DELAY_SEC,
        prepressurize_on_hv_on=PREPRESSURIZE_ON_HV_ON,
        pressure_gauge_min=PRESSURE_GAUGE_MIN_PSI,
        pressure_gauge_max=PRESSURE_GAUGE_MAX_PSI,
        pressure_control_max=PRESSURE_CONTROL_MAX_PSI,
        pressure_presets=PRESSURE_PRESETS_PSI,
        startup_charge_kv=STARTUP_CHARGE_KV,
    )
    window.show()

    sys.exit(app.exec())
 
