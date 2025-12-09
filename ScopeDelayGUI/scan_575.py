# import serial
# import time

# PORT = "COM5"
# BAUD = 115200
# TIMEOUT = 0.5

# # ------------------------------
# # Commands extracted from manual
# # ------------------------------

# common_commands = [
#     "*IDN?",
#     "*RST",
#     "*CLS",
# ]

# instrument_commands = [
#     ":INST:CAT?",
#     ":INST:FULL?",
#     ":INST:COMM?",
#     ":INST:NSEL 0",
#     ":INST:NSEL 1",
#     ":INST:SEL T0",
#     ":INST:SEL CHA",
#     ":INST:SEL CHB",
# ]

# system_commands = [
#     ":PULSE0:STATE?",
#     ":PULSE0:STATE ON",
#     ":PULSE0:STATE OFF",
#     ":PULSE0:PER?",
#     ":PULSE0:PER 0.001",
#     ":PULSE0:MODE?",
#     ":PULSE0:MODE NORM",
#     ":PULSE0:MODE SING",
#     ":PULSE0:MODE BURST",
#     ":PULSE0:BCOUNTER 5",
#     ":PULSE0:PCOUNTER 5",
#     ":PULSE0:OCOUNTER 5",
#     ":PULSE0:ICLOCK?",
#     ":PULSE0:ICLOCK SYS",
#     ":PULSE0:TRIG:MODE?",
#     ":PULSE0:TRIG:MODE TRIG",
#     ":PULSE0:TRIG:LEV 2.5",
#     ":PULSE0:GATE:MODE?",
#     ":PULSE0:GATE:MODE DIS",
# ]

# channel_commands = [
#     ":PULSE1:STATE?",
#     ":PULSE1:STATE ON",
#     ":PULSE1:STATE OFF",
#     ":PULSE1:WIDT?",
#     ":PULSE1:WIDT 0.000010",
#     ":PULSE1:DELAY?",
#     ":PULSE1:DELAY 0.000005",
#     ":PULSE1:POL?",
#     ":PULSE1:POL NORM",
#     ":PULSE1:SYNC?",
#     ":PULSE1:SYNC T0",
#     ":PULSE1:MUX?",
#     ":PULSE1:MUX 1",
#     ":PULSE1:OUTP:MODE?",
#     ":PULSE1:OUTP:MODE TTL",
# ]

# # Expand for channels B–D
# for ch in [2,3,4]:
#     for c in [
#         f":PULSE{ch}:STATE?",
#         f":PULSE{ch}:WIDT?",
#         f":PULSE{ch}:DELAY?",
#         f":PULSE{ch}:SYNC?",
#         f":PULSE{ch}:MUX?",
#     ]:
#         channel_commands.append(c)

# # -------------------------------------------------
# # Helper function to send and log each SCPI command
# # -------------------------------------------------
# def send_cmd(ser, cmd):
#     ser.write((cmd + "\r\n").encode())
#     time.sleep(0.05)

#     try:
#         resp = ser.read_until(b"\n").decode(errors="ignore").strip()
#     except:
#         resp = "<no response>"
#     return resp


# # -----------------------
# # Main scanning procedure
# # -----------------------
# def main():
#     ser = serial.Serial(PORT, BAUD, timeout=TIMEOUT)
#     time.sleep(2)

#     results = []

#     all_cmds = (
#         ["===== COMMON ====="] + common_commands +
#         ["===== INSTRUMENT ====="] + instrument_commands +
#         ["===== SYSTEM ====="] + system_commands +
#         ["===== CHANNELS ====="] + channel_commands
#     )

#     print("\nStarting BNC 575 Capability Scan...\n")

#     for cmd in all_cmds:
#         if cmd.startswith("===="):
#             print(cmd)
#             results.append(cmd)
#             continue

#         print(f"Sending: {cmd}")
#         resp = send_cmd(ser, cmd)
#         print(f"Response: {resp}\n")

#         results.append(f"{cmd} -> {resp}")

#     ser.close()

#     with open("575_scan_results.txt", "w") as f:
#         for line in results:
#             f.write(line + "\n")

#     print("\nScan complete! Results saved to 575_scan_results.txt")


# if __name__ == "__main__":
#     main()
import serial
import time
import json

PORT = "COM5"
BAUD = 115200
TIMEOUT = 0.5

def send(ser, cmd):
    ser.write((cmd + "\r\n").encode())
    time.sleep(0.05)
    resp = ser.read_until(b"\n").decode(errors="ignore").strip()
    if resp.startswith("?"):
        return False, resp
    if resp.lower().startswith("ok"):
        return True, resp
    return True, resp  # treat weird replies as partial success

def scan():
    ser = serial.Serial(PORT, BAUD, timeout=TIMEOUT)
    time.sleep(1)

    capabilities = {}

    test_commands = {
        "set_state": ":PULSE1:STATE ON",
        "set_width": ":PULSE1:WIDT 0.000010",
        "set_delay": ":PULSE1:DELAY 0.000005",
        "set_polarity": ":PULSE1:POL NORM",
        "set_sync": ":PULSE1:SYNC T0",
        "set_mux": ":PULSE1:MUX 1",
        "set_mode_norm": ":PULSE0:MODE NORM",
        "set_mode_sing": ":PULSE0:MODE SING",
        "set_mode_burst": ":PULSE0:MODE BURST",
        "set_burst_count": ":PULSE0:BCOUNTER 5",
        "set_trigger_mode": ":PULSE0:TRIG:MODE TRIG",
        "set_trigger_level": ":PULSE0:TRIG:LEV 2.5",
        "set_gate_mode": ":PULSE0:GATE:MODE DIS",
        "set_period": ":PULSE0:PER 0.001",
        "cls_command": "*CLS",
    }

    for name, cmd in test_commands.items():
        ok, resp = send(ser, cmd)
        capabilities[name] = {
            "supported": ok,
            "response": resp
        }
        time.sleep(0.1)

    ser.close()

    with open("575_capabilities.json", "w") as f:
        json.dump(capabilities, f, indent=4)

    print("\nFinished scanning capabilities.")
    print("Saved to 575_capabilities.json")

scan()
