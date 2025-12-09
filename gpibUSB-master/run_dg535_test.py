# import sys, os, time
# sys.path.append(os.path.join(os.path.dirname(__file__), "gpibUSB-master"))
# from devices.dg535 import dg535

# COM_PORT = "COM5"
# GPIB_ADDR = 15

# dev = dg535(COM_PORT, GPIB_ADDR)
# time.sleep(0.2)

# # --- Tell DG535 to expect LF only as command terminator ---
# print("Setting DG535 terminator to LF only...")
# dev.sendCmd("GT 10\r")

# # Optional: verify by sending a known command with LF ending
# print("Testing with LF terminator only...")
# dev.port.write(b"CL\n")
# time.sleep(0.1)
# dev.port.write(b"TM 2\n")   # single-shot mode
# time.sleep(0.1)
# dev.port.write(b"SS\n")     # fire single pulse
# print("Pulse fired with LF terminator.")
import sys, os, time
sys.path.append(os.path.join(os.path.dirname(__file__), "gpibUSB-master"))
from devices.dg535 import dg535

COM_PORT = "COM5"
GPIB_ADDR = 15

print("Connecting to DG535...")
dev = dg535(COM_PORT, GPIB_ADDR)
time.sleep(0.2)

# Reset and configure Channel A for a 1 µs TTL pulse with no delay
dev.sendCmd("C L\r")
time.sleep(0.1)
# dev.sendCmd("DT 2,1,0\r")          # A delay = 0
# dev.sendCmd("DT 3,2,1.0E-6\r")     # Pulse width = 1 µs
# dev.sendCmd("TZ 2,0\r")            # 50 Ω load
# dev.sendCmd("OM 2,0\r")            # TTL mode
# dev.sendCmd("OP 2,1\r")            # Normal polarity

# --- Single-shot trigger mode ---
dev.sendCmd("T M 2\r")              # Single-Shot mode
time.sleep(0.1)

print("Firing one pulse...")
dev.sendCmd("S S\r")                # Fire single shot
print("Pulse fired.")
