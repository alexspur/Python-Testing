"""
laser_id.py

Identifies the two Quantel CFR lasers (ICE450 controllers) on Prolific PL2303
USB-to-serial adapters (VID 067B, PID 2303).

The Prolific adapters are identical and have no serial number, so the script asks
each laser for its factory flashlamp shot count (F command). That count never
resets and only goes up. LASER1 has far more shots than LASER2, so a fixed
threshold tells them apart on any USB port and any COM number.

Requires pyserial:  pip install pyserial

Usage:
    python laser_id.py --scan
        Show shot count, state and USB location for each Prolific port.

    python laser_id.py
        Resolve LASER1 and LASER2 to COM ports.

In your GUI (call before your GUI opens the laser ports):
    from laser_id import find_lasers
    ports = find_lasers()        # {"LASER1": "COM8", "LASER2": "COM6"}

Serial settings from the CFR manual: 9600 baud, 8N1, no flow control, commands
end with CR LF, about 150 ms between commands. If someone presses a Remote Box
button, the serial link turns OFF. Turn it back on in the Remote Box System menu.
"""

import argparse
import re
import sys
import time

import serial
from serial.tools import list_ports


VID = 0x067B
PID = 0x2303
LASER_NAMES = ("LASER1", "LASER2")

# LASER1 had 17,546 shots and LASER2 had 37 shots on 2026-09-23.
# LASER2 will stay well below LASER1, so a fixed threshold separates them.
# A count in the gap between the two numbers raises an error.
LASER1_MIN_SHOTS = 17_000
LASER2_MAX_SHOTS = 15_000

BAUD = 9600
TIMEOUT = 1.0
CMD_GAP = 0.15

# Only these commands are ever sent. Both are read-only queries.
# Never add A, E, M, S, CC or OP. Those fire or stop the laser.
SAFE_QUERIES = {"F", "ST"}


# ---------------------------------------------------------------------------
# ICE450 queries
# ---------------------------------------------------------------------------
def ice_query(s, cmd):
    if cmd not in SAFE_QUERIES:
        raise ValueError(f"Refusing to send {cmd!r}. Only {sorted(SAFE_QUERIES)} are allowed.")
    s.reset_input_buffer()
    s.write(cmd.encode() + b"\r\n")
    time.sleep(CMD_GAP)
    deadline = time.time() + TIMEOUT
    buf = b""
    while time.time() < deadline:
        chunk = s.read(64)
        if chunk:
            buf += chunk
            deadline = time.time() + 0.1
        elif buf:
            break
    return buf.decode(errors="ignore").strip()


def read_laser(port):
    """Return {"shots", "state", "raw_f", "error"} for one port."""
    out = {"shots": None, "state": None, "raw_f": None, "error": None}
    try:
        with serial.Serial(port, BAUD, bytesize=8, parity="N", stopbits=1,
                           timeout=0.1, xonxoff=False, rtscts=False) as s:
            f = ice_query(s, "F")
            time.sleep(CMD_GAP)
            st = ice_query(s, "ST")
    except serial.SerialException as e:
        out["error"] = f"could not open ({e}). Close any program that has this port open."
        return out
    out["raw_f"] = f
    out["state"] = st or None
    m = re.search(r"LP\s*(\d+)", f)
    if m:
        out["shots"] = int(m.group(1))
    else:
        out["error"] = "no shot count reply. Check the laser is on and the serial link is ON."
    return out


def gather():
    rows = []
    for p in sorted(list_ports.comports(), key=lambda p: p.device):
        if (p.vid, p.pid) != (VID, PID):
            continue
        row = {"device": p.device, "location": p.location}
        row.update(read_laser(p.device))
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Resolve
# ---------------------------------------------------------------------------
def classify(shots):
    if shots >= LASER1_MIN_SHOTS:
        return "LASER1"
    if shots < LASER2_MAX_SHOTS:
        return "LASER2"
    return None


def find_lasers():
    """Return {"LASER1": "COMx", "LASER2": "COMy"}. Raise instead of guessing."""
    rows = [r for r in gather() if r["shots"] is not None]
    if len(rows) != len(LASER_NAMES):
        raise LookupError(f"Expected {len(LASER_NAMES)} lasers answering, found {len(rows)}. "
                          f"Run --scan to see which port is missing.")
    result = {}
    for r in rows:
        name = classify(r["shots"])
        if name is None:
            raise LookupError(f"{r['device']} has {r['shots']:,} shots, between "
                              f"LASER2_MAX_SHOTS and LASER1_MIN_SHOTS. Check the lasers "
                              f"and the thresholds.")
        if name in result:
            raise LookupError(f"Both {result[name]} and {r['device']} look like {name}. "
                              f"Check the lasers and the thresholds.")
        result[name] = r["device"]
    return {n: result[n] for n in LASER_NAMES}


def scan():
    rows = gather()
    if not rows:
        print("No Prolific ports found. Check that both lasers are connected.")
        return
    for r in rows:
        shots = f"{r['shots']:,}" if r["shots"] is not None else None
        print(f"{r['device']:<6} shots={shots}  state={r['state']!r}  "
              f"location={r['location']}  {r['error'] or ''}")
    print(f"\nLASER1 needs >= {LASER1_MIN_SHOTS:,} shots. LASER2 needs < {LASER2_MAX_SHOTS:,} shots.")


def main():
    ap = argparse.ArgumentParser(description="Identify the Quantel CFR lasers.")
    ap.add_argument("--scan", action="store_true", help="show shot count per port")
    args = ap.parse_args()

    if args.scan:
        scan()
    else:
        try:
            for name, dev in find_lasers().items():
                print(f"{name}: {dev}")
        except LookupError as e:
            print(f"ERROR: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()