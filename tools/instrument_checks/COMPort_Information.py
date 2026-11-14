# """
# list_com_ports.py

# Lists every serial (COM) port and the fields you can use to identify it.
# Requires pyserial:  pip install pyserial

# Usage:
#     python list_com_ports.py            readable report
#     python list_com_ports.py --json     JSON output (save it as a device inventory)
#     python list_com_ports.py --watch    reprint whenever a device is plugged or unplugged
# """

# import argparse
# import json
# import time

# from serial.tools import list_ports


# FIELDS = [
#     "device",         # COM number, e.g. COM5 (can change)
#     "name",
#     "description",    # friendly name from Device Manager
#     "manufacturer",
#     "product",
#     "vid",            # USB vendor ID
#     "pid",            # USB product ID
#     "serial_number",  # unique per unit if the chip has one
#     "location",       # physical USB path, stable for a given port
#     "interface",      # useful for multi-port adapters
#     "hwid",           # full hardware ID string
# ]


# def port_info(p):
#     info = {f: getattr(p, f, None) for f in FIELDS}
#     info["vid_hex"] = f"{p.vid:04X}" if p.vid is not None else None
#     info["pid_hex"] = f"{p.pid:04X}" if p.pid is not None else None
#     info["match_rule"] = suggest_match(p)
#     return info


# def suggest_match(p):
#     """Return the most reliable way to find this device again."""
#     if p.vid is None:
#         return "Not a USB device. Match on the description or the COM number."
#     base = f"p.vid == 0x{p.vid:04X} and p.pid == 0x{p.pid:04X}"
#     if p.serial_number and not looks_generated(p.serial_number):
#         return f'{base} and p.serial_number == "{p.serial_number}"'
#     if p.location:
#         return f'{base} and p.location == "{p.location}"  (no unique serial, tied to this USB port)'
#     return f"{base}  (no serial or location, not unique if you own two)"


# def looks_generated(serial):
#     """Flag serials that are not unique per unit.

#     Windows invents an instance ID like 5&1A2B3C4D&0&2 when the chip has no serial.
#     Some chips ship with a padded placeholder like TUSB3410________ that every
#     unit shares.
#     """
#     s = serial.strip()
#     if "&" in s:
#         return True
#     if "_" in s and s.rstrip("_") != s:
#         return True
#     if len(set(s)) <= 1:
#         return True
#     return False


# def get_ports():
#     return sorted(list_ports.comports(), key=lambda p: p.device)


# def print_report(ports):
#     if not ports:
#         print("No serial ports found.")
#         return
#     for p in ports:
#         info = port_info(p)
#         print("=" * 70)
#         print(f"{info['device']}  {info['description']}")
#         print("-" * 70)
#         for key in ["manufacturer", "product", "vid_hex", "pid_hex",
#                     "serial_number", "location", "interface", "hwid"]:
#             print(f"  {key:<14} {info[key]}")
#         print(f"  {'match_rule':<14} {info['match_rule']}")
#     print("=" * 70)
#     print(f"{len(ports)} port(s) found.")


# def watch(interval=1.0):
#     print("Watching for changes. Press Ctrl+C to stop.\n")
#     seen = None
#     try:
#         while True:
#             ports = get_ports()
#             current = {p.device for p in ports}
#             if current != seen:
#                 if seen is not None:
#                     added = current - seen
#                     removed = seen - current
#                     if added:
#                         print(f"\nAdded: {', '.join(sorted(added))}")
#                     if removed:
#                         print(f"\nRemoved: {', '.join(sorted(removed))}")
#                 print_report(ports)
#                 seen = current
#             time.sleep(interval)
#     except KeyboardInterrupt:
#         pass


# def main():
#     parser = argparse.ArgumentParser(description="List COM port identification info.")
#     parser.add_argument("--json", action="store_true", help="output JSON")
#     parser.add_argument("--watch", action="store_true", help="reprint on plug or unplug")
#     args = parser.parse_args()

#     if args.watch:
#         watch()
#     elif args.json:
#         print(json.dumps([port_info(p) for p in get_ports()], indent=2))
#     else:
#         print_report(get_ports())


# if __name__ == "__main__":
#     main()

"""
glassman_id.py

Finds the positive and negative Glassman / XP Power WJ supplies by USB identity,
confirms each one answers the WJ serial protocol, and returns their COM ports.

Requires pyserial:  pip install pyserial

Usage:
    python glassman_id.py --scan    list every WJ candidate with serial, location, firmware
    python glassman_id.py           resolve POS and NEG to COM ports using SUPPLIES below
    python glassman_id.py --status  resolve, then read voltage, current and status once

In your GUI:
    from glassman_id import find_supplies
    ports = find_supplies()          # {"POS": "COM13", "NEG": "COM15"}
"""

import argparse
import sys

import serial
from serial.tools import list_ports


# ---------------------------------------------------------------------------
# Edit this table. Each rule lists the port attributes that must all match.
# Use exactly one of these per supply:
#   serial_number  best (FTDI USB-RS232 adapter attached to the supply)
#   location       tied to a physical hub port
# The POS and NEG assignment below is a placeholder. Confirm it with --scan
# and the front panel polarity LEDs before you rely on it.
# ---------------------------------------------------------------------------
SUPPLIES = {
    "POS": {"vid": 0x0451, "pid": 0x3410, "location": "1-13.2.4",
            "rated_kv": None, "rated_ma": None},
    "NEG": {"vid": 0x0451, "pid": 0x3410, "location": "1-13.2.3",
            "rated_kv": None, "rated_ma": None},

    # Example for FTDI adapters on the RS-232 port (J1):
    # "POS": {"vid": 0x0403, "pid": 0x6001, "serial_number": "XXXXXXXX",
    #         "rated_kv": 30.0, "rated_ma": 4.0},
}

MATCH_KEYS = ("vid", "pid", "serial_number", "location")

# USB IDs that may carry a WJ supply. TI TUSB3410 is the built-in USB port.
# FTDI and Prolific cover USB-RS232 adapters on J1.
CANDIDATE_IDS = {(0x0451, 0x3410), (0x0403, 0x6001), (0x067B, 0x2303)}

BAUD = 9600
TIMEOUT = 0.5


# ---------------------------------------------------------------------------
# WJ protocol helpers
# ---------------------------------------------------------------------------
def checksum(payload: bytes) -> bytes:
    """Modulo 256 sum, sent as two uppercase ASCII hex characters."""
    return f"{sum(payload) & 0xFF:02X}".encode()


def packet(body: bytes) -> bytes:
    """SOH + body + checksum + CR. The checksum excludes SOH."""
    return b"\x01" + body + checksum(body) + b"\r"


def open_port(port):
    return serial.Serial(port, BAUD, bytesize=8, parity="N", stopbits=1, timeout=TIMEOUT)


def transact(s, body: bytes) -> bytes:
    s.reset_input_buffer()
    s.write(packet(body))
    return s.read_until(b"\r")


def read_version(port):
    """Send V. Return the two-character firmware revision, or None if no valid reply."""
    try:
        with open_port(port) as s:
            r = transact(s, b"V")
    except serial.SerialException:
        return None
    if len(r) == 6 and r[:1] == b"B" and r[3:5] == checksum(r[1:3]):
        return r[1:3].decode()
    return None


def read_status(port, rated_kv=None, rated_ma=None):
    """Send Q and parse the 16-byte R packet."""
    with open_port(port) as s:
        r = transact(s, b"Q")
    if len(r) != 16 or r[:1] != b"R":
        raise IOError(f"{port}: bad reply {r!r}")
    if r[13:15] != checksum(r[1:13]):
        raise IOError(f"{port}: checksum mismatch in {r!r}")

    v_raw = int(r[1:4], 16)
    i_raw = int(r[4:7], 16)
    bits = int(r[10:11], 16)
    status = {
        "v_fraction": v_raw / 0x3FF,
        "i_fraction": i_raw / 0x3FF,
        "current_mode": bool(bits & 0x1),
        "fault": bool(bits & 0x2),
        "hv_on": bool(bits & 0x4),
    }
    if rated_kv:
        status["kv"] = status["v_fraction"] * rated_kv
    if rated_ma:
        status["ma"] = status["i_fraction"] * rated_ma
    return status


# ---------------------------------------------------------------------------
# Identification
# ---------------------------------------------------------------------------
def matches(p, rule):
    return all(getattr(p, k) == rule[k] for k in MATCH_KEYS if k in rule)


def find_supplies(verify=True):
    """Return {"POS": "COMx", "NEG": "COMy"}. Raise if anything is ambiguous."""
    ports = list_ports.comports()
    result = {}
    for name, rule in SUPPLIES.items():
        hits = [p for p in ports if matches(p, rule)]
        if not hits:
            raise LookupError(f"{name}: no port matches {rule}")
        if len(hits) > 1:
            devs = ", ".join(p.device for p in hits)
            raise LookupError(f"{name}: rule matches several ports ({devs}). Make it more specific.")
        dev = hits[0].device
        if verify and read_version(dev) is None:
            raise IOError(f"{name}: {dev} matched but did not answer the WJ version query.")
        result[name] = dev

    if len(set(result.values())) != len(result):
        raise LookupError(f"Two supplies resolved to the same port: {result}")
    return result


def scan():
    found = [p for p in sorted(list_ports.comports(), key=lambda p: p.device)
             if (p.vid, p.pid) in CANDIDATE_IDS]
    if not found:
        print("No candidate ports found.")
        return
    for p in found:
        fw = read_version(p.device)
        label = f"WJ firmware {fw}" if fw else "no WJ reply"
        print(f"{p.device:<7} {label:<16} vid={p.vid:04X} pid={p.pid:04X} "
              f"serial={p.serial_number!r} location={p.location!r}")
    print("\nCheck the polarity LED on each supply, then fill in SUPPLIES.")


def main():
    ap = argparse.ArgumentParser(description="Identify Glassman WJ supplies.")
    ap.add_argument("--scan", action="store_true", help="list all WJ candidates")
    ap.add_argument("--status", action="store_true", help="read status after resolving")
    args = ap.parse_args()

    if args.scan:
        scan()
        return

    try:
        ports = find_supplies()
    except (LookupError, IOError) as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    for name, dev in ports.items():
        print(f"{name}: {dev}")
        if args.status:
            rule = SUPPLIES[name]
            print("   ", read_status(dev, rule.get("rated_kv"), rule.get("rated_ma")))


if __name__ == "__main__":
    main()