"""
Benchmark a Rigol scope link: USB TMC vs LAN (VXI-11 or raw socket).

Run it once per scope on USB, then again on Ethernet, and compare the JSON
files. It measures the two numbers that actually decide the question:

  ROUND-TRIP LATENCY  how long one short query costs. A full 4-channel read
                      spends most of its time here, not moving bytes, so this
                      is usually what decides whether a link feels fast.

  BULK THROUGHPUT     MB/s on a large :WAVeform:DATA? transfer. This is the
                      number people expect to matter. It usually does not.

NON-DESTRUCTIVE. This script never sends :SINGle, :RUN or :AUTO. It reads
whatever the scope is already holding, so it is safe to run on a live shot.
It sends :STOP only when the scope is not already stopped, which RAW mode
requires and which does not clear acquisition memory.

Usage:
    python bench_scope_link.py "USB0::0x1AB1::0x0514::DS7A232900210::0::INSTR" --tag r1-usb
    python bench_scope_link.py "TCPIP0::192.168.1.51::INSTR"                   --tag r1-lan
    python bench_scope_link.py --compare bench_r1-usb.json bench_r1-lan.json
"""

import argparse
import json
import statistics
import sys
import time


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

def open_link(resource, timeout_ms=30000):
    """Open a VISA session. Works for USB TMC, TCPIP INSTR and TCPIP SOCKET."""
    import pyvisa

    rm = pyvisa.ResourceManager()
    instr = rm.open_resource(resource)
    instr.timeout = timeout_ms
    instr.read_termination = "\n"
    instr.write_termination = "\n"

    # A raw socket session needs an explicit terminator. INSTR sessions do not
    # care, so setting it is harmless either way.
    if "SOCKET" in resource.upper():
        instr.read_termination = "\n"

    return rm, instr


def read_tmc_block(instr, cmd):
    """Send a query and read exactly the byte count the TMC header declares."""
    old = instr.read_termination
    instr.read_termination = None
    try:
        instr.write(cmd)
        head = instr.read_bytes(2)
        if head[0:1] != b"#":
            raise RuntimeError(f"bad TMC header: {head!r}")
        n = int(head[1:2])
        length = int(instr.read_bytes(n))
        data = instr.read_bytes(length)
        try:
            instr.read_bytes(1)          # trailing terminator
        except Exception:
            pass
        return data
    finally:
        instr.read_termination = old


# ---------------------------------------------------------------------------
# Scope helpers
# ---------------------------------------------------------------------------

_SI = {"": 1, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9}


def parse_points(text):
    """Parse ':ACQuire:MDEPth?' replies: '1M', '125M', '1000000', 'AUTO'."""
    import re
    text = (text or "").strip()
    if not text or text.upper() == "AUTO":
        return None
    m = re.fullmatch(r"([0-9.]+(?:[eE][+-]?\d+)?)\s*([kKMG]?)(?:pts)?", text)
    return int(float(m.group(1)) * _SI[m.group(2)]) if m else None


def memory_depth(instr):
    """Total RAW points. Falls back to asking the scope to clamp a huge STOP."""
    try:
        d = parse_points(instr.query(":ACQuire:MDEPth?"))
        if d:
            return d
    except Exception:
        pass
    try:
        instr.write(":WAVeform:STARt 1")
        instr.write(":WAVeform:STOP 1000000000")
        clamped = int(float(instr.query(":WAVeform:STOP?")))
        if clamped > 1:
            return clamped
    except Exception:
        pass
    return 0


def displayed_channels(instr):
    out = []
    for ch in range(1, 5):
        try:
            if instr.query(f":CHANnel{ch}:DISPlay?").strip() in ("1", "ON"):
                out.append(ch)
        except Exception:
            pass
    return out


def ensure_stopped(instr):
    """Stop the scope if it is running. Does not clear acquisition memory."""
    try:
        if instr.query(":TRIGger:STATus?").strip() != "STOP":
            instr.write(":STOP")
            time.sleep(0.2)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Measurements
# ---------------------------------------------------------------------------

def measure_latency(instr, n=200):
    """Time n short queries. This is the per-transaction cost of the link."""
    samples = []
    for _ in range(n):
        t0 = time.perf_counter()
        instr.query(":TRIGger:STATus?")
        samples.append((time.perf_counter() - t0) * 1000.0)

    samples.sort()
    return {
        "samples": n,
        "mean_ms": round(statistics.fmean(samples), 3),
        "median_ms": round(statistics.median(samples), 3),
        "p95_ms": round(samples[int(0.95 * (n - 1))], 3),
        "min_ms": round(samples[0], 3),
        "max_ms": round(samples[-1], 3),
    }


def measure_bulk(instr, channel, total, chunk):
    """Time a full RAW read of one channel and report MB/s."""
    instr.write(f":WAVeform:SOURce CHANnel{channel}")
    instr.write(":WAVeform:MODE RAW")
    instr.write(":WAVeform:FORMat BYTE")

    got = 0
    transfers = 0
    start = 1
    t0 = time.perf_counter()

    while start <= total:
        stop = min(start + chunk - 1, total)
        instr.write(f":WAVeform:STARt {start}")
        instr.write(f":WAVeform:STOP {stop}")
        data = read_tmc_block(instr, ":WAVeform:DATA?")
        transfers += 1
        if not data:
            break
        got += len(data)
        start += len(data)

    elapsed = time.perf_counter() - t0
    mb = got / 1e6

    return {
        "channel": channel,
        "points": got,
        "expected": total,
        "complete": got >= total,
        "chunk_points": chunk,
        "transfers": transfers,
        "seconds": round(elapsed, 3),
        "MB": round(mb, 3),
        "MB_per_s": round(mb / elapsed, 2) if elapsed > 0 else None,
    }


def measure_full_capture(instr, channels, total, chunk):
    """Wall time for a realistic 4-channel read, the way the GUI does it."""
    t0 = time.perf_counter()
    points = {}
    for ch in channels:
        r = measure_bulk(instr, ch, total, chunk)
        points[ch] = r["points"]
    elapsed = time.perf_counter() - t0
    return {
        "channels": list(channels),
        "points_per_channel": points,
        "seconds": round(elapsed, 3),
    }


def count_transactions(n_channels, total, chunk):
    """Round trips one 4-channel read costs, to weigh against latency.

    Per channel: SOURce, MODE, FORMat, STARt, STOP, PREamble?, DISPlay?
    plus STARt, STOP, DATA? per chunk.
    """
    chunks = max(1, -(-total // chunk))
    per_channel = 7 + 3 * chunks
    return per_channel * n_channels


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run(resource, tag, chunk, latency_n, timeout_ms):
    rm, instr = open_link(resource, timeout_ms)
    result = {
        "tag": tag,
        "resource": resource,
        "when": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    try:
        t0 = time.perf_counter()
        idn = instr.query("*IDN?").strip()
        result["idn"] = idn
        result["first_query_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        print(f"Connected: {idn}")

        # Link details, when the scope is on the network.
        if resource.upper().startswith("TCPIP"):
            for cmd, key in ((":LAN:STATus?", "lan_status"),
                             (":LAN:IPADdress?", "lan_ip"),
                             (":LAN:MAC?", "lan_mac"),
                             (":LAN:DHCP?", "lan_dhcp"),
                             (":LAN:VISA?", "lan_visa")):
                try:
                    result[key] = instr.query(cmd).strip()
                except Exception:
                    result[key] = None
            print(f"LAN: {result.get('lan_status')} at {result.get('lan_ip')}, "
                  f"DHCP={result.get('lan_dhcp')}")

        ensure_stopped(instr)

        chans = displayed_channels(instr)
        total = memory_depth(instr)
        result["displayed_channels"] = chans
        result["memory_depth"] = total
        print(f"Channels on: {chans}, memory depth: {total} pts")

        if not chans or total <= 0:
            print("Nothing to read. Turn a channel on and capture a shot first.")
            result["error"] = "no data available"
            return result

        print(f"\nLatency, {latency_n} short queries...")
        result["latency"] = measure_latency(instr, latency_n)
        lat = result["latency"]
        print(f"  median {lat['median_ms']} ms, mean {lat['mean_ms']} ms, "
              f"p95 {lat['p95_ms']} ms")

        print(f"\nBulk read, CH{chans[0]}, {total} pts, {chunk}-pt chunks...")
        result["bulk"] = measure_bulk(instr, chans[0], total, chunk)
        b = result["bulk"]
        print(f"  {b['MB']} MB in {b['seconds']} s = {b['MB_per_s']} MB/s "
              f"over {b['transfers']} transfers")
        if not b["complete"]:
            print(f"  WARNING: got {b['points']} of {b['expected']} points")

        print(f"\nFull capture, {len(chans)} channels...")
        result["full_capture"] = measure_full_capture(instr, chans, total, chunk)
        print(f"  {result['full_capture']['seconds']} s")

        # How much of that time was spent on round trips rather than bytes.
        txn = count_transactions(len(chans), total, chunk)
        overhead_s = txn * lat["median_ms"] / 1000.0
        wall = result["full_capture"]["seconds"]
        result["transactions"] = txn
        result["latency_overhead_s"] = round(overhead_s, 3)
        result["latency_overhead_pct"] = round(100 * overhead_s / wall, 1) if wall else None
        print(f"  {txn} round trips, about {overhead_s:.2f} s of that "
              f"({result['latency_overhead_pct']}%) is link latency")

        return result

    finally:
        try:
            instr.close()
            rm.close()
        except Exception:
            pass


def compare(paths):
    runs = []
    for p in paths:
        with open(p) as f:
            runs.append(json.load(f))

    print(f"\n{'':<26}" + "".join(f"{r['tag']:>18}" for r in runs))
    print("-" * (26 + 18 * len(runs)))

    def row(label, fn):
        cells = []
        for r in runs:
            try:
                v = fn(r)
            except Exception:
                v = None
            cells.append(f"{v if v is not None else '-':>18}")
        print(f"{label:<26}" + "".join(cells))

    row("median latency (ms)", lambda r: r["latency"]["median_ms"])
    row("p95 latency (ms)", lambda r: r["latency"]["p95_ms"])
    row("bulk throughput (MB/s)", lambda r: r["bulk"]["MB_per_s"])
    row("1 channel (s)", lambda r: r["bulk"]["seconds"])
    row("full capture (s)", lambda r: r["full_capture"]["seconds"])
    row("round trips", lambda r: r["transactions"])
    row("latency share (%)", lambda r: r["latency_overhead_pct"])

    print()
    fastest = min(runs, key=lambda r: r["full_capture"]["seconds"])
    slowest = max(runs, key=lambda r: r["full_capture"]["seconds"])
    if fastest is not slowest:
        gain = slowest["full_capture"]["seconds"] / fastest["full_capture"]["seconds"]
        print(f"{fastest['tag']} is {gain:.2f}x faster than {slowest['tag']} "
              f"on a full capture.")

    # The judgement that matters: is the link latency-bound or bandwidth-bound?
    for r in runs:
        share = r.get("latency_overhead_pct")
        if share is None:
            continue
        if share > 50:
            print(f"{r['tag']}: latency-bound. Bigger chunks will help more "
                  f"than a faster link.")
        else:
            print(f"{r['tag']}: bandwidth-bound. A faster link would help.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("resource", nargs="?", help="VISA resource string")
    ap.add_argument("--tag", default="run", help="label for the output file")
    ap.add_argument("--chunk", type=int, default=250000,
                    help="points per transfer (default 250000)")
    ap.add_argument("--latency-n", type=int, default=200,
                    help="short queries to time (default 200)")
    ap.add_argument("--timeout", type=int, default=30000, help="VISA timeout ms")
    ap.add_argument("--compare", nargs="+", metavar="JSON",
                    help="compare saved runs instead of measuring")
    args = ap.parse_args()

    if args.compare:
        compare(args.compare)
        return 0

    if not args.resource:
        ap.error("give a VISA resource string, or --compare some JSON files")

    result = run(args.resource, args.tag, args.chunk, args.latency_n, args.timeout)

    out = f"bench_{args.tag}.json"
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())