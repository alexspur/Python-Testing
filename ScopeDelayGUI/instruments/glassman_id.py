"""
glassman_id.py

Tells the two Glassman / XP Power WJ supplies apart by the firmware revision
their controllers answer, confirms each one speaks the WJ serial protocol,
and returns their COM ports.

Requires pyserial:  pip install pyserial

Lives in ScopeDelayGUI/instruments/ so the GUI can import it.

Usage (run from the ScopeDelayGUI folder):
    python instruments/glassman_id.py --scan    list every WJ candidate with serial, location, firmware
    python instruments/glassman_id.py           resolve POS and NEG to COM ports by firmware
    python instruments/glassman_id.py --status  resolve, then read voltage, current and status once

In the GUI (utils/connect_memory.py resolves WJ1=NEG, WJ2=POS this way, and
gui/main_window.py assigns each port at connect the same way):
    from instruments.glassman_id import find_supplies
    ports = find_supplies()          # {"POS": "COM16", "NEG": "COM13"} -- COM numbers change
"""

import argparse
import sys

import serial
from serial.tools import list_ports


# ---------------------------------------------------------------------------
# Identity is the firmware revision, nothing else.
#
#   firmware 15  NEG  WJ1 (negative supply)
#   firmware 14  POS  WJ2 (positive supply)
#
# Neither the COM number nor the USB serial identifies a supply. COM numbers
# move with cables and hub ports. The two USB links report different serials
# ("TUSB3410________" and ""), but evidence from 2026-09-24 shows that serial
# follows the USB adapter or cable, not the supply: the "TUSB3410________"
# link answered firmware 15 on 2026-09-23 and firmware 14 the next morning.
# A firmware revision cannot move between units, so it is the identity, and
# the ports are matched to it at every connect.
#
# Limits: two units with equal firmware would be indistinguishable, and a
# serviced or reflashed supply changes its firmware; both fail loud here and
# must be re-entered deliberately. Confirm POS with the front-panel polarity
# LED before trusting this table.
# ---------------------------------------------------------------------------
FIRMWARE_UNITS = {"15": "NEG", "14": "POS"}

SUPPLIES = {
    "POS": {"vid": 0x0451, "pid": 0x3410, "firmware": "14", "rated_kv": None, "rated_ma": None},
    "NEG": {"vid": 0x0451, "pid": 0x3410, "firmware": "15", "rated_kv": None, "rated_ma": None},
}

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
def unit_for_firmware(fw):
    """'NEG', 'POS', or None for a firmware that is neither 15 nor 14."""
    return FIRMWARE_UNITS.get(fw)


def find_supplies(verify=True):
    """Return {"POS": "COMx", "NEG": "COMy"} from the firmware each candidate
    port answers. Raise if anything is ambiguous.

    Every candidate USB port is asked for its version. A port with no WJ
    reply is skipped. A firmware that is neither 14 nor 15 raises IOError;
    two ports with the same firmware raise LookupError, as does a missing
    supply. `verify` is accepted for the old call signature; the version is
    always read, since it is the identity.
    """
    result = {}
    seen = {}
    for p in sorted(list_ports.comports(), key=lambda p: p.device):
        if (p.vid, p.pid) not in CANDIDATE_IDS:
            continue
        fw = read_version(p.device)
        if fw is None:
            continue
        name = unit_for_firmware(fw)
        if name is None:
            raise IOError(f"{p.device} answers WJ firmware {fw}, which is neither "
                          "14 (POS, WJ2) nor 15 (NEG, WJ1).")
        if name in result:
            raise LookupError(f"{result[name]} and {p.device} both answer WJ firmware {fw}: "
                              "the supplies cannot be told apart. Check the cables.")
        result[name] = p.device
        seen[p.device] = fw
    missing = [name for name in SUPPLIES if name not in result]
    if missing:
        raise LookupError(f"{', '.join(missing)}: no port answered WJ firmware "
                          f"{', '.join(SUPPLIES[n]['firmware'] for n in missing)}"
                          + (f" (found {seen})" if seen else ""))
    return result


def scan():
    found = [p for p in sorted(list_ports.comports(), key=lambda p: p.device)
             if (p.vid, p.pid) in CANDIDATE_IDS]
    if not found:
        print("No candidate ports found.")
        return
    for p in found:
        fw = read_version(p.device)
        unit = unit_for_firmware(fw) if fw else None
        label = f"WJ firmware {fw} ({unit or 'unknown'})" if fw else "no WJ reply"
        print(f"{p.device:<7} {label:<26} vid={p.vid:04X} pid={p.pid:04X} "
              f"serial={p.serial_number!r} location={p.location!r}")
    print("\nFirmware 15 is NEG (WJ1), 14 is POS (WJ2). Check the polarity LED on each supply.")


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
