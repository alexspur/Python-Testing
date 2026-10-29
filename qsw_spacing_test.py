"""
Laser 1 and laser 2 Q-switch spacing test on scope 3. No Marx, no HV.

The laser DG535 is programmed the way the GUI runs it (A = T0 + 0, B = A + B,
C = T0 + 0, D = C + D, external trigger from BNC 575 B) and all four channels
are read back until they hold exactly what was written. A write that fails, a
readback that cannot be read and a readback that does not match are each
written and read again, up to DG_TRIES times, before the test stops. Each shot:

    prep laser 1 and laser 2 with the GUI's own Prep (EXT/EXT)
    confirm both report ARMED, and that B and D still read back as written
    arm scope 3, fire the BNC 575 once
    stop both lasers with the GUI's own Stop
    read CH1 (L1 Q-switch) and CH2 (L2 Q-switch)
    time both Q-switch edges at 50 %: spacing = CH2 - CH1

By default each row of the table gets all its shots before the next row, with
the DG535 written once per row. With --interleave the rows take turns
(1000, 500, 300, 200, 1000, ...) and the DG535 is written and read back
before every shot. The spacing should equal D - B within TOL_NS.

Results go to qsw_test_results/qsw_<date>_<time>/:
    summary.csv           one row per shot (edges, spacing, prep and DG535 checks)
    rows.csv              one row per table row (mean, sd, min, max of the spacing)
    traces_<gap>ns.csv    t_us, then L1_s01..L1_sNN and L2_s01..L2_sNN, volts,
                          cropped around the two edges, for MATLAB (readmatrix)
    traces.png, spacing.png, run.log

Usage (close the GUI first: it holds the instrument ports):
    python qsw_spacing_test.py check          connect and read back only, no fire
    python qsw_spacing_test.py                every row of the table
    python qsw_spacing_test.py 500 300        only those rows
    python qsw_spacing_test.py --shots 5 1000
    python qsw_spacing_test.py --shots 5 --interleave
                                              every row, 5 shots each, rows in turn
"""

import csv
import json
import os
import sys
import time
from datetime import datetime
from types import SimpleNamespace

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
GUI_DIR = os.path.join(HERE, "ScopeDelayGUI")
sys.path.insert(0, HERE)
sys.path.append(GUI_DIR)

# ---------------------------------------------------------------------------
# Things you might change
# ---------------------------------------------------------------------------
SHOTS = 30                # shots per row of the table
TOL_NS = 5.0              # a shot passes when |spacing - (D - B)| <= this

# The spacing table: target output gap (ns) -> (B, D) in us.
TABLE = {
    1000: (180.5755, 181.6458),
    500:  (180.8255, 181.3958),
    300:  (180.9255, 181.2958),
    200:  (180.9755, 181.2458),
}

SCOPE = "3"
CH_L1 = 1                 # scope 3 CH1, L1 Q-switch
CH_L2 = 2                 # scope 3 CH2, L2 Q-switch

# Ports come from connection_memory.json, the GUI's file. The lasers have no
# USB serial number, so their ports are only as good as that file. Override
# here if they swap, e.g. {"laser1": "COM8", "laser2": "COM6"}.
PORT_OVERRIDE = {}
DG_GPIB = 15

RESTORE_DG535 = True      # put B and D back as found when the test ends
SAVE_BEFORE_US = 1.0      # saved traces start this long before the L1 edge
SAVE_AFTER_US = 3.0       # and end this long after the L2 edge
OUT_ROOT = os.path.join(HERE, "qsw_test_results")

DG_MATCH_S = 1e-11        # readback must equal what was written (the GUI's rule)
DG_TRIES = 3              # DG535 write-and-read-back attempts before stopping
ARM_TIMEOUT_S = 5.0       # no scope trigger this long after the fire = missed
MAX_BAD_IN_A_ROW = 3      # stop after this many shots of a row with no spacing
SECONDS_PER_SHOT = 12     # for the time estimate only
SECONDS_PER_DG_WRITE = 3  # likewise, a DG535 write and full readback

SUMMARY_COLS = [
    "seq", "target_gap_ns", "B_us", "D_us", "cmd_spacing_ns", "shot", "time",
    "laser1_st", "laser2_st", "dg_B_us", "dg_D_us", "dg_ok", "dg_tries", "triggered",
    "l1_t50_us", "l2_t50_us", "spacing_ns", "spacing_minus_cmd_ns", "within_tol",
    "l1_amp_v", "l2_amp_v", "l1_rise_ns", "l2_rise_ns", "note",
]
ROW_COLS = [
    "target_gap_ns", "B_us", "D_us", "cmd_spacing_ns", "shots", "good",
    "within_tol", "spacing_mean_ns", "spacing_sd_ns", "spacing_min_ns",
    "spacing_max_ns", "mean_minus_cmd_ns", "l1_sd_ps", "l2_sd_ps",
]

LOG = None
EARLY = []                # lines printed before run.log exists


def say(msg=""):
    print(msg)
    if LOG is None:
        EARLY.append(msg)
    else:
        LOG.write(msg + "\n")
        LOG.flush()


class Abort(Exception):
    """Stop the test. The lasers are stopped and everything so far is saved."""


def find_ports():
    """The GUI's remembered ports, with the DG535 and BNC 575 resolved by USB
    identity (utils/connect_memory.py, run from this folder like the GUI)."""
    from utils.connect_memory import load_memory
    m = load_memory()
    p = {"dg535": m.get("DG535_COM"), "bnc": m.get("BNC575_COM"),
         "laser1": m.get("CFR_LASER_COM"), "laser2": m.get("CFR_LASER2_COM")}
    p.update(PORT_OVERRIDE)
    return p


# ---------------------------------------------------------------------------
# Laser DG535
# ---------------------------------------------------------------------------
def dg_query(dg, cmd, parse, tries=3):
    """parse(reply) for a DG535 query, retried: a GPIB read now and then
    times out and returns ''. The input buffer is cleared first, so a late
    reply to an earlier query is never read as this one. Abort if no try
    gives a readable reply."""
    resp = ""
    for _ in range(tries):
        dg.ser.reset_input_buffer()
        resp = dg._query_gpib(cmd)
        try:
            return parse(resp)
        except (ValueError, IndexError, KeyError):
            time.sleep(0.3)
    raise Abort(f"the DG535 gave no readable reply to {cmd} in {tries} tries "
                f"(last {resp!r})")


def dg_read(dg, name):
    """(reference, delay in s) as the DG535 reports it.

    Not dg.get_delay(): on an unreadable reply that returns the driver's own
    record of what it last wrote, so a check against it would prove nothing.
    """
    from instruments.dg535 import Channel

    def parse(resp):
        ref, delay = resp.split(",")[:2]
        return Channel(int(ref)).name, float(delay)
    return dg_query(dg, f"DT {int(Channel[name])}", parse)


def dg_trigger_mode(dg):
    from instruments.dg535 import TriggerMode
    return dg_query(dg, "TM", lambda resp: TriggerMode(int(resp)).name)


def dg_snapshot(dg):
    return {n: dg_read(dg, n) for n in "ABCD"}, dg_trigger_mode(dg)


def dg_text(snap):
    return "  ".join(f"{n} = {r} + {d * 1e6:.6f} us" for n, (r, d) in snap.items())


def dg_fixed_problems(snap, mode):
    """What is wrong with A, C and the trigger. The test never writes them."""
    p = []
    for n in ("A", "C"):
        ref, d = snap[n]
        if ref != "T0" or abs(d) > DG_MATCH_S:
            p.append(f"DG535 {n} is {ref} + {d * 1e6:.6f} us; the test expects T0 + 0")
    if mode != "EXTERNAL":
        p.append(f"DG535 trigger mode is {mode}; the test expects EXTERNAL (BNC 575 B)")
    return p


def dg_bd(dg, b_us, d_us):
    """(ok, B us, D us): B and D as read back, and whether they match."""
    (rb, b), (rd, d) = dg_read(dg, "B"), dg_read(dg, "D")
    ok = (rb == "A" and abs(b - b_us * 1e-6) <= DG_MATCH_S
          and rd == "C" and abs(d - d_us * 1e-6) <= DG_MATCH_S)
    return ok, b * 1e6, d * 1e6


def dg_program(dg, b_us, d_us):
    """Write B = A + b and D = C + d, then read all four channels back.

    A write that raises, a readback that cannot be read (dg_query has already
    retried it) and a readback that does not match each start the write and
    readback over, up to DG_TRIES times. A and C are never written, so a wrong
    A or C fails every try. Returns the number of tries used; Abort if none
    gave an exact match.
    """
    from instruments.dg535 import Channel
    want = {"A": ("T0", 0.0), "B": ("A", b_us * 1e-6),
            "C": ("T0", 0.0), "D": ("C", d_us * 1e-6)}
    why = ""
    for attempt in range(1, DG_TRIES + 1):
        try:
            dg.set_delay(Channel.B, Channel.A, b_us * 1e-6)
            dg.set_delay(Channel.D, Channel.C, d_us * 1e-6)
            got = {n: dg_read(dg, n) for n in "ABCD"}
        except Abort as e:
            why = str(e)
        except Exception as e:
            why = f"write failed: {e}"
        else:
            bad = [f"{n} = {r} + {d * 1e6:.6f} us" for n, (r, d) in got.items()
                   if r != want[n][0] or abs(d - want[n][1]) > DG_MATCH_S]
            if not bad:
                return attempt
            why = "read back " + ", ".join(bad)
        say(f"    DG535 try {attempt} of {DG_TRIES}: {why}")
        time.sleep(0.5)
    raise Abort(f"the DG535 would not hold B = A + {b_us:.4f} us, D = C + {d_us:.4f} us "
                f"after {DG_TRIES} tries ({why})")


def dg_restore(dg, orig):
    from instruments.dg535 import Channel
    for n in ("B", "D"):
        ref, d = orig[n]
        dg.set_delay(Channel[n], Channel[ref], d)
    now = {n: dg_read(dg, n) for n in ("B", "D")}
    ok = all(now[n][0] == orig[n][0] and abs(now[n][1] - orig[n][1]) <= DG_MATCH_S
             for n in now)
    say(f"DG535 B and D {'restored' if ok else 'NOT restored'}: "
        + "  ".join(f"{n} = {r} + {d * 1e6:.6f} us" for n, (r, d) in now.items()))


# ---------------------------------------------------------------------------
# Lasers
# ---------------------------------------------------------------------------
class Laser:
    """One CFR laser through the GUI's own LaserColumn (gui/laser_panel.py).

    prep() is the column's _run_prep(), the code behind Prep System, and
    stop() its _stop_worker(), behind Stop Both. EXT/EXT, as in the GUI. The
    column's log lines are kept and printed only when a prep fails.
    """

    def __init__(self, port, title, save_key, tag):
        from gui.laser_panel import LaserColumn
        self.tag, self.port = tag, port
        self.lines = []
        self.col = LaserColumn(log_func=self.lines.append, default_port=port,
                               title=title, save_key=save_key, log_tag=tag)
        self.col.laser.connect(port)
        # The first command after the port opens comes back "cmd not found"
        # (seen on both lasers; the BNC 575 answers its first *IDN? with ?1
        # the same way), so a throwaway query goes first.
        self.col.laser.send_cmd("ST")
        self.prepped = False

    def check(self):
        """The GUI's Check Interlocks, retried once if WOR comes back unreadable."""
        clear, summary, _ = self.col.laser.check_interlocks()
        if not clear and summary.startswith("Could not parse WOR"):
            clear, summary, _ = self.col.laser.check_interlocks()
        return clear, summary

    def state(self):
        """(armed, ST reply). Armed when ST shows ext and qs: the GUI's test."""
        st = (self.col.laser.send_cmd("ST") or "").strip()
        return ("ext" in st.lower() and "qs" in st.lower()), st

    def prep(self):
        self.lines.clear()
        self.prepped = True
        return self.col._run_prep()

    def stop(self):
        self.col._stop_worker()
        self.prepped = False

    def close(self):
        try:
            if self.prepped:
                self.stop()
        finally:
            self.col.shutdown()


def prep_both(lasers):
    """Prep each laser (one retry), then confirm both still report ARMED.
    Returns {tag: ST reply}."""
    for L in lasers:
        for attempt in (1, 2):
            ok, detail = L.prep()
            if ok:
                break
            say(f"  {L.tag}: prep failed ({detail}), try {attempt}")
            for line in L.lines[-8:]:
                say(f"      {line}")
            L.stop()
            time.sleep(1.0)
        else:
            raise Abort(f"{L.tag} would not prep: {detail}")
    st = {}
    for L in lasers:
        armed, reply = L.state()
        if not armed:
            raise Abort(f"{L.tag} is not ARMED just before the fire: ST = {reply!r}")
        st[L.tag] = reply
    return st


def stop_lasers(lasers):
    for L in lasers:
        try:
            L.stop()
        except Exception as e:
            say(f"  {L.tag} stop error: {e}")


# ---------------------------------------------------------------------------
# Scope 3 and the Q-switch edges
# ---------------------------------------------------------------------------
def report_scope(scope):
    say(f"Scope {SCOPE}: {scope.query('*IDN?').strip()}")
    for q, label in ((":TRIGger:EDGE:SOURce?", "trigger source"),
                     (":TRIGger:SWEep?", "trigger sweep"),
                     (":TIMebase:MAIN:SCALe?", "timebase s/div"),
                     (":ACQuire:MDEPth?", "memory depth")):
        try:
            say(f"  {label:<16} {scope.query(q).strip()}")
        except Exception:
            pass
    problems = []
    for ch, name in ((CH_L1, "L1 Q-switch"), (CH_L2, "L2 Q-switch")):
        try:
            imp = scope.query(f":CHANnel{ch}:IMPedance?").strip()
            scl = float(scope.query(f":CHANnel{ch}:SCALe?"))
            on = scope.query(f":CHANnel{ch}:DISPlay?").strip()
            say(f"  CH{ch} {name:<12} {imp:<5} {scl:g} V/div  display {on}")
            if on in ("0", "OFF"):
                problems.append(f"scope {SCOPE} CH{ch} ({name}) is off")
        except Exception as e:
            problems.append(f"scope {SCOPE} CH{ch}: {e}")
    return problems


def qsw_edge(t, v):
    """50 % rising edge of one Q-switch monitor pulse, interpolated.

    The pulse is found the way the analysis pipeline finds it (gate_qsw: the
    longest run above half the height of a 20 ns mean, at least 100 ns long),
    so the spacing matches the Qsw spacing of the shot analysis. It is then
    timed with edge_timing.edge_stats, as laser_io.py times its edges.
    Returns {"t50" s, "amp" V, "rise" s} or None.
    """
    from analysis.pipeline import gate_qsw
    from edge_timing import edge_stats
    _, coarse = gate_qsw(t, v)
    if not np.isfinite(coarse):
        return None
    st = edge_stats(t, v, rising=True, search=(coarse - 100e-9, coarse + 150e-9))
    if not np.isfinite(st["edge_time"]):
        return None
    return {"t50": st["edge_time"], "amp": st["amplitude"],
            "rise": st["risetime_20_80"]}


# ---------------------------------------------------------------------------
# One row of the table
# ---------------------------------------------------------------------------
class Row:
    """A row's shots, with every shot's traces cropped to the same window so
    the CSV has one time column."""

    def __init__(self, gap, b_us, d_us):
        self.gap, self.b_us, self.d_us = gap, b_us, d_us
        self.cmd_ns = (d_us - b_us) * 1e3
        self.shots = 0
        self.bad = 0           # shots in a row of this row with no spacing
        self.edges = []        # (shot, L1 t50 s, L2 t50 s) for good shots
        self.window = None     # (first sample time s, dt s, samples)
        self.pending = []      # full records until the window is known
        self.traces = []       # (shot, L1 volts, L2 volts), cropped

    def add_trace(self, shot, t, v1, v2, e1, e2):
        if self.window is None and e1 and e2:
            dt = (t[-1] - t[0]) / (t.size - 1)
            lo = e1["t50"] - SAVE_BEFORE_US * 1e-6
            hi = e2["t50"] + SAVE_AFTER_US * 1e-6
            i0 = int(np.searchsorted(t, lo))
            self.window = (float(t[i0]), float(dt), int(round((hi - lo) / dt)))
            for rec in self.pending:
                self._crop(*rec)
            self.pending = []
        if self.window is None:
            self.pending.append((shot, t, v1, v2))
        else:
            self._crop(shot, t, v1, v2)

    def _crop(self, shot, t, v1, v2):
        t0, dt, n = self.window
        i0 = int(np.searchsorted(t, t0 - dt / 2))
        out = []
        for v in (v1, v2):
            seg = np.full(n, np.nan)
            part = v[i0:i0 + n]
            seg[:part.size] = part
            out.append(seg)
        self.traces.append((shot, out[0], out[1]))

    def stats(self):
        s = {"shots": self.shots, "good": len(self.edges)}
        if not self.edges:
            return s
        t1 = np.array([e[1] for e in self.edges])
        t2 = np.array([e[2] for e in self.edges])
        sp = (t2 - t1) * 1e9

        def sd(x):
            return float(np.std(x, ddof=1)) if x.size > 1 else float("nan")

        s.update(within_tol=int(np.sum(np.abs(sp - self.cmd_ns) <= TOL_NS)),
                 mean=float(sp.mean()), sd=sd(sp), min=float(sp.min()),
                 max=float(sp.max()), mean_minus_cmd=float(sp.mean() - self.cmd_ns),
                 l1_mean_s=float(t1.mean()), l1_sd_ps=sd(t1) * 1e12,
                 l2_sd_ps=sd(t2) * 1e12, spacing=sp)
        return s

    def save_traces(self, folder):
        if not self.traces:
            return None
        t0, dt, n = self.window
        cols = ([(t0 + dt * np.arange(n)) * 1e6]
                + [tr[1] for tr in self.traces] + [tr[2] for tr in self.traces])
        head = (["t_us"] + [f"L1_s{tr[0]:02d}" for tr in self.traces]
                + [f"L2_s{tr[0]:02d}" for tr in self.traces])
        path = os.path.join(folder, f"traces_{self.gap}ns.csv")
        np.savetxt(path, np.column_stack(cols), delimiter=",", header=",".join(head),
                   comments="", fmt=["%.9g"] + ["%.5g"] * (len(cols) - 1))
        return path


def take_shot(row, i, b, program):
    """Shot i of one row. b holds the instruments and the output files.

    program: write B and D and read all four channels back first (with
    --interleave the DG535 still holds the previous row's values).
    """
    from calibrate_channel import arm_and_wait, read_channel
    b.seq += 1
    label = f"  {row.gap:>4} ns shot {i:2d}"
    r = {"seq": b.seq, "target_gap_ns": row.gap, "B_us": row.b_us, "D_us": row.d_us,
         "cmd_spacing_ns": f"{row.cmd_ns:.4f}", "shot": i,
         "time": datetime.now().isoformat(timespec="seconds")}
    tries = dg_program(b.dg, row.b_us, row.d_us) if program else 0

    st = prep_both(b.lasers)
    r["laser1_st"], r["laser2_st"] = st["Laser1"], st["Laser2"]

    # B and D once more, right before the fire. A readback that cannot be read
    # or does not match is written and read back again before giving up.
    try:
        ok, bb, dd = dg_bd(b.dg, row.b_us, row.d_us)
        why = f"B = {bb:.6f} us, D = {dd:.6f} us"
    except Abort as e:
        ok, bb, dd, why = False, float("nan"), float("nan"), str(e)
    if not ok:
        say(f"{label}: DG535 before the fire: {why}. Writing it again.")
        tries += dg_program(b.dg, row.b_us, row.d_us)
        ok, bb, dd = dg_bd(b.dg, row.b_us, row.d_us)
        if not ok:
            stop_lasers(b.lasers)
            raise Abort(f"{row.gap} ns shot {i}: the DG535 reads B = {bb:.6f} us, "
                        f"D = {dd:.6f} us after being written")
    r.update(dg_B_us=f"{bb:.6f}", dg_D_us=f"{dd:.6f}", dg_ok=1, dg_tries=tries)

    try:
        arm_and_wait(b.scope, ARM_TIMEOUT_S, fire=b.fire)
        got = True
    except TimeoutError:
        got = False
    except RuntimeError as e:
        raise Abort(f"{row.gap} ns shot {i}: {e}")
    finally:
        stop_lasers(b.lasers)
    row.shots += 1
    r["triggered"] = int(got)

    e1 = e2 = None
    if got:
        t, v1 = read_channel(b.scope, CH_L1)
        _, v2 = read_channel(b.scope, CH_L2)
        e1, e2 = qsw_edge(t, v1), qsw_edge(t, v2)
        row.add_trace(i, t, v1, v2, e1, e2)
    for tag, e in (("l1", e1), ("l2", e2)):
        if e:
            r[f"{tag}_t50_us"] = f"{e['t50'] * 1e6:.7f}"
            r[f"{tag}_amp_v"] = f"{e['amp']:.3f}"
            r[f"{tag}_rise_ns"] = f"{e['rise'] * 1e9:.2f}"

    dg_note = "" if not tries else f"  DG535 verified{'' if tries == 1 else f' ({tries} tries)'}"
    if e1 and e2:
        sp = (e2["t50"] - e1["t50"]) * 1e9
        row.edges.append((i, e1["t50"], e2["t50"]))
        inside = abs(sp - row.cmd_ns) <= TOL_NS
        r.update(spacing_ns=f"{sp:.3f}", spacing_minus_cmd_ns=f"{sp - row.cmd_ns:.3f}",
                 within_tol=int(inside), note="" if inside else "spacing out of tolerance")
        row.bad = 0
        say(f"{label}: L1 {e1['t50'] * 1e6:.4f} us  L2 {e2['t50'] * 1e6:.4f} us"
            f"  spacing {sp:8.2f} ns ({sp - row.cmd_ns:+6.2f})"
            f"  {'OK' if inside else 'OUT OF TOLERANCE'}{dg_note}")
    else:
        missing = ("no scope trigger" if not got else
                   " and ".join(n for n, e in (("no L1 Q-switch", e1),
                                               ("no L2 Q-switch", e2)) if not e))
        r["note"] = missing
        row.bad += 1
        say(f"{label}: {missing}{dg_note}")
    b.writer.writerow(r)
    b.summary_file.flush()
    if row.bad >= MAX_BAD_IN_A_ROW:
        raise Abort(f"{row.bad} shots in a row of the {row.gap} ns row without both "
                    f"Q-switch edges. Check the lasers, the DG535 trigger and the "
                    f"scope {SCOPE} cabling")


def run_row(row, shots, b):
    """Every shot of one row: the DG535 written once, B and D checked before
    each shot."""
    say(f"\n=== {row.gap} ns row: B = A + {row.b_us:.4f} us, D = C + {row.d_us:.4f} us,"
        f" D - B = {row.cmd_ns:.2f} ns ===")
    tries = dg_program(b.dg, row.b_us, row.d_us)
    say(f"  DG535 written and read back{'' if tries == 1 else f' ({tries} tries)'}")
    for i in range(1, shots + 1):
        take_shot(row, i, b, program=False)


def run_interleaved(rows, shots, b):
    """Rows take turns, one shot each, the DG535 written and read back before
    every shot."""
    say("\n=== interleaved: the DG535 is written and read back before every shot ===")
    for row in rows:
        say(f"  {row.gap:>4} ns row: B = A + {row.b_us:.4f} us, D = C + {row.d_us:.4f} us,"
            f" D - B = {row.cmd_ns:.2f} ns")
    for i in range(1, shots + 1):
        for row in rows:
            take_shot(row, i, b, program=True)


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
def report(rows, folder):
    say("\nRESULTS (spacing = L2 Q-switch - L1 Q-switch at 50 %)")
    say("=" * 96)
    say(f"  {'target':>7}{'D - B':>11}{'good':>8}{'in tol':>8}{'mean':>11}{'sd':>8}"
        f"{'min':>10}{'max':>10}{'mean-cmd':>10}{'L1 jit':>9}{'L2 jit':>9}")
    say(f"  {'ns':>7}{'ns':>11}{'':>8}{'':>8}{'ns':>11}{'ns':>8}{'ns':>10}{'ns':>10}"
        f"{'ns':>10}{'ps':>9}{'ps':>9}")
    out = []
    for r in rows:
        s = r.stats()
        line = {"target_gap_ns": r.gap, "B_us": r.b_us, "D_us": r.d_us,
                "cmd_spacing_ns": f"{r.cmd_ns:.4f}", "shots": s["shots"], "good": s["good"]}
        if s["good"]:
            line.update(within_tol=s["within_tol"], spacing_mean_ns=f"{s['mean']:.3f}",
                        spacing_sd_ns=f"{s['sd']:.3f}", spacing_min_ns=f"{s['min']:.3f}",
                        spacing_max_ns=f"{s['max']:.3f}",
                        mean_minus_cmd_ns=f"{s['mean_minus_cmd']:.3f}",
                        l1_sd_ps=f"{s['l1_sd_ps']:.0f}", l2_sd_ps=f"{s['l2_sd_ps']:.0f}")
            say(f"  {r.gap:>7}{r.cmd_ns:>11.2f}{s['good']:>4}/{s['shots']:<3}"
                f"{s['within_tol']:>8}{s['mean']:>11.2f}{s['sd']:>8.2f}{s['min']:>10.2f}"
                f"{s['max']:>10.2f}{s['mean_minus_cmd']:>+10.2f}{s['l1_sd_ps']:>9.0f}"
                f"{s['l2_sd_ps']:>9.0f}")
        else:
            say(f"  {r.gap:>7}{r.cmd_ns:>11.2f}{0:>4}/{s['shots']:<3}   no good shots")
        out.append(line)
    with open(os.path.join(folder, "rows.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ROW_COLS)
        w.writeheader()
        w.writerows(out)


def make_plots(rows, folder):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = [r for r in rows if r.edges]
    if not rows:
        return []
    c1, c2 = "#d9541a", "#7d2e8f"      # the analysis figure's Q-switch colors
    paths = []

    fig, axs = plt.subplots(len(rows), 1, figsize=(12, 3.2 * len(rows)), squeeze=False)
    for ax, r in zip(axs[:, 0], rows):
        s = r.stats()
        t0, dt, n = r.window
        x = ((t0 + dt * np.arange(n)) - s["l1_mean_s"]) * 1e9
        for _, v1, v2 in r.traces:
            ax.plot(x, v1, color=c1, lw=0.6, alpha=0.5)
            ax.plot(x, v2, color=c2, lw=0.6, alpha=0.5)
        ax.plot([], [], color=c1, label=f"L1 Q-switch (CH{CH_L1})")
        ax.plot([], [], color=c2, label=f"L2 Q-switch (CH{CH_L2})")
        ax.axvline(r.cmd_ns, color="k", ls="--", lw=1, label=f"D - B = {r.cmd_ns:.2f} ns")
        ax.set_title(f"{r.gap} ns row: spacing {s['mean']:.2f} +/- {s['sd']:.2f} ns, "
                     f"{s['good']}/{s['shots']} shots")
        ax.set_ylabel("V")
        ax.grid(alpha=0.3)
        ax.legend(loc="upper right", fontsize=8)
    axs[-1, 0].set_xlabel("Time from the mean L1 Q-switch edge (ns)")
    fig.tight_layout()
    paths.append(os.path.join(folder, "traces.png"))
    fig.savefig(paths[-1], dpi=110)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4.5))
    for r in rows:
        s = r.stats()
        ax.plot([e[0] for e in r.edges], s["spacing"] - r.cmd_ns, "o-", ms=4,
                label=f"{r.gap} ns row (D - B {r.cmd_ns:.2f} ns)")
    ax.axhspan(-TOL_NS, TOL_NS, color="0.9", zorder=0, label=f"+/- {TOL_NS:g} ns")
    ax.axhline(0, color="k", lw=0.8)
    ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
    ax.set_xlabel("Shot")
    ax.set_ylabel("Spacing - (D - B)  (ns)")
    ax.set_title("Q-switch spacing error per shot")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    paths.append(os.path.join(folder, "spacing.png"))
    fig.savefig(paths[-1], dpi=110)
    plt.close(fig)
    return paths


# ---------------------------------------------------------------------------
def main():
    global LOG
    args = sys.argv[1:]
    check_only = bool(args) and args[0].lower() == "check"
    if check_only:
        args = args[1:]
    shots = SHOTS
    interleave = "--interleave" in args
    if interleave:
        args.remove("--interleave")
    if "--shots" in args:
        k = args.index("--shots")
        shots = int(args[k + 1])
        del args[k:k + 2]
    gaps = [int(a) for a in args] if args else list(TABLE)
    unknown = [g for g in gaps if g not in TABLE]
    if unknown:
        print(f"No table row for {unknown}. Rows: {list(TABLE)}")
        return 1

    os.chdir(HERE)            # connection_memory.json and calibrate_channel's imports
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])   # noqa: F841, LaserColumn needs it
    from calibrate_channel import SCOPE_IPS, connect, open_bnc
    from instruments.dg535 import DG535Controller

    ports = find_ports()
    say("Ports (connection_memory.json): " + ", ".join(f"{k} {v}" for k, v in ports.items()))
    b = SimpleNamespace(dg=None, scope=None, rm=None, bnc=None, lasers=[], fire=None,
                        writer=None, summary_file=None, seq=0, started=False)
    rows = [Row(g, *TABLE[g]) for g in gaps]
    orig, sweep0, folder, problems = None, None, None, []
    t_start = time.time()

    def opening(what, fn):
        try:
            return fn()
        except Abort:
            raise
        except Exception as e:
            raise Abort(f"could not open {what}: {e}. If the GUI is running, close it: "
                        f"it holds the instrument ports")

    try:
        b.dg = DG535Controller()
        opening(f"the DG535 on {ports['dg535']}",
                lambda: b.dg.connect(port=ports["dg535"], gpib_addr=DG_GPIB))
        orig, mode = opening("the DG535 readback", lambda: dg_snapshot(b.dg))
        say(f"DG535: {dg_text(orig)}  trigger {mode}")
        problems += dg_fixed_problems(orig, mode)

        b.rm, b.scope, _ = opening(f"scope {SCOPE}",
                                   lambda: connect(SCOPE_IPS[SCOPE], socket=True))
        problems += report_scope(b.scope)

        for key, title, save_key, tag in (("laser1", "CFR Laser 1", "CFR_LASER_COM", "Laser1"),
                                          ("laser2", "CFR Laser 2", "CFR_LASER2_COM", "Laser2")):
            L = opening(f"{tag} on {ports[key]}",
                        lambda: Laser(ports[key], title, save_key, tag))
            b.lasers.append(L)
            armed, reply = L.state()
            say(f"{tag} on {ports[key]}: ST = {reply!r}")
            if armed:
                # Closing the GUI only closes the laser ports, so a laser can
                # still be armed in EXT/EXT from the last session, firing on
                # any DG535 trigger. Start every check and run from stopped.
                L.stop()
                say(f"  it was left ARMED: stopped it with the GUI's Stop (CS, S, SHC0)."
                    f" ST now {L.state()[1]!r}")
            clear, summary = L.check()
            say("  " + summary.replace("\n", "\n  "))
            if not clear:
                problems.append(f"{tag} interlocks are not clear")

        # open_bnc refuses unless the 575 is in DIS, where a software fire pulses.
        b.bnc, fire = opening(f"the BNC 575 on {ports['bnc']}",
                              lambda: open_bnc(ports["bnc"], assume_yes=True))

        def fire_once():
            if not fire():
                raise RuntimeError("the BNC 575 did not accept the fire command")
        b.fire = fire_once

        if problems:
            say("\nNot ready:")
            for p in problems:
                say(f"  - {p}")
        if check_only:
            say("\nCheck only: nothing was written to the DG535 and nothing was fired.")
            return 1 if problems else 0
        if problems:
            say("Nothing was written or fired.")
            return 1

        total = shots * len(gaps)
        per_shot = SECONDS_PER_SHOT + (SECONDS_PER_DG_WRITE if interleave else 0)
        order = ("rows in turn, DG535 written and read back before every shot"
                 if interleave else "one row after another")
        say(f"\nPlan: rows {gaps}, {shots} shots each, {order}, {total} shots, "
            f"about {max(1, round(total * per_shot / 60))} min.")
        say("  BOTH LASERS FIRE on every shot. Beams blocked, eyewear on, area clear.")
        say("  The BNC 575 fires every output on each shot. In the shot setup its A")
        say("  output drives the Marx DG535: the WJ supplies must be off and the")
        say("  Marx grounded, or A disconnected.")
        if input("  Type yes to start: ").strip().lower() != "yes":
            say("Stopped. Nothing was written or fired.")
            return 1

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = os.path.join(OUT_ROOT, f"qsw_{stamp}")
        os.makedirs(folder)
        LOG = open(os.path.join(folder, "run.log"), "w", encoding="utf-8")
        LOG.write("\n".join(EARLY) + "\n")
        say(f"Results in {folder}")
        with open(os.path.join(folder, "settings.json"), "w") as f:
            json.dump({"table": {str(k): v for k, v in TABLE.items()}, "rows": gaps,
                       "shots": shots, "interleave": interleave, "dg_tries": DG_TRIES,
                       "tol_ns": TOL_NS, "ports": ports,
                       "scope": SCOPE, "ch_l1": CH_L1, "ch_l2": CH_L2,
                       "dg535_before": {n: [r, d] for n, (r, d) in orig.items()},
                       "dg535_trigger": mode}, f, indent=2)
        b.summary_file = open(os.path.join(folder, "summary.csv"), "w", newline="")
        b.writer = csv.DictWriter(b.summary_file, fieldnames=SUMMARY_COLS)
        b.writer.writeheader()

        b.started = True          # from here the DG535 gets written: restore it at the end
        sweep0 = b.scope.query(":TRIGger:SWEep?").strip()
        if not sweep0.upper().startswith("NORM"):
            b.scope.write(":TRIGger:SWEep NORMal")

        try:
            if interleave:
                run_interleaved(rows, shots, b)
            else:
                for row in rows:
                    run_row(row, shots, b)
        finally:
            for row in rows:
                path = row.save_traces(folder)
                if path:
                    say(f"  traces saved: {path}")
        return 0

    except Abort as e:
        say(f"\nSTOPPED: {e}")
        return 1
    except KeyboardInterrupt:
        say("\nSTOPPED with Ctrl+C")
        return 1
    except Exception as e:
        import traceback
        say(f"\nSTOPPED: unexpected error: {e!r}")
        if LOG is not None:
            LOG.write(traceback.format_exc())
        return 1
    finally:
        # Lasers first, whatever happened.
        armed = [L for L in b.lasers if L.prepped]
        if armed:
            stop_lasers(armed)
            say(f"Stopped {' and '.join(L.tag for L in armed)}.")
        for L in b.lasers:
            try:
                L.close()
            except Exception as e:
                say(f"{L.tag} close error: {e}")
        if b.dg is not None:
            try:
                if RESTORE_DG535 and orig and b.started:
                    dg_restore(b.dg, orig)
            except Exception as e:
                say(f"DG535 restore error: {e}. Check B and D in the GUI.")
            b.dg.close()
        if b.scope is not None:
            try:
                if sweep0 and not sweep0.upper().startswith("NORM"):
                    b.scope.write(f":TRIGger:SWEep {sweep0}")
                b.scope.close()
                b.rm.close()
            except Exception:
                pass
        if b.bnc is not None:
            b.bnc.close()
        if b.summary_file is not None:
            b.summary_file.close()
        done = [r for r in rows if r.shots]
        if folder and done:
            report(done, folder)
            for p in make_plots(done, folder):
                say(f"plot: {p}")
                try:
                    os.startfile(p)
                except Exception:
                    pass
            say(f"summary: {os.path.join(folder, 'summary.csv')}")
            say(f"time: {(time.time() - t_start) / 60:.1f} min")
        if LOG is not None:
            LOG.close()


if __name__ == "__main__":
    sys.exit(main())
