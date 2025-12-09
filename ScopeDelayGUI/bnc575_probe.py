import serial
import time

PORT = "COM5"   # <-- change if needed

def send(ser, cmd):
    ser.write((cmd + "\n").encode())
    time.sleep(0.05)
    resp = ser.readlines()
    if resp:
        return [r.decode().strip() for r in resp]
    return []

print("\n---------------------")
print("   BNC575 PROBE TOOL")
print("---------------------\n")

ser = serial.Serial(PORT, 115200, timeout=0.2)
time.sleep(1)

# Flush
ser.reset_input_buffer()
ser.reset_output_buffer()

def q(cmd):
    ser.write((cmd + "\n").encode())
    time.sleep(0.05)
    return ser.readline().decode().strip()

print("IDENTIFY:")
print(q("*IDN?"))
print()

print("CHANNEL CATALOG:")
print(q(":INST:CATalog?"))
print()

print("FULL CHANNEL LIST:")
print(q(":INST:FULL?"))
print()

# Query all channels for DEL and WIDT support
channels = ["T0", "CHA", "CHB", "CHC", "CHD", "CHE", "CHF", "CHG", "CHH"]

print("CHANNEL CAPABILITY SCAN:")
print("------------------------")

for ch in channels:
    print(f"\n--- {ch} ---")
    
    ser.write(f":INST:SEL {ch}\n".encode())
    time.sleep(0.05)

    # Query DEL
    try:
        d = q(":DELay?")
        print(f"DELay? → {d}")
    except:
        print("DELay? → ERROR")

    # Query WIDT
    try:
        w = q(":WIDT?")
        print(f"WIDT?  → {w}")
    except:
        print("WIDT?  → ERROR")

    # State
    try:
        s = q(":STATe?")
        print(f"STATe? → {s}")
    except:
        print("STATe? → ERROR")

ser.close()
print("\nProbe complete.")
