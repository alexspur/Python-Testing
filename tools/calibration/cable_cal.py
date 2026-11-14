"""
Turn VNA cable measurements plus one calibration shot into a per-channel
timing offset referenced to the delay generator output.

What you end up with
--------------------
For any channel on any scope:

    time_since_DG_output = recorded_time + trig_cable_delay + offset[scope, ch]

`trig_cable_delay` comes from the .s1p of that scope's trigger cable.
`offset` lumps together everything you cannot measure separately: the EXT
comparator's propagation delay and that channel's own front-end delay. You do
not need them apart, only their sum, and one calibration shot gives it.

The model
---------
Let T0 be the instant the DG535 asserts its trigger output at the connector.

  - The trigger edge reaches scope M's EXT input at T0 + tau_trig[M].
  - Scope M places its internal t=0 near that moment, off by an unknown
    comparator delay.
  - A signal at channel N's connector at absolute time T_sig lands in the
    record at t_rec.

Collecting the unknowns into offset[M,N]:

    T_sig - T0 = t_rec + tau_trig[M] + offset[M,N]

Calibration drives a second DG535 output, programmed at delay dg_delay
relative to the trigger output, through a cable of known delay tau_cal into
channel N. Then T_sig - T0 is known to be dg_delay + tau_cal, so:

    offset[M,N] = dg_delay + tau_cal - tau_trig[M] - t_rec_cal

Every term on the right is measured. Average t_rec_cal over many shots to
beat the jitter down.
"""

from __future__ import annotations

import json
import os

import numpy as np


# ---------------------------------------------------------------------------
# Touchstone
# ---------------------------------------------------------------------------

def read_s1p(path):
    """Read a 1-port Touchstone file. Handles RI, MA and DB formats."""
    fmt, z0 = "ri", 50.0
    f, vals = [], []
    for line in open(path):
        s = line.strip()
        if not s or s.startswith("!"):
            continue
        if s.startswith("#"):
            tok = s[1:].split()
            low = [t.lower() for t in tok]
            for cand in ("ri", "ma", "db"):
                if cand in low:
                    fmt = cand
            if "r" in low:
                z0 = float(tok[low.index("r") + 1])
            mult = {"hz": 1, "khz": 1e3, "mhz": 1e6, "ghz": 1e9}
            unit = next((mult[t] for t in low if t in mult), 1)
            continue
        p = s.split()
        f.append(float(p[0]) * (unit if "unit" in dir() else 1))
        vals.append((float(p[1]), float(p[2])))

    f = np.asarray(f, float)
    a = np.asarray([v[0] for v in vals], float)
    b = np.asarray([v[1] for v in vals], float)
    if fmt == "ri":
        s11 = a + 1j * b
    elif fmt == "ma":
        s11 = a * np.exp(1j * np.radians(b))
    else:
        s11 = 10 ** (a / 20) * np.exp(1j * np.radians(b))
    return f, s11, z0


# ---------------------------------------------------------------------------
# Cable delay from S11
# ---------------------------------------------------------------------------

def cable_delay(path_or_data, fmin=1e6, fmax=None, vf=0.66, verbose=False):
    """One-way delay of an open- or short-terminated cable, from S11 phase.

    The far end must be left OPEN or SHORTED, never terminated in 50 ohms.
    A terminated cable reflects nothing and there is no phase slope to fit.

    Phase slope is used rather than a time-domain transform because a
    401-point sweep to 450 MHz only resolves about 1.1 ns in the time domain,
    while the phase fit reaches single-digit picoseconds.

    Returns a dict with the delay, its standard error, the implied physical
    length, and quality flags worth reading before you trust it.
    """
    if isinstance(path_or_data, (str, bytes, os.PathLike)):
        f, s11, _ = read_s1p(path_or_data)
        label = os.path.basename(str(path_or_data))
    else:
        f, s11 = path_or_data
        label = "data"

    if fmax is None:
        fmax = f[-1]

    warn = []
    mag_lo = float(np.abs(s11[f <= max(f[0], 2e6)]).mean())
    if mag_lo < 0.8:
        warn.append(f"|S11| is only {mag_lo:.2f} at low frequency. The far end "
                    f"should be open or shorted, not terminated.")

    ph_all = np.unwrap(np.angle(s11))

    # NanoVNA units switch harmonic bands partway up the sweep and leave a
    # phase step there. Find it so the fit can stop short of it.
    d = np.diff(ph_all)
    med, sd = np.median(d), np.std(d)
    jumps = np.flatnonzero(np.abs(d - med) > 5 * sd)
    if jumps.size:
        f_jump = f[jumps[0]]
        warn.append(f"phase discontinuity near {f_jump/1e6:.0f} MHz "
                    f"(instrument band switch), fit stops below it")
        fmax = min(fmax, f_jump * 0.97)

    m = (f >= fmin) & (f <= fmax)
    if m.sum() < 10:
        raise ValueError(f"{label}: only {m.sum()} usable points")

    ff, ph = f[m], ph_all[m]
    slope, icpt = np.polyfit(ff, ph, 1)
    resid = ph - (slope * ff + icpt)

    tau = -slope / (4 * np.pi)          # open/short: phase = -4 pi f tau
    n = ff.size
    slope_se = np.std(resid) / (np.std(ff) * np.sqrt(n))
    tau_se = slope_se / (4 * np.pi)

    rms_deg = float(np.degrees(np.std(resid)))
    if rms_deg > 8:
        warn.append(f"phase fit residual is {rms_deg:.1f} deg, poor fit")
    if tau <= 0:
        warn.append("negative delay, check the file")

    out = {
        "label": label,
        "delay_s": float(tau),
        "delay_ns": float(tau * 1e9),
        "stderr_ps": float(tau_se * 1e12),
        "length_m": float(tau * vf * 299792458.0),
        "fit_band_MHz": (fmin / 1e6, fmax / 1e6),
        "fit_points": int(n),
        "resid_rms_deg": rms_deg,
        "warnings": warn,
    }
    if verbose:
        print(f"{out['label']:<28} {out['delay_ns']:8.3f} ns "
              f"+/- {out['stderr_ps']:.1f} ps   {out['length_m']:.2f} m")
        for w in warn:
            print(f"{'':<28} note: {w}")
    return out


# ---------------------------------------------------------------------------
# Calibration table
# ---------------------------------------------------------------------------

class TimingCal:
    """Per-scope trigger cable delays and per-channel offsets.

    Save it next to the campaign data. An offset without the cable lengths and
    the date it was taken is not worth much six months later.
    """

    def __init__(self):
        self.trig_delay = {}     # {scope: seconds}
        self.offset = {}         # {"scope/ch": seconds}
        self.meta = {}

    # -- setup ----------------------------------------------------------

    def set_trig_cable(self, scope, s1p_path, **kw):
        r = cable_delay(s1p_path, **kw)
        self.trig_delay[str(scope)] = r["delay_s"]
        self.meta.setdefault("trig_cables", {})[str(scope)] = r
        return r

    def solve_offset(self, scope, channel, t_rec_cal, cal_cable_s1p=None,
                     cal_cable_delay=None, dg_delay=0.0):
        """Work out offset[scope, channel] from one calibration measurement.

        Args:
            t_rec_cal: edge time of the calibration pulse as it appears in the
                record, in seconds. Average several shots.
            cal_cable_s1p: .s1p of the cable feeding the channel, or
            cal_cable_delay: its delay in seconds if you already know it
            dg_delay: programmed delay of the calibration output relative to
                the trigger output. Zero if both fire together.
        """
        scope = str(scope)
        if scope not in self.trig_delay:
            raise KeyError(f"set_trig_cable({scope}, ...) first")

        if cal_cable_delay is None:
            if cal_cable_s1p is None:
                raise ValueError("give cal_cable_s1p or cal_cable_delay")
            r = cable_delay(cal_cable_s1p)
            cal_cable_delay = r["delay_s"]
            self.meta.setdefault("cal_cables", {})[f"{scope}/{channel}"] = r

        off = dg_delay + cal_cable_delay - self.trig_delay[scope] - t_rec_cal
        self.offset[f"{scope}/{channel}"] = float(off)
        return off

    # -- use ------------------------------------------------------------

    def to_dg_time(self, t_rec, scope, channel):
        """Convert a recorded time to time since the DG535 output fired."""
        scope = str(scope)
        key = f"{scope}/{channel}"
        if key not in self.offset:
            raise KeyError(f"no calibration for {key}")
        return np.asarray(t_rec) + self.trig_delay[scope] + self.offset[key]

    def channel_skew(self, scope):
        """Offsets of each channel on one scope, relative to its channel 1."""
        scope = str(scope)
        chans = {k.split("/")[1]: v for k, v in self.offset.items()
                 if k.startswith(scope + "/")}
        if not chans:
            return {}
        ref = chans.get("1", min(chans.values()))
        return {c: v - ref for c, v in sorted(chans.items())}

    # -- persistence ----------------------------------------------------

    def save(self, path):
        with open(path, "w") as f:
            json.dump({"trig_delay": self.trig_delay,
                       "offset": self.offset,
                       "meta": self.meta}, f, indent=2)

    @classmethod
    def load(cls, path):
        c = cls()
        d = json.load(open(path))
        c.trig_delay = d.get("trig_delay", {})
        c.offset = d.get("offset", {})
        c.meta = d.get("meta", {})
        return c

    def report(self):
        lines = ["Trigger cables, delay generator to EXT TRIG:"]
        if self.trig_delay:
            ref = min(self.trig_delay.values())
            for s in sorted(self.trig_delay):
                d = self.trig_delay[s]
                lines.append(f"  scope {s}: {d*1e9:8.3f} ns"
                             f"   ({(d-ref)*1e9:+6.3f} ns skew)")
        lines.append("")
        lines.append("Channel offsets (EXT comparator minus front-end delay):")
        for k in sorted(self.offset):
            lines.append(f"  {k:<10} {self.offset[k]*1e9:+8.3f} ns")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Demo on the three measured trigger cables
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import glob
    import sys

    paths = sys.argv[1:] or sorted(glob.glob("*Scope*.s1p"))
    if not paths:
        print("usage: python cable_cal.py Scope1.s1p Scope2.s1p Scope3.s1p")
        raise SystemExit(1)

    print("Cable delays from S11 phase slope\n")
    print(f"{'file':<28}{'1-way':>10}{'stderr':>9}{'length':>9}")
    print("-" * 56)
    results = {}
    for p in paths:
        r = cable_delay(p)
        results[p] = r
        print(f"{r['label']:<28}{r['delay_ns']:8.3f}ns{r['stderr_ps']:7.1f}ps"
              f"{r['length_m']:8.2f}m")
        for w in r["warnings"]:
            print(f"{'':<28}  note: {w}")

    taus = {p: r["delay_s"] for p, r in results.items()}
    ref = min(taus.values())
    print("\nSkew relative to the shortest cable:")
    for p in paths:
        print(f"  {results[p]['label']:<28}{(taus[p]-ref)*1e9:+8.3f} ns")

    print("\nThat skew is a fixed offset between the scopes' time axes.")
    print("Either match the cable lengths or carry it in the correction.")
