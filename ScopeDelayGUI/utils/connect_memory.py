# utils/connect_memory.py
import json
import os

import serial.tools.list_ports

MEM_FILE = "connection_memory.json"

default_data = {
    "DG535_COM": "COM4",
    "BNC575_COM": "COM5",
    "WJ1_COM": "COM13",
    "WJ2_COM": "COM16",
    "RELAY_COM": "COM7",
    "CFR_LASER_COM": "COM6",
    "CFR_LASER2_COM": "COM8",

    # The scopes are on the instrument network (VXI-11 over Ethernet), not USB.
    "Rigol1_VISA": "TCPIP0::192.168.10.51::INSTR",
    "Rigol2_VISA": "TCPIP0::192.168.10.52::INSTR",
    "Rigol3_VISA": "TCPIP0::192.168.10.53::INSTR",
}

# --------------------------------------------------------------------------
# Never hardcode COM numbers: Windows reassigns them on replug or power
# cycle. Every device is matched by USB identity instead, and resolve_ports()
# rewrites the COM values to wherever each device currently lives.
#
# The two WJ supplies are NOT in the table below. They are resolved by
# instruments/glassman_id.py, which matches each supply by the USB serial its
# own TUSB3410 chip reports (one "TUSB3410________", the other empty). That
# serial follows the supply to any USB socket; hub location does not, and has
# been observed swapping between these two supplies.
#
# To (re)learn signatures for new hardware, run:  python -m utils.connect_memory
# and copy the printed values in here.
#
# Fields:
#   vid      : USB vendor id  (int)          -- required
#   pid      : USB product id (int)          -- required
#   serial   : exact serial_number to match  -- use it when the adapter has a
#              unique one (e.g. the two FTDI cables for DG535 and BNC575).
#   location : USB port path, e.g. "1-13.1.2" -- last resort, for identical
#              adapters with no usable serial. Tied to the physical socket, so
#              it breaks if the cable or hub wiring moves.
# --------------------------------------------------------------------------
DEVICE_SIGNATURES = {
    "DG535_COM":        {"vid": 0x0403, "pid": 0x6001, "serial": "PXA9SEVMA"},
    "BNC575_COM":       {"vid": 0x0403, "pid": 0x6001, "serial": "AG0JQ9JNA"},
    "RELAY_COM":        {"vid": 0x2A19, "pid": 0x0C01, "serial": "NLRL260303R0290"},
    # Two Prolific USB-serial adapters (the CFR lasers) are on this PC and
    # neither reports a serial, so a VID:PID match is ambiguous and resolves to
    # nothing; the remembered COM number is used. They were seen at locations
    # 1-13.1.2 and 1-13.1.4 -- add "location" here once it is known which
    # adapter belongs to which laser.
    "CFR_LASER_COM":    {"vid": 0x067B, "pid": 0x2303},
}


def _port_location(p):
    """USB port path without the interface suffix ("1-13.1.2:x.0" -> "1-13.1.2")."""
    return (p.location or "").split(":")[0]


def _find_port_for_signature(sig, ports):
    """Return the COM device string for a signature, or None if not present.

    1. serial and/or location: exact match only, with no fallback. "The only
       device left with this VID:PID" is how you connect to the wrong unit.
    2. With neither, accept a VID+PID match only when exactly ONE port has
       that VID:PID (otherwise it's ambiguous and we refuse to guess).
    """
    vid, pid = sig.get("vid"), sig.get("pid")
    candidates = [p for p in ports if p.vid == vid and p.pid == pid]
    want_serial = sig.get("serial")
    want_location = sig.get("location")

    if want_serial or want_location:
        for p in candidates:
            if want_serial and p.serial_number != want_serial:
                continue
            if want_location and _port_location(p) != want_location:
                continue
            return p.device
        return None

    if len(candidates) == 1:
        return candidates[0].device

    return None


def _resolve_wj_supplies(data):
    """Resolve both WJ supplies by USB serial (see instruments/glassman_id.py).

    WJ1 is the NEGATIVE supply, WJ2 the POSITIVE one, matching the panel
    labels. If either is missing, unpowered or ambiguous, find_supplies()
    raises and the remembered COM values are left alone rather than guessed at.
    """
    try:
        from instruments.glassman_id import find_supplies
        found = find_supplies()
    except Exception as e:
        print(f"[connect_memory] WJ supplies not resolved ({e}); keeping remembered ports")
        return
    data["WJ1_COM"] = found["NEG"]
    data["WJ2_COM"] = found["POS"]


def resolve_ports(data):
    """Rewrite *_COM values in `data` to the live port for each known device.

    Devices that aren't currently connected keep their remembered COM value
    so nothing breaks if a device is simply unplugged.
    """
    ports = list(serial.tools.list_ports.comports())
    for key, sig in DEVICE_SIGNATURES.items():
        found = _find_port_for_signature(sig, ports)
        if found:
            data[key] = found
    _resolve_wj_supplies(data)
    return data


def load_memory(resolve=True):
    """Load remembered connections, then (by default) resolve serial devices
    to their current COM ports by USB identity."""
    if not os.path.exists(MEM_FILE):
        data = default_data.copy()
    else:
        try:
            with open(MEM_FILE, "r") as f:
                data = {**default_data, **json.load(f)}
        except Exception:
            data = default_data.copy()

    if resolve:
        data = resolve_ports(data)
    return data


def save_memory(key, value):
    """Update one field in memory and write file.

    Note: we save the resolved COM number as a fallback for when the device
    isn't connected, but on next load the live USB match takes priority.
    """
    # Load WITHOUT resolving so we persist the raw remembered table, then
    # overwrite the single key the caller asked us to save.
    data = load_memory(resolve=False)
    data[key] = value
    with open(MEM_FILE, "w") as f:
        json.dump(data, f, indent=2)


if __name__ == "__main__":
    # Discovery helper: list every serial port with the identifiers you need
    # to fill in DEVICE_SIGNATURES. WJ firmware is read (read-only V command)
    # from ports whose VID:PID is a WJ supply.
    from instruments.glassman_id import read_version

    print(f"{'PORT':<8} {'VID:PID':<12} {'SERIAL':<26} {'LOCATION':<14} {'WJ FW':<6} DESCRIPTION")
    print("-" * 103)
    for p in serial.tools.list_ports.comports():
        vidpid = f"{p.vid:04X}:{p.pid:04X}" if p.vid else "-"
        fw = read_version(p.device) if (p.vid, p.pid) == (0x0451, 0x3410) else None
        print(f"{p.device:<8} {vidpid:<12} {str(p.serial_number):<26} "
              f"{_port_location(p) or '-':<14} {fw or '-':<6} {p.description}")
