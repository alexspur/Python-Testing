"""
glassman_id.py

Finds the positive and negative Glassman / XP Power WJ supplies by USB identity,
confirms each one answers the WJ serial protocol, and returns their COM ports.

Requires pyserial:  pip install pyserial

Lives in ScopeDelayGUI/instruments/ so the GUI can import it.

Usage (run from the ScopeDelayGUI folder):
    python instruments/glassman_id.py --scan    list every WJ candidate with serial, location, firmware
    python instruments/glassman_id.py           resolve POS and NEG to COM ports using SUPPLIES below
    python instruments/glassman_id.py --status  resolve, then read voltage, current and status once

In the GUI (utils/connect_memory.py resolves WJ1=NEG, WJ2=POS this way):
    from instruments.glassman_id import find_supplies
    ports = find_supplies()          # {"POS": "COM16", "NEG": "COM13"} -- COM numbers change
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
#
# The two WJ supplies report different USB serials, and a cable swap test
# showed the serial follows the supply, not the hub port:
#   one supply reports "TUSB3410________"
#   the other reports an empty serial ""
# That makes the match independent of which USB port each supply uses.
#
# Verified 2026-09-23 by unplugging the POSITIVE supply:
#   POS  serial ""                  WJ firmware 14
#   NEG  serial "TUSB3410________"  WJ firmware 15
# The firmware version is recorded as documentation only; nothing matches on
# it (a serviced or reflashed supply would change it). Do NOT match these
# supplies on location: the two have been seen swapping hub locations.
# Confirm POS with the front panel polarity LED before trusting this table.
# ---------------------------------------------------------------------------
SUPPLIES = {
    "POS": {"vid": 0x0451, "pid": 0x3410, "serial_number": "",
            "firmware": "14", "rated_kv": None, "rated_ma": None},
    "NEG": {"vid": 0x0451, "pid": 0x3410, "serial_number": "TUSB3410________",
            "firmware": "15", "rated_kv": None, "rated_ma": None},

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
    for k in MATCH_KEYS:
        if k not in rule:
            continue
        actual = getattr(p, k)
        if k == "serial_number":
            actual = actual or ""   # treat None and "" as the same empty serial
        if actual != rule[k]:
            return False
    return True


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