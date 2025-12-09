#!/usr/bin/env python3
import pyvisa
import numpy as np
import time
import matplotlib.pyplot as plt


class RigolScope:
    def __init__(self, resource):
        self.resource = resource
        self.rm = None
        self.inst = None

    def connect(self):
        print(f"Connecting to {self.resource} ...")
        self.rm = pyvisa.ResourceManager()
        self.inst = self.rm.open_resource(self.resource)
        self.inst.timeout = 15000
        self.inst.chunk_size = 2_000_000
        self.inst.write("*CLS")
        time.sleep(0.1)
        print("Connected:", self.inst.query("*IDN?").strip())

    def arm_single(self):
        self.inst.write(":STOP")
        time.sleep(0.05)
        self.inst.write(":SINGLE")
        print("  → Armed (SINGLE)")

    def wait_for_trigger(self):
        print("  → Waiting for trigger...")
        while True:
            opc = self.inst.query(":TRIG:STAT?").strip()
            if opc in ("STOP", "TD"):   # TD = triggered
                print("  → Trigger detected.")
                return
            time.sleep(0.05)

    def setup_waveform(self, ch):
        self.inst.write(f":{ch}:DISP ON")
        self.inst.write(":WAV:MODE NORM")
        self.inst.write(":WAV:FORM BYTE")
        self.inst.write(f":WAV:SOUR {ch}")
        time.sleep(0.05)

        self.inst.write(":WAV:STAR 1")
        mdep = int(float(self.inst.query(":ACQ:MDEP?")))
        self.inst.write(f":WAV:STOP {mdep}")

        pre = self.inst.query(":WAV:PRE?").split(',')
        xinc = float(pre[4])
        xorig = float(pre[5])
        yinc = float(pre[7])
        yorig = float(pre[8])
        yref = float(pre[9])

        return xinc, xorig, yinc, yorig, yref

    def read_block(self):
        raw = self.inst.read_raw()
        if raw[0:1] != b'#':
            raise RuntimeError("Invalid SCPI block from Rigol")

        nd = int(raw[1:2])
        size = int(raw[2:2+nd])
        start = 2 + nd
        data = raw[start:start+size]

        return np.frombuffer(data, dtype=np.uint8)

    def capture_channel(self, ch):
        xinc, xorig, yinc, yorig, yref = self.setup_waveform(ch)
        self.inst.write(":WAV:DATA?")
        raw = self.read_block()

        volts = (raw - yref) * yinc + yorig
        t = xorig + np.arange(len(volts)) * xinc
        return t, volts

    def capture_two(self):
        t1, v1 = self.capture_channel("CHAN1")
        t2, v2 = self.capture_channel("CHAN2")
        return (t1, v1), (t2, v2)


# ===========================================================
#  MAIN SCRIPT (edit VISA addresses as needed)
# ===========================================================

RIGOL_ADDR = [
    "USB0::0x1AB1::0x0514::DS7A233300256::0::INSTR",
    "USB0::0x1AB1::0x0514::DS7A232900210::0::INSTR",
    "USB0::0x1AB1::0x0514::DS7A230800035::0::INSTR",
]

scopes = []

# Connect to all scopes
for addr in RIGOL_ADDR:
    s = RigolScope(addr)
    s.connect()
    scopes.append(s)

print("\n--- ARMING ALL SCOPES ---")
for s in scopes:
    s.arm_single()

print("\n⚠  Waiting for YOUR manual trigger (press button, DG535, etc.)")
for s in scopes:
    s.wait_for_trigger()

print("\n--- Capturing Waveforms ---")
captures = []
for idx, s in enumerate(scopes):
    print(f"Reading Scope #{idx+1} ...")
    c = s.capture_two()
    captures.append(c)

print("Done. Plotting...")

# ===========================================================
#  PLOTS
# ===========================================================

fig, axes = plt.subplots(3, 1, figsize=(10, 12))

for i, ((t1, v1), (t2, v2)) in enumerate(captures):
    ax = axes[i]
    ax.plot(t1, v1, label=f"Scope {i+1} CH1")
    ax.plot(t2, v2, label=f"Scope {i+1} CH2")
    ax.legend()
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Voltage (V)")
    ax.set_title(f"Rigol Scope {i+1}")

plt.tight_layout()
plt.show()
