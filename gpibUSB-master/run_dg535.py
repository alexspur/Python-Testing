"""
run_dg535.py
Control the SRS DG535 via a Prologix GPIB-USB adapter on COM5
Run directly in VS Code (Ctrl + F5)
"""

import sys
import os
import time

# Add path to gpibUSB-master folder
sys.path.append(os.path.join(os.path.dirname(__file__), "gpibUSB-master"))

from devices.dg535 import dg535


# === User settings ===
COM_PORT = "COM5"       # Change if your adapter uses a different port
GPIB_ADDR = 15          # DG535 front-panel GPIB address

# === Connect to DG535 ===
print(f"Connecting to DG535 on {COM_PORT}, address {GPIB_ADDR}...")
dev = dg535(COM_PORT, GPIB_ADDR)  # add DOUBLE_BITS=True if you see garbled commands
print("Connected.\n")

# === Example commands ===
print("Clearing and setting up DG535...")

dev.setTrg(0, trgRt=1000)      # Internal trigger @1 kHz
dev.setPulse1(1e-6)            # Pulse 1 width 1 µs
dev.setPulse2(5e-6, 2e-6)      # Pulse 2 starts 5 µs after Pulse 1, lasts 2 µs
dev.setAmp(4, 1.0)             # Output 4 amplitude = 1 V
print("Configuration sent.\n")

# === Keep program alive briefly ===
time.sleep(1)
print("Done.")
