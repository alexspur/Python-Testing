"""
Laser 1 trigger-in to sync-out timing, on scope 3, by moving two cable ends.

Three long cable runs stay on their scope channels for the whole test:

    CH1   "L1 Q-switch" run        the far end moves
    CH3   "Flashlamp 1" run        the far end moves
    CH2   "L2 Q-switch" run        fixed reference on the laser DG535 T0 output

Run "in"    the far ends look at what the laser DG535 SENDS to laser 1
            CH1 run  <- barrel <- DG535 output B cable (off laser 1 Q-switch IN)
            CH3 run  <- barrel <- DG535 output A cable (off laser 1 Flashlamp IN)
            Laser 1 gets no triggers and does not fire.

Run "out"   the far ends look at what laser 1 SENDS BACK
            CH1 run  <- laser 1 Q-switch OUT
            CH3 run  <- laser 1 Lamp OUT
            DG535 A and B cables are back on laser 1. Laser 1 fires.
            Each shot preps laser 1 with the GUI's own Prep (EXT/EXT) and
            stops it with the GUI's own Stop, through gui/laser_panel.py.

The same cable and the same scope channel carry the "in" and the "out" edge,
so the cable, the channel and the scope trigger all cancel:

    laser delay = (t_out - t_ref) - (t_in - t_ref)

Usage (or press Run and answer the prompt):

    python laser_io.py in
    python laser_io.py out
    python laser_io.py solve
"""

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# ---------------------------------------------------------------------------
# Things you might change
# ---------------------------------------------------------------------------
SCOPE = "3"
BNC_PORT = "COM5"
LASER1_PORT = "COM8"      # laser 1. connection_memory.json says COM6: wrong
SHOTS = 30

CH_QSW = 1        # "L1 Q-switch" long run
CH_LAMP = 3       # "Flashlamp 1" long run
CH_REF = 2        # "L2 Q-switch" long run, on the laser DG535 T0 output

# One-way cable delays, ns. Only used for the absolute times, never for the
# laser delay itself.
CABLE = {CH_QSW: 268.558 / 2, CH_LAMP: 268.631 / 2, CH_REF: 268.926 / 2}

# Delay generator settings of shot 43, 24 Sept 2026.
BNC_B_US = 3.025          # BNC 575 channel B delay
LAMP_US = 0.0             # laser DG535 A = T0 + 0
QSW_US = 180.5            # laser DG535 B = A + 180.5 us

# The timing map, ns.
TRIG_ARRIVAL = 13.392     # BNC 575 A to scope 3 EXT TRIG
SCOPE_OFFSET = -87.138    # scope 3, CH4 value, borrowed by the other channels
A_TO_DG_EXT = -0.783 + 166.410 + 1.556     # B skew + fiber link + cable
DG_INS = {"T0": 85.09, "A": 86.426, "B": 86.409}
DG_TO_LASER = {"A": 4.523, "B": 4.536}

# Earlier values for the Q-switch IN to OUT delay.
BENCH_QSW = 123.7         # laser0.csv bench test, 50% to 50%
SHOT43_QSW = 111.15       # inferred from shot 43 and the map
BENCH_LAMP = 498.0        # laser0.csv, Flashlamp IN to Lamp OUT

STORE = os.path.join(HERE, "laser_io.json")
FIND_HALF_NS = 1500.0     # look this far each side of the expected edge
FIT_BEFORE_NS = 100.0
FIT_AFTER_NS = 150.0


# ---------------------------------------------------------------------------
# What the map predicts
# ---------------------------------------------------------------------------
def map_times():
    """Times after T0, ns, at the device connectors."""
    ext = BNC_B_US * 1e3 + A_TO_DG_EXT
    lamp = ext + DG_INS["A"] + LAMP_US * 1e3
    qsw = ext + DG_INS["B"] + (LAMP_US + QSW_US) * 1e3
    return {
        "ref": ext + DG_INS["T0"],                    # DG535 T0 output
        "lamp_in": lamp + DG_TO_LASER["A"],           # laser 1 Flashlamp IN
        "qsw_in": qsw + DG_TO_LASER["B"],             # laser 1 Q-switch IN
    }


def to_record(t0_ns, ch):
    """Time after T0 at the far end of a cable -> scope 3 record time."""
    return t0_ns + CABLE[ch] - TRIG_ARRIVAL - SCOPE_OFFSET


def to_t0(rec_ns, ch):
    """Scope 3 record time -> time after T0 at the far end of the cable."""
    return rec_ns + TRIG_ARRIVAL + SCOPE_OFFSET - CABLE[ch]


def expected_record(mode):
    m = map_times()
    exp = {CH_REF: to_record(m["ref"], CH_REF)}
    if mode == "in":
        exp[CH_QSW] = to_record(m["qsw_in"], CH_QSW)
        exp[CH_LAMP] = to_record(m["lamp_in"], CH_LAMP)
    else:
        mid = 0.5 * (BENCH_QSW + SHOT43_QSW)
        exp[CH_QSW] = to_record(m["qsw_in"] + mid, CH_QSW)
        exp[CH_LAMP] = to_record(m["lamp_in"] + BENCH_LAMP, CH_LAMP)
    return exp


NAMES = {
    "in": {CH_QSW: "Q-switch trigger at laser 1",
           CH_LAMP: "Flashlamp trigger at laser 1",
           CH_REF: "DG535 T0 output (reference)"},
    "out": {CH_QSW: "Laser 1 Q-switch OUT",
            CH_LAMP: "Laser 1 Lamp OUT",
            CH_REF: "DG535 T0 output (reference)"},
}


# ---------------------------------------------------------------------------
# Edge finding
# ---------------------------------------------------------------------------
def locate(t, v, t_exp, half):
    """First rising edge within +/- half of t_exp. Returns (time, amp) or None.

    The baseline comes from the first fifth of the window, so a pulse that is
    already high when the window opens is rejected instead of mistaken for a
    baseline.
    """
    m = (t >= t_exp - half) & (t <= t_exp + half)
    tw, vw = t[m], v[m]
    n = vw.size
    if n < 50:
        return None
    head = vw[: n // 5]
    base = float(np.median(head))
    noise = float(np.median(np.abs(head - base))) * 1.4826
    top = float(np.percentile(vw, 99.5))
    amp = top - base
    if amp < max(10.0 * noise, 0.2):
        return None
    above = vw >= base + 0.5 * amp
    k = 5
    run = np.convolve(above.astype(int), np.ones(k, int), mode="valid")
    idx = np.flatnonzero(run == k)
    idx = idx[idx > 0]
    idx = idx[~above[idx - 1]] if idx.size else idx
    if idx.size == 0:
        return None
    return float(tw[int(idx[0])]), amp


def time_edge(t, v, tc):
    """50% and 10% crossing near tc, plus amplitude and 20-80 risetime."""
    from edge_timing import edge_stats, edge_time
    search = (tc - FIT_BEFORE_NS * 1e-9, tc + FIT_AFTER_NS * 1e-9)
    st = edge_stats(t, v, rising=True, search=search)
    t10 = edge_time(t, v, fraction=0.1, rising=True, search=search)
    return {"t50": st["edge_time"], "t10": t10, "amp": st["amplitude"],
            "rise": st["risetime_20_80"]}


def list_edges(t, v):
    from fiber_transit import multi_edges
    edges, info = multi_edges(t, v, max_report=12)
    if not edges:
        print(f"      no pulse found at all: {info.get('reason', '')}")
        return
    for te, d, amp in edges:
        print(f"      {te*1e9:12.2f} ns  {d:<8} {amp:.3f} V")


# ---------------------------------------------------------------------------
# Acquisition
# ---------------------------------------------------------------------------
def acquire(instr, fire):
    """One acquisition, all three channels from the same trigger."""
    from calibrate_channel import arm_and_wait, read_channel
    arm_and_wait(instr, 5.0 if fire else 30.0, fire=fire)
    return {ch: read_channel(instr, ch) for ch in (CH_QSW, CH_LAMP, CH_REF)}


def report_scope(instr):
    print(instr.query("*IDN?").strip())
    for q, label in ((":TRIGger:EDGE:SOURce?", "trigger source"),
                     (":TIMebase:MAIN:SCALe?", "timebase s/div"),
                     (":ACQuire:MDEPth?", "memory depth")):
        try:
            print(f"  {label:<16} {instr.query(q).strip()}")
        except Exception:
            pass
    for ch in (CH_QSW, CH_LAMP, CH_REF):
        try:
            imp = instr.query(f":CHANnel{ch}:IMPedance?").strip()
            scl = float(instr.query(f":CHANnel{ch}:SCALe?"))
            on = instr.query(f":CHANnel{ch}:DISPlay?").strip()
            print(f"  CH{ch}  {imp:<5} {scl:g} V/div  display {on}")
            if not imp.upper().startswith("FIFT"):
                print(f"  WARNING: CH{ch} is not at 50 ohm. Set it to 50 ohm.")
            if on in ("0", "OFF"):
                print(f"  WARNING: CH{ch} is off. Turn it on.")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Laser 1, run "out" only
# ---------------------------------------------------------------------------
class LaserNotReady(Exception):
    pass


class Laser1:
    """Laser 1 through the GUI's own LaserColumn (gui/laser_panel.py).

    The prep and the stop are the column's own _run_prep() and _stop_worker(),
    the code behind Prep System and Stop Both, called on this thread. No serial
    command is sent from here. The column starts in EXT/EXT, as in the GUI.
    """

    def __init__(self, port):
        gui_dir = os.path.join(HERE, "ScopeDelayGUI")
        if gui_dir not in sys.path:
            sys.path.append(gui_dir)
        from PyQt6.QtWidgets import QApplication
        self.app = QApplication.instance() or QApplication([])
        from gui.laser_panel import LaserColumn
        self.col = LaserColumn(default_port=port, title="CFR Laser 1",
                               save_key="CFR_LASER_COM", log_tag="Laser1")
        self.armed = False
        self.col.laser.connect(port)

    def check(self):
        """The GUI's Check Interlocks. Returns (clear, summary)."""
        clear, summary, _ = self.col.laser.check_interlocks()
        return clear, summary

    def arm(self):
        self.armed = True
        ok, detail = self.col._run_prep()
        if not ok:
            raise LaserNotReady(f"laser 1 prep failed: {detail}")

    def stop(self):
        self.col._stop_worker()
        self.armed = False

    def close(self):
        try:
            if self.armed:
                self.stop()
        finally:
            self.col.shutdown()


def do_run(mode, instr, fire, shots, laser=None):
    exp = expected_record(mode)
    half = FIND_HALF_NS * 1e-9

    print(f"\nRun '{mode}', {shots} shots")
    for ch in (CH_QSW, CH_LAMP, CH_REF):
        print(f"  CH{ch}  {NAMES[mode][ch]:<30} expected near "
              f"{exp[ch]:10.1f} ns")
    print()

    centre = None
    rows = []
    for i in range(shots):
        if laser is not None:
            laser.arm()
        try:
            rec = acquire(instr, fire)
        except TimeoutError as e:
            print(f"  shot {i+1:3d}: missed ({e})")
            continue
        finally:
            if laser is not None:
                laser.stop()
                print(f"  shot {i+1:3d}: laser 1 armed, then stopped")

        if centre is None:
            centre, bad = {}, False
            for ch in (CH_QSW, CH_LAMP, CH_REF):
                t, v = rec[ch]
                got = locate(t, v, exp[ch] * 1e-9, half)
                if got is None:
                    bad = True
                    print(f"  CH{ch}: no rising edge within "
                          f"{FIND_HALF_NS:.0f} ns of {exp[ch]:.1f} ns.")
                    print(f"    record {t[0]*1e9:+.0f} to {t[-1]*1e9:+.0f} ns. "
                          f"Edges in the whole record:")
                    list_edges(t, v)
                else:
                    centre[ch] = got[0]
                    print(f"  CH{ch}: edge at {got[0]*1e9:10.2f} ns, "
                          f"{got[1]:.2f} V, "
                          f"{got[0]*1e9 - exp[ch]:+7.2f} ns from expected")
            if bad:
                print("\nStopped. Check the cabling, the 50 ohm settings and "
                      "the delay generator settings, then run again.")
                return 1
            print()

        e = {ch: time_edge(rec[ch][0], rec[ch][1], centre[ch])
             for ch in (CH_QSW, CH_LAMP, CH_REF)}
        if not all(np.isfinite(e[ch]["t50"]) for ch in e):
            print(f"  shot {i+1:3d}: no clean edge on one channel, skipped")
            continue
        rows.append(e)
        if len(rows) == 1 or (i + 1) % 10 == 0 or i == shots - 1:
            print(f"  shot {i+1:3d}:  CH{CH_QSW} {e[CH_QSW]['t50']*1e9:11.3f}"
                  f"   CH{CH_LAMP} {e[CH_LAMP]['t50']*1e9:10.3f}"
                  f"   CH{CH_REF} {e[CH_REF]['t50']*1e9:10.3f} ns")

    if len(rows) < 3:
        print("\nNot enough good shots.")
        return 1

    def col(ch, key):
        return np.array([r[ch][key] for r in rows]) * 1e9

    out = {"n": len(rows), "settings": {"bnc_b_us": BNC_B_US,
                                        "lamp_us": LAMP_US, "qsw_us": QSW_US}}
    ref50, ref10 = col(CH_REF, "t50"), col(CH_REF, "t10")
    print(f"\n  {'':<32}{'record time':>14}{'jitter':>10}{'amp':>8}"
          f"{'rise':>9}")
    print("  " + "-" * 71)
    for tag, ch in (("qsw", CH_QSW), ("lamp", CH_LAMP), ("ref", CH_REF)):
        t50, t10 = col(ch, "t50"), col(ch, "t10")
        amp = float(np.mean([r[ch]["amp"] for r in rows]))
        rise = float(np.nanmean([r[ch]["rise"] for r in rows]) * 1e9)
        d50, d10 = t50 - ref50, t10 - ref10
        out[tag] = {
            "rec_ns": float(t50.mean()), "rec_sd_ps": float(t50.std(ddof=1) * 1e3),
            "d50_ns": float(d50.mean()), "d50_sd_ps": float(d50.std(ddof=1) * 1e3),
            "d10_ns": float(np.nanmean(d10)),
            "amp": amp, "rise_ns": rise,
        }
        print(f"  {NAMES[mode][ch]:<32}{t50.mean():11.3f} ns"
              f"{t50.std(ddof=1)*1e3:7.0f} ps{amp:7.2f} V{rise:7.1f} ns")
    for tag, ch in (("qsw", CH_QSW), ("lamp", CH_LAMP)):
        o = out[tag]
        print(f"  CH{ch} minus CH{CH_REF}: {o['d50_ns']:13.3f} ns, "
              f"jitter {o['d50_sd_ps']:.0f} ps")

    d = json.load(open(STORE)) if os.path.exists(STORE) else {}
    d[mode] = out
    json.dump(d, open(STORE, "w"), indent=2)
    print(f"\n  saved run '{mode}' in {STORE}")
    if "in" in d and "out" in d:
        print()
        do_solve()
    else:
        other = "out" if mode == "in" else "in"
        print(f"  Next: rewire for run '{other}' and run it.")
    return 0


# ---------------------------------------------------------------------------
# Solve
# ---------------------------------------------------------------------------
def do_solve():
    d = json.load(open(STORE)) if os.path.exists(STORE) else {}
    if "in" not in d or "out" not in d:
        print(f"Need both runs. Have: {sorted(d)}")
        return 1
    I, O = d["in"], d["out"]
    m = map_times()

    def se(a, b, n1, n2):
        return float(np.hypot(a / np.sqrt(n1), b / np.sqrt(n2)))

    q50 = O["qsw"]["d50_ns"] - I["qsw"]["d50_ns"]
    q10 = O["qsw"]["d10_ns"] - I["qsw"]["d10_ns"]
    qse = se(O["qsw"]["d50_sd_ps"], I["qsw"]["d50_sd_ps"], O["n"], I["n"])
    l50 = O["lamp"]["d50_ns"] - I["lamp"]["d50_ns"]
    lse = se(O["lamp"]["d50_sd_ps"], I["lamp"]["d50_sd_ps"], O["n"], I["n"])

    print("LASER 1 INTERNAL DELAYS (cables and scope cancel)")
    print("=" * 66)
    print(f"  Q-switch IN  -> Q-switch OUT   {q50:9.3f} ns  +/- {qse:.0f} ps"
          f"   (50% to 50%)")
    print(f"                                 {q10:9.3f} ns"
          f"               (10% to 10%)")
    print(f"      bench test, laser0.csv     {BENCH_QSW:9.3f} ns")
    print(f"      shot 43 with the map       {SHOT43_QSW:9.3f} ns")
    print(f"  Flashlamp IN -> Lamp OUT       {l50:9.3f} ns  +/- {lse:.0f} ps")
    print(f"      bench test, laser0.csv     {BENCH_LAMP:9.3f} ns")
    print(f"  jitter of Q-switch OUT against the DG535 T0 output: "
          f"{O['qsw']['d50_sd_ps']:.0f} ps rms")
    print(f"  Q-switch OUT risetime at the scope: {O['qsw']['rise_ns']:.1f} ns,"
          f" trigger risetime: {I['qsw']['rise_ns']:.1f} ns")

    # Absolute times. The reference fixes the DG535 T0 output on the T0 axis,
    # the same-channel differences carry everything else.
    ref_t0 = to_t0(0.5 * (I["ref"]["rec_ns"] + O["ref"]["rec_ns"]), CH_REF)
    qin = to_t0(I["qsw"]["rec_ns"], CH_QSW)
    lin = to_t0(I["lamp"]["rec_ns"], CH_LAMP)
    qout = to_t0(O["qsw"]["rec_ns"], CH_QSW)
    lout = to_t0(O["lamp"]["rec_ns"], CH_LAMP)

    print("\n\nTIMES AFTER T0, AND THE MAP")
    print("=" * 66)
    print(f"  {'':<30}{'measured':>14}{'map':>14}{'diff':>8}")
    print("  " + "-" * 64)
    for name, got, want in (
            ("DG535 T0 output", ref_t0, m["ref"]),
            ("Flashlamp trigger at laser 1", lin, m["lamp_in"]),
            ("Q-switch trigger at laser 1", qin, m["qsw_in"])):
        print(f"  {name:<30}{got:11.2f} ns{want:11.2f} ns{got-want:+8.2f}")
    print(f"  {'Lamp OUT at laser 1':<30}{lout:11.2f} ns")
    print(f"  {'Q-switch OUT at laser 1':<30}{qout:11.2f} ns")
    print("  Absolute times carry about 2 ns, because CH1 to CH3 borrow the")
    print("  CH4 scope offset. The differences above do not.")

    print(f"\n  Lamp trigger to Q-switch trigger   {qin-lin:12.2f} ns"
          f"   programmed {QSW_US*1e3:.0f}")
    print(f"  Lamp OUT to Q-switch OUT           {qout-lout:12.2f} ns")

    print("\n\nWHEN LASER 1 FIRES, shot 43 settings")
    print("=" * 66)
    print(f"  Q-switch trigger reaches laser 1   {qin/1e3:12.4f} us after T0")
    print(f"  Q-switch OUT edge leaves laser 1   {qout/1e3:12.4f} us after T0")
    print(f"  Light, about 70 ns later (manual)  {(qout+70)/1e3:12.4f} us "
          f"after T0, not measured")

    print("\n\nWHICH EARLIER NUMBER WAS RIGHT")
    print("=" * 66)
    if abs(q50 - BENCH_QSW) < abs(q50 - SHOT43_QSW):
        print(f"  {q50:.1f} ns sits closer to the bench test ({BENCH_QSW} ns).")
    else:
        print(f"  {q50:.1f} ns sits closer to the shot 43 value "
              f"({SHOT43_QSW} ns).")
    off = qin - m["qsw_in"]
    print(f"  The Q-switch trigger reaches laser 1 {off:+.2f} ns from where "
          f"the map puts it.")
    return 0


# ---------------------------------------------------------------------------
def main():
    args = [a.lower() for a in sys.argv[1:]]
    mode = args[0] if args else input(
        "Which run? Type in, out or solve: ").strip().lower()
    if mode == "solve":
        return do_solve()
    if mode not in ("in", "out"):
        print("Type in, out or solve.")
        return 1
    shots = int(args[1]) if len(args) > 1 else SHOTS

    from calibrate_channel import connect, open_bnc, SCOPE_IPS
    bnc, fire = open_bnc(BNC_PORT)
    rm, instr, res = connect(SCOPE_IPS.get(SCOPE, SCOPE), socket=True)
    sweep0 = None
    laser = None
    try:
        report_scope(instr)

        if mode == "out":
            print(f"\nLaser 1 on {LASER1_PORT}")
            laser = Laser1(LASER1_PORT)
            clear, summary = laser.check()
            print("  " + summary.replace("\n", "\n  "))
            if not clear:
                print("\nLaser 1 is not ready. Nothing was fired.")
                return 1
            ok = input("\nLaser 1 WILL FIRE on every shot. The beam must be "
                       "blocked. Type yes to go on: ").strip().lower()
            if ok != "yes":
                print("Stopped. Nothing was fired.")
                return 1

        try:
            sweep0 = instr.query(":TRIGger:SWEep?").strip()
            if not sweep0.upper().startswith("NORM"):
                instr.write(":TRIGger:SWEep NORMal")
        except Exception:
            sweep0 = None
        try:
            return do_run(mode, instr, fire, shots, laser)
        except LaserNotReady as e:
            print(f"\n{e}. Stopped.")
            return 1
    finally:
        if laser is not None:
            try:
                laser.close()
            except Exception as e:
                print(f"Laser 1 stop/close error: {e}")
        try:
            if sweep0 and not sweep0.upper().startswith("NORM"):
                instr.write(f":TRIGger:SWEep {sweep0}")
        except Exception:
            pass
        try:
            instr.close()
            rm.close()
        except Exception:
            pass
        if bnc is not None:
            bnc.close()


if __name__ == "__main__":
    sys.exit(main())
