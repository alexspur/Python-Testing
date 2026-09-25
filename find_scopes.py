"""
Find Rigol scopes on the instrument subnet and emit their VISA strings.

Run this after you give each scope a static IP. It scans the subnet, opens a
VISA session to anything that answers, and prints the exact resource string to
paste into connect_memory.py. It also reports each scope's LAN status, so a
half-configured scope shows up as a problem rather than a silent no-show.

NON-DESTRUCTIVE. It only sends *IDN? and :LAN: queries. It never touches
acquisition state, so it is safe to run mid-campaign.

It also reports non-VISA devices on the segment, so one run tells you whether
the whole instrument island is healthy: router, Opta and all three scopes.

Usage:
    python find_scopes.py 192.168.10.0/24
    python find_scopes.py 192.168.10.51 192.168.10.52 192.168.10.53
    python find_scopes.py 192.168.10.0/24 --emit
"""

import argparse
import concurrent.futures as cf
import ipaddress
import socket
import sys

# VXI-11 instruments answer the RPC portmapper on 111. Probing that first is
# far quicker than opening a VISA session to every dead address on the subnet.
PORTMAP_PORT = 111
SOCKET_PORT = 5555
MODBUS_PORT = 502      # Arduino Opta and other Modbus TCP devices
HTTP_PORTS = (80, 443)  # EdgeRouter web UI, scope LXI page


def expand(targets):
    """Turn CIDR blocks and bare addresses into a flat list of IP strings."""
    out = []
    for t in targets:
        if "/" in t:
            net = ipaddress.ip_network(t, strict=False)
            out.extend(str(ip) for ip in net.hosts())
        else:
            out.append(t)
    return out


def port_open(ip, port, timeout=0.3):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False


def probe(ip, timeout=0.3):
    """Cheap TCP check. Returns which instrument ports answered."""
    return {
        "ip": ip,
        "vxi11": port_open(ip, PORTMAP_PORT, timeout),
        "socket": port_open(ip, SOCKET_PORT, timeout),
        "modbus": port_open(ip, MODBUS_PORT, timeout),
        "http": any(port_open(ip, p, timeout) for p in HTTP_PORTS),
    }


def interrogate(ip, timeout_ms=5000):
    """Open a VISA session and ask the instrument who and where it is."""
    import pyvisa

    resource = f"TCPIP0::{ip}::INSTR"
    rm = pyvisa.ResourceManager()
    info = {"ip": ip, "resource": resource}
    instr = None
    try:
        instr = rm.open_resource(resource)
        instr.timeout = timeout_ms
        instr.read_termination = "\n"
        instr.write_termination = "\n"

        info["idn"] = instr.query("*IDN?").strip()

        for cmd, key in ((":LAN:STATus?", "lan_status"),
                         (":LAN:MAC?", "mac"),
                         (":LAN:DHCP?", "dhcp"),
                         (":LAN:VISA?", "visa"),
                         (":ACQuire:MDEPth?", "mdepth"),
                         (":TRIGger:STATus?", "trig")):
            try:
                info[key] = instr.query(cmd).strip()
            except Exception:
                info[key] = None

        # A scope still on DHCP will move. Flag it here, not during a campaign.
        if info.get("dhcp") in ("1", "ON"):
            info["warning"] = "DHCP is ON, this address can change"

        return info
    except Exception as e:
        info["error"] = str(e)
        return info
    finally:
        try:
            if instr is not None:
                instr.close()
            rm.close()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("targets", nargs="+",
                    help="CIDR block (192.168.2.0/24) or explicit addresses")
    ap.add_argument("--emit", action="store_true",
                    help="print a connect_memory.py default_data block")
    ap.add_argument("--timeout", type=float, default=0.3,
                    help="TCP probe timeout in seconds (default 0.3)")
    ap.add_argument("--workers", type=int, default=64)
    args = ap.parse_args()

    ips = expand(args.targets)
    print(f"Probing {len(ips)} address(es)...")

    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        probes = list(pool.map(lambda ip: probe(ip, args.timeout), ips))

    live = [p for p in probes
            if p["vxi11"] or p["socket"] or p["modbus"] or p["http"]]
    if not live:
        print("\nNothing answered on the instrument ports.")
        print("Check cabling, that the scope LAN icon is lit, and that the PC")
        print("and the scopes are on the same subnet with the same mask.")
        return 1

    # VISA devices get interrogated. Everything else is reported as-is, so the
    # Opta and the router show up and you can see the whole segment at once.
    visa_hosts = [p for p in live if p["vxi11"] or p["socket"]]
    other_hosts = [p for p in live if p not in visa_hosts]

    print(f"{len(live)} device(s) answered "
          f"({len(visa_hosts)} VISA). Interrogating...\n")

    found = []
    for p in visa_hosts:
        info = interrogate(p["ip"])
        info["socket_port_open"] = p["socket"]
        found.append(info)

    scopes = []
    for info in found:
        ip = info["ip"]
        if "error" in info:
            print(f"{ip:<16} no VISA response: {info['error']}")
            continue

        idn = info.get("idn", "")
        print(f"{ip:<16} {idn}")
        print(f"{'':<16} resource     {info['resource']}")
        if info.get("visa"):
            print(f"{'':<16} scope says   {info['visa']}")
        print(f"{'':<16} LAN          {info.get('lan_status')}  "
              f"MAC {info.get('mac')}  DHCP {info.get('dhcp')}")
        print(f"{'':<16} state        {info.get('trig')}  "
              f"depth {info.get('mdepth')}")
        if info.get("socket_port_open"):
            print(f"{'':<16} raw socket   TCPIP0::{ip}::{SOCKET_PORT}::SOCKET "
                  f"is open, worth benchmarking")
        if info.get("warning"):
            print(f"{'':<16} WARNING      {info['warning']}")
        print()

        if "RIGOL" in idn.upper():
            # Serial number is the third comma-separated field of *IDN?.
            parts = [x.strip() for x in idn.split(",")]
            scopes.append({
                "ip": ip,
                "resource": info["resource"],
                "serial": parts[2] if len(parts) > 2 else "",
            })

    if other_hosts:
        print("Other devices on this segment:")
        for p in other_hosts:
            kinds = []
            if p["modbus"]:
                kinds.append(f"Modbus TCP :{MODBUS_PORT} (Opta?)")
            if p["http"]:
                kinds.append("web UI")
            print(f"{p['ip']:<16} {', '.join(kinds)}")
        print()

    if args.emit and scopes:
        emit(scopes)

    return 0


# Serial number to scope number, taken from the USB resource strings already in
# connect_memory.py. Keeping this mapping is what stops a switch to Ethernet
# from silently renumbering the scopes and mislabelling every CSV afterwards.
# If you add or replace a scope, update this.
KNOWN_SERIALS = {
    "DS7A232900210": 1,
    "DS7A230800035": 2,
    "DS7A233300256": 3,
}


def emit(scopes):
    """Print a connect_memory.py block, preserving the existing numbering."""
    assigned = {}
    unknown = []

    for s in scopes:
        n = KNOWN_SERIALS.get(s["serial"])
        if n is None:
            unknown.append(s)
        else:
            assigned[n] = s

    # Give anything unrecognised the lowest free number, and say so loudly.
    next_n = 1
    for s in sorted(unknown, key=lambda x: x["serial"]):
        while next_n in assigned:
            next_n += 1
        assigned[next_n] = s
        s["new"] = True

    print("\nPaste into connect_memory.py default_data:\n")
    for n in sorted(assigned):
        s = assigned[n]
        note = "  <-- UNRECOGNISED SERIAL, CHECK THIS" if s.get("new") else ""
        print(f'    "Rigol{n}_VISA": "{s["resource"]}",'
              f'   # {s["serial"]}{note}')

    missing = sorted(set(KNOWN_SERIALS) - {s["serial"] for s in scopes})
    if missing:
        print("\nNot found on the network:")
        for serial in missing:
            print(f"    Rigol{KNOWN_SERIALS[serial]}  {serial}")

    if unknown:
        print("\nOne or more serials are not in KNOWN_SERIALS. Confirm which")
        print("physical scope each one is before you trust the numbering.")


if __name__ == "__main__":
    sys.exit(main())
