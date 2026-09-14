# utils/connect_memory.py
import json
import os

import serial.tools.list_ports

MEM_FILE = "connection_memory.json"

default_data = {
    "DG535_COM": "COM4",
    "BNC575_COM": "COM5",
    "Arduino_COM": "COM9",
    "WJ1_COM": "COM6",
    "WJ2_COM": "COM8",
    "RELAY_COM": "COM7",
    "CFR_LASER_COM": "COM18",

    "Rigol1_VISA": "USB0::0x1AB1::0x0514::DS7A232900210::0::INSTR",
    "Rigol2_VISA": "USB0::0x1AB1::0x0514::DS7A230800035::0::INSTR",
    "Rigol3_VISA": "USB0::0x1AB1::0x0514::DS7A233300256::0::INSTR",
}

# --------------------------------------------------------------------------
# Stable hardware signatures for each serial device.
#
# Windows reassigns COM numbers across replug/reboot, so remembering the
# last COM number is unreliable. Instead we match each logical device to a
# physical device by its VID:PID plus whatever identifies it: USB serial
# number, instrument firmware, or USB port location. resolve_ports() scans
# the live port list and rewrites the COM values to wherever each device
# currently lives.
#
# To (re)learn signatures for new hardware, run:  python -m utils.connect_memory
# and copy the printed values in here.
#
# Fields:
#   vid         : USB vendor id  (int)          -- required
#   pid         : USB product id (int)          -- required
#   serial      : exact serial_number to match  -- use it when the adapter has
#                 a unique one (e.g. the two FTDI cables for DG535 and BNC575).
#   wj_firmware : version a WJ supply reports to the read-only V command.
#                 Identifies the supply itself, in any USB socket.
#   location    : USB port path, e.g. "1-13.1.3" -- for identical adapters with
#                 no usable serial. Tied to the physical socket.
# --------------------------------------------------------------------------
DEVICE_SIGNATURES = {
    "DG535_COM":        {"vid": 0x0403, "pid": 0x6001, "serial": "PXA9SEVMA"},
    "BNC575_COM":       {"vid": 0x0403, "pid": 0x6001, "serial": "AG0JQ9JNA"},
    "RELAY_COM":        {"vid": 0x2A19, "pid": 0x0C01, "serial": "NLRL260303R0290"},
    "Arduino_COM":      {"vid": 0x2341, "pid": 0x025B, "serial": "0035002A3132511539313731"},
    # Both WJ supplies use the same TI TUSB3410 bridge and neither USB serial
    # is usable (one reads "TUSB3410________", the other is blank). They are
    # identified by WJ firmware version, so either can go in any USB socket.
    # location is the fallback for a supply that doesn't answer (powered off,
    # port held by another program). Identified 2026-09-14 by unplugging the
    # negative supply. If a supply is serviced or reflashed, update its version.
    "WJ1_COM":          {"vid": 0x0451, "pid": 0x3410, "wj_firmware": "14", "location": "1-13.4.4.3.4"},  # negative
    "WJ2_COM":          {"vid": 0x0451, "pid": 0x3410, "wj_firmware": "15", "location": "1-13.4.4.3.2"},  # positive
    # Prolific USB-serial adapter has no serial number, so match on VID:PID
    # alone (works as long as it's the only Prolific adapter plugged in).
    "CFR_LASER_COM":    {"vid": 0x067B, "pid": 0x2303},
}


def _port_location(p):
    """USB port path without the interface suffix ("1-13.1.3:x.0" -> "1-13.1.3")."""
    return (p.location or "").split(":")[0]


def _wj_firmware(port):
    """Firmware version a WJ supply on `port` reports to the read-only V
    command, or None if nothing answers (not a WJ, powered off, port busy)."""
    from instruments.wj import WJPowerSupply   # only needed for WJ signatures
    wj = WJPowerSupply()
    try:
        wj.connect(port)
        ver = wj.get_version()
    except Exception:
        return None
    finally:
        wj.close()
    return ver.get("version") if ver.get("type") == "B" else None


def _find_port_for_signature(sig, ports, firmware_cache):
    """Return the COM device string for a signature, or None if not present.

    1. wj_firmware: ask each port with this VID:PID for its version and take
       the one that matches. firmware_cache keeps it to one probe per port.
    2. serial and/or location: exact match only. A port that answered with a
       different WJ firmware is a known other supply and is skipped.
    3. With no identity fields, accept a VID+PID match only when exactly ONE
       port has that VID:PID (otherwise it's ambiguous and we refuse to guess).

    With any identity field there is no VID:PID fallback: with one of two
    identical WJ supplies unplugged, "the only TUSB3410 left" would be the
    other supply.
    """
    vid, pid = sig.get("vid"), sig.get("pid")
    candidates = [p for p in ports if p.vid == vid and p.pid == pid]
    want_firmware = sig.get("wj_firmware")
    want_serial = sig.get("serial")
    want_location = sig.get("location")

    if want_firmware:
        for p in candidates:
            if p.device not in firmware_cache:
                firmware_cache[p.device] = _wj_firmware(p.device)
            if firmware_cache[p.device] == want_firmware:
                return p.device

    if want_firmware or want_serial or want_location:
        if want_serial or want_location:
            for p in candidates:
                if want_serial and p.serial_number != want_serial:
                    continue
                if want_location and _port_location(p) != want_location:
                    continue
                if want_firmware and firmware_cache.get(p.device) is not None:
                    continue
                return p.device
        return None

    if len(candidates) == 1:
        return candidates[0].device

    return None


def resolve_ports(data):
    """Rewrite *_COM values in `data` to the live port for each known device.

    Devices that aren't currently connected keep their remembered COM value
    so nothing breaks if a device is simply unplugged.
    """
    ports = list(serial.tools.list_ports.comports())
    firmware_cache = {}
    for key, sig in DEVICE_SIGNATURES.items():
        found = _find_port_for_signature(sig, ports, firmware_cache)
        if found:
            data[key] = found
    return data


def load_memory(resolve=True):
    """Load remembered connections, then (by default) resolve serial devices
    to their current COM ports by signature."""
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
    # to fill in DEVICE_SIGNATURES. WJ firmware is asked only on ports whose
    # VID:PID belongs to a WJ signature (read-only V command).
    wj_ids = {(s["vid"], s["pid"]) for s in DEVICE_SIGNATURES.values() if "wj_firmware" in s}
    print(f"{'PORT':<8} {'VID:PID':<12} {'SERIAL':<26} {'LOCATION':<14} {'WJ FW':<6} DESCRIPTION")
    print("-" * 103)
    for p in serial.tools.list_ports.comports():
        vidpid = f"{p.vid:04X}:{p.pid:04X}" if p.vid else "-"
        fw = _wj_firmware(p.device) if (p.vid, p.pid) in wj_ids else None
        print(f"{p.device:<8} {vidpid:<12} {str(p.serial_number):<26} "
              f"{_port_location(p) or '-':<14} {fw or '-':<6} {p.description}")
