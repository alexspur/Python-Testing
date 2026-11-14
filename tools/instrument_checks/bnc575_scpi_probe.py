import serial
import time

PORT = "COM5"   # <-- change to your port


def try_cmd(ser, cmd):
    """Try writing a SCPI command and report if it errors."""
    try:
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        ser.write((cmd + "\n").encode())
        ser.flush()

        time.sleep(0.05)

        # Attempt to read any error reply (some firmware echoes or sends an error string)
        try:
            resp = ser.read(128).decode(errors="ignore").strip()
        except:
            resp = ""

        if resp:
            print(f"  ⚠ Response to {cmd!r}: {resp}")
        else:
            print(f"  ✅ OK: {cmd}")

        return True
    except Exception as e:
        print(f"  ❌ FAIL: {cmd}  ({e})")
        return False


print("\n======================")
print("BNC575 SCPI PROBE TOOL")
print("======================\n")

try:
    ser = serial.Serial(PORT, baudrate=115200, timeout=0.1, write_timeout=0.1)
    time.sleep(0.3)
    print(f"Connected to {PORT}\n")
except Exception as e:
    print(f"Could not open port {PORT}: {e}")
    exit(1)

# -------------------------------
# TEST GROUP 1: PULSE ENGINE STYLE
# -------------------------------
print("\n### TESTING SYNTAX TYPE 1: ':PULSE<num>:CMD' style ###\n")

pulse_style_cmds = [
    ":PULSE1:DEL 1E-6",
    ":PULSE1:WIDT 1E-6",
    ":PULSE1:POL NORM",
    ":PULSE1:STATE ON",
    ":PULSE0:TRIG:SOUR EXT",
    ":PULSE0:TRIG:LEV 2.5",
    ":PULSE0:TRIG:EDGE RIS",
    ":PULSE0:MODE SING",
]

for cmd in pulse_style_cmds:
    try_cmd(ser, cmd)

# -------------------------------
# TEST GROUP 2: CHANNEL NAME STYLE
# -------------------------------
print("\n### TESTING SYNTAX TYPE 2: 'CHA:CMD' style ###\n")

channel_style_cmds = [
    "CHA:DEL 1E-6",
    "CHA:WIDT 1E-6",
    "CHA:POL NORM",
    "CHA:STATE ON",
    "CHB:DEL 2E-6",
    "T0:TRIG:SOUR EXT",
    "T0:TRIG:LEV 2.5",
    "T0:MODE SING",
]

for cmd in channel_style_cmds:
    try_cmd(ser, cmd)

# -------------------------------
# TEST GROUP 3: SHORT / ALTERNATE COMMANDS
# -------------------------------
print("\n### TESTING SYNTAX TYPE 3: Alternative commands ###\n")

alt_cmds = [
    "DEL1 1E-6",
    "WID1 1E-6",
    "POL1 NORM",
    "ENA1 1",
    "TRIG EXT",
    "MODE SING",
    "*TRG",
]

for cmd in alt_cmds:
    try_cmd(ser, cmd)

# -------------------------------
# TEST GROUP 4: SAFE ID/STATUS CHECKS
# -------------------------------
print("\n### TESTING SAFE ID/STATUS COMMANDS ###\n")

id_cmds = [
    "*IDN?",
    "ID?",
    ":SYST:ERR?",
    ":PULSE0:STAT?",
]

for cmd in id_cmds:
    try_cmd(ser, cmd)

print("\n\n=============================")
print("TEST COMPLETE — copy results")
print("=============================\n")
