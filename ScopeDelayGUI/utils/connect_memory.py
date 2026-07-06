# utils/connect_memory.py
import json
import os

import serial.tools.list_ports

MEM_FILE = "connection_memory.json"

default_data = {
    "DG535_COM": "COM4",
    "BNC575_COM": "COM5",
    "Arduino_COM": "COM9",
    "WJ_COM": "COM6",
    "WJ1_COM": "COM6",
    "WJ2_COM": "COM7",
    "RELAY_COM": "COM7",
    "Glassman_Mega_COM": "COM17",
    "CFR_LASER_COM": "COM18",

    "Rigol1_VISA": "USB0::0x1AB1::0x0514::DS7A232900210::0::INSTR",
    "Rigol2_VISA": "USB0::0x1AB1::0x0514::DS7A230800035::0::INSTR",
    "Rigol3_VISA": "USB0::0x1AB1::0x0514::DS7A233300256::0::INSTR",
}

# --------------------------------------------------------------------------
# Stable USB hardware signatures for each serial device.
#
# Windows reassigns COM numbers across replug/reboot, so remembering the
# last COM number is unreliable. Instead we match each logical device to a
# physical USB device by its VID:PID and (where needed) serial number, which
# never change. resolve_ports() scans the live port list and rewrites the
# COM values to wherever each device currently lives.
#
# To (re)learn signatures for new hardware, run:  python -m utils.connect_memory
# and copy the printed serial numbers in here.
#
# Fields:
#   vid    : USB vendor id  (int)            -- required
#   pid    : USB product id (int)            -- required
#   serial : exact serial_number to match    -- optional but REQUIRED to tell
#            apart two devices that share the same VID:PID (e.g. the two FTDI
#            cables for DG535 and BNC575).
# --------------------------------------------------------------------------
DEVICE_SIGNATURES = {
    "DG535_COM":        {"vid": 0x0403, "pid": 0x6001, "serial": "PXA9SEVMA"},
    "BNC575_COM":       {"vid": 0x0403, "pid": 0x6001, "serial": "AG0JQ9JNA"},
    "WJ_COM":           {"vid": 0x0451, "pid": 0x3410, "serial": "TUSB3410________"},
    "WJ1_COM":          {"vid": 0x0451, "pid": 0x3410, "serial": "TUSB3410________"},
    "RELAY_COM":        {"vid": 0x2A19, "pid": 0x0C01, "serial": "NLRL260303R0290"},
    "WJ2_COM":          {"vid": 0x2A19, "pid": 0x0C01, "serial": "NLRL260303R0290"},
    "Arduino_COM":      {"vid": 0x2341, "pid": 0x025B, "serial": "0035002A3132511539313731"},
    "Glassman_Mega_COM": {"vid": 0x2341, "pid": 0x0042, "serial": "1453230393135111E042"},
    # Prolific USB-serial adapter has no serial number, so match on VID:PID
    # alone (works as long as it's the only Prolific adapter plugged in).
    "CFR_LASER_COM":    {"vid": 0x067B, "pid": 0x2303},
}


def _find_port_for_signature(sig, ports):
    """Return the COM device string for a signature, or None if not present.

    1. Try an exact match on VID + PID + serial number.
    2. If no serial was given (or it didn't match), accept a VID+PID match
       only when exactly ONE port has that VID:PID (otherwise it's ambiguous
       and we refuse to guess).
    """
    vid, pid = sig.get("vid"), sig.get("pid")
    want_serial = sig.get("serial")

    if want_serial:
        for p in ports:
            if p.vid == vid and p.pid == pid and p.serial_number == want_serial:
                return p.device

    vp_matches = [p for p in ports if p.vid == vid and p.pid == pid]
    if len(vp_matches) == 1:
        return vp_matches[0].device

    return None


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
    return data


def load_memory(resolve=True):
    """Load remembered connections, then (by default) resolve serial devices
    to their current COM ports by USB signature."""
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
    isn't connected, but on next load the live signature match takes priority.
    """
    # Load WITHOUT resolving so we persist the raw remembered table, then
    # overwrite the single key the caller asked us to save.
    data = load_memory(resolve=False)
    data[key] = value
    with open(MEM_FILE, "w") as f:
        json.dump(data, f, indent=2)


if __name__ == "__main__":
    # Discovery helper: list every serial port with the identifiers you need
    # to fill in DEVICE_SIGNATURES.
    print(f"{'PORT':<8} {'VID:PID':<12} {'SERIAL':<28} MANUFACTURER")
    print("-" * 70)
    for p in serial.tools.list_ports.comports():
        vidpid = f"{p.vid:04X}:{p.pid:04X}" if p.vid else "-"
        print(f"{p.device:<8} {vidpid:<12} {str(p.serial_number):<28} {p.manufacturer}")
