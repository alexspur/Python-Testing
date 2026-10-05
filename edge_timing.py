"""
Sub-sample edge timing and cross-scope alignment for the LTGS captures.

The problem this solves
-----------------------
The EXT TRIG input is never digitized. The scope uses it to start the
acquisition and then throws it away, so nothing in your CSV tells you where
the physical trigger edge actually was. Every time in the record is measured
against the scope's internal t=0, which differs from the edge at the BNC by:

  - the EXT comparator's analog propagation delay (unspecified by Rigol)
  - cable delay from the tee to that particular scope
  - trigger-level-vs-slew-rate error, which moves if the edge amplitude moves
  - shot-to-shot trigger jitter

Record the trigger pulse on a signal channel (a fiducial) and all four
collapse. Measuring signal-minus-fiducial cancels the trigger jitter exactly,
because jitter shifts the whole record and the fiducial rides along with it.

Timing is extracted at a fixed FRACTION of the edge amplitude, not at an
absolute voltage. An absolute threshold turns any shot-to-shot amplitude
change into an apparent timing change.

Achieved precision is well below one sample interval. See the self-test at the
bottom, which reports measured jitter against a known truth.
"""

from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# Edge timing
# ---------------------------------------------------------------------------

def edge_time(t, v, fraction=0.5, rising=True, baseline_frac=0.1,
              top_frac=0.9, fit_span=0.8, search=None):
    """Time at which an edge crosses `fraction` of its own amplitude.

    Args:
        t, v: time and voltage arrays for one channel
        fraction: crossing level as a fraction of the edge amplitude.
                  0.5 is the usual choice and is least sensitive to
                  risetime changes.
        rising: True for a rising edge, False for falling
        baseline_frac, top_frac: percentiles used to estimate the two levels,
                  robust against overshoot and ringing
        fit_span: fraction of the transition used for the straight-line fit.
                  0.8 keeps the fit inside the linear part of the edge.
        search: optional (t_min, t_max) window to look in, for records with
                  more than one edge

    Returns:
        float crossing time, or nan if no clean edge was found
    """
    t = np.asarray(t, dtype=float)
    v = np.asarray(v, dtype=float)

    if search is not None:
        m = (t >= search[0]) & (t <= search[1])
        t, v = t[m], v[m]
    if t.size < 4:
        return float("nan")

    # Levels from percentiles, so overshoot and ringing do not set the scale.
    lo = np.percentile(v, 100 * baseline_frac)
    hi = np.percentile(v, 100 * top_frac)
    amp = hi - lo
    if amp <= 0 or not np.isfinite(amp):
        return float("nan")

    level = lo + fraction * amp

    # First crossing in the requested direction.
    above = v >= level
    if rising:
        idx = np.flatnonzero((~above[:-1]) & above[1:])
    else:
        idx = np.flatnonzero(above[:-1] & (~above[1:]))
    if idx.size == 0:
        return float("nan")
    i = int(idx[0])

    # Straight-line fit through the samples inside the linear part of the
    # transition. More noise-immune than interpolating the two bracketing
    # samples, and it is what buys sub-sample precision.
    # Fit band, clamped to stay inside the real transition. Without the clamp a
    # low or high `fraction` pushes the band past the baseline or the top, the
    # walk below runs off into the flat part, and the fitted slope collapses.
    half = fit_span / 2.0
    band_lo = lo + max(fraction - half, 0.08) * amp
    band_hi = lo + min(fraction + half, 0.92) * amp
    lo_b, hi_b = min(band_lo, band_hi), max(band_lo, band_hi)

    # Bounded walk, so noise inside the band cannot drag the fit across the
    # whole record.
    max_walk = max(8, int(0.02 * v.size))

    j0 = i
    while j0 > 0 and lo_b <= v[j0 - 1] <= hi_b and (i - j0) < max_walk:
        j0 -= 1
    j1 = i + 1
    while j1 < v.size - 1 and lo_b <= v[j1 + 1] <= hi_b and (j1 - i) < max_walk:
        j1 += 1

    if j1 - j0 >= 2:
        tt, vv = t[j0:j1 + 1], v[j0:j1 + 1]
        slope, intercept = np.polyfit(tt, vv, 1)
        if slope != 0:
            return float((level - intercept) / slope)

    # Fall back to interpolating between the bracketing samples.
    v0, v1 = v[i], v[i + 1]
    if v1 == v0:
        return float(t[i])
    return float(t[i] + (level - v0) * (t[i + 1] - t[i]) / (v1 - v0))


def edge_stats(t, v, **kw):
    """Edge time plus the numbers you need to judge whether to trust it."""
    t = np.asarray(t, float)
    v = np.asarray(v, float)
    lo = np.percentile(v, 10)
    hi = np.percentile(v, 90)
    te = edge_time(t, v, **kw)

    t20 = edge_time(t, v, fraction=0.2, **{k: val for k, val in kw.items()
                                           if k != "fraction"})
    t80 = edge_time(t, v, fraction=0.8, **{k: val for k, val in kw.items()
                                           if k != "fraction"})
    rise = t80 - t20 if np.isfinite(t20) and np.isfinite(t80) else float("nan")

    dt = float(t[1] - t[0]) if t.size > 1 else float("nan")
    noise = float(np.std(v[v <= np.percentile(v, 20)]))
    slew = (0.6 * (hi - lo) / rise) if rise and np.isfinite(rise) else float("nan")

    return {
        "edge_time": te,
        "amplitude": float(hi - lo),
        "risetime_20_80": rise,
        "sample_interval": dt,
        "samples_on_edge": rise / dt if dt and np.isfinite(rise) else float("nan"),
        "baseline_noise_rms": noise,
        # Timing uncertainty from amplitude noise on a finite slew rate.
        "timing_sigma_est": noise / slew if slew and np.isfinite(slew) else float("nan"),
    }


# ---------------------------------------------------------------------------
# Using a fiducial
# ---------------------------------------------------------------------------

def delay_from_fiducial(t, v_signal, v_fiducial, **kw):
    """Delay from the recorded trigger edge to the signal edge.

    This is the number that is actually meaningful. It does not depend on
    where the scope put t=0, so it is immune to trigger jitter, EXT
    comparator delay, and the cable run to that scope.
    """
    t_fid = edge_time(t, v_fiducial, **kw)
    t_sig = edge_time(t, v_signal, **kw)
    return t_sig - t_fid


def align_records(records, **kw):
    """Put several scopes on one common time axis using their fiducials.

    Args:
        records: {name: (t, v_fiducial)}

    Returns:
        {name: shift} to ADD to that scope's time axis so every fiducial
        lands at t=0. Apply the same shift to every channel of that scope.
    """
    shifts = {}
    for name, (t, v_fid) in records.items():
        shifts[name] = -edge_time(np.asarray(t), np.asarray(v_fid), **kw)
    return shifts


# ---------------------------------------------------------------------------
# DG535 sweep calibration
# ---------------------------------------------------------------------------

def fit_delay_sweep(programmed, measured):
    """Fit measured delay against DG535 programmed delay.

    Sweeping the delay generator and fitting is far more trustworthy than one
    absolute reading. The DG535's delay RESOLUTION and JITTER are orders of
    magnitude better than its absolute accuracy, so the slope and the scatter
    are solid even where the intercept carries the generator's absolute error
    plus every fixed delay in your chain.

    Returns:
        slope      should be 1.0000. Deviation is scope timebase error.
        offset     fixed delay of the chain for this scope, in seconds.
                   Subtract it from measurements.
        residual_rms  shot-to-shot timing repeatability, in seconds.
    """
    p = np.asarray(programmed, float)
    m = np.asarray(measured, float)
    good = np.isfinite(p) & np.isfinite(m)
    p, m = p[good], m[good]
    if p.size < 2:
        return {"slope": float("nan"), "offset": float("nan"),
                "residual_rms": float("nan"), "n": int(p.size)}

    slope, offset = np.polyfit(p, m, 1)
    resid = m - (slope * p + offset)
    return {
        "slope": float(slope),
        "offset": float(offset),
        "residual_rms": float(np.std(resid)),
        "residual_max": float(np.max(np.abs(resid))),
        "n": int(p.size),
        "timebase_error_ppm": float((slope - 1.0) * 1e6),
    }


# ---------------------------------------------------------------------------
# Cable delay reference
# ---------------------------------------------------------------------------

CABLE_NS_PER_M = {
    "RG-58 solid PE (VF 0.66)": 5.05,
    "RG-58 foam PE (VF 0.78)": 4.27,
    "RG-174 solid PE (VF 0.66)": 5.05,
    "RG-213 solid PE (VF 0.66)": 5.05,
    "RG-400 PTFE (VF 0.70)": 4.76,
    "LMR-240 (VF 0.84)": 3.97,
    "air line (VF 1.00)": 3.34,
}


def cable_delay(length_m, cable="RG-58 solid PE (VF 0.66)"):
    """Propagation delay of a coax run, in seconds."""
    return length_m * CABLE_NS_PER_M[cable] * 1e-9


# ---------------------------------------------------------------------------
# Self-test: what precision is actually achievable at 2.5 GSa/s
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    rng = np.random.default_rng(0)
    fs = 2.5e9                     # your four-channel sample rate
    dt = 1 / fs
    n = 4000
    t = np.arange(n) * dt - 400e-9

    def make_edge(t0, risetime, amp=1.0, noise=0.0, quantize=True, axis=None):
        """Smooth edge at t0, 8-bit quantized the way the scope delivers it."""
        tt = t if axis is None else axis
        tau = risetime / 2.2        # 20-80 risetime to tanh width
        v = amp * 0.5 * (1 + np.tanh((tt - t0) / tau))
        v = v + rng.normal(0, noise, tt.size)
        if quantize:
            counts = np.clip(np.round(v / amp * 100) + 128, 0, 255)
            v = (counts - 128) * (amp / 100)
        return v

    print("Edge timing precision at 2.5 GSa/s (400 ps sample interval)")
    print("8-bit quantized, error on a 1 V edge\n")
    print(f"{'risetime':>10} {'noise':>8} {'samples':>8} {'bias':>10} {'jitter':>10}")
    print("-" * 50)

    for rise in (0.5e-9, 1e-9, 2e-9, 5e-9):
        for noise in (0.002, 0.01):
            errs = []
            for _ in range(200):
                true_t0 = rng.uniform(-50e-9, 50e-9)
                v = make_edge(true_t0, rise, noise=noise)
                est = edge_time(t, v, fraction=0.5)
                if np.isfinite(est):
                    errs.append(est - true_t0)
            errs = np.array(errs)
            print(f"{rise*1e9:9.1f}n {noise*1e3:7.0f}m {rise/dt:8.1f} "
                  f"{np.mean(errs)*1e12:9.1f}p {np.std(errs)*1e12:9.1f}p")

    print("\nsamples = how many samples span the 20-80 transition")
    print("jitter  = 1 sigma timing error, the number that matters")
    print(f"\nOne sample interval is {dt*1e12:.0f} ps. Interpolation beats it"
          f" comfortably\nwhen the edge spans more than about two samples.")

    # The claim that matters: a fiducial cancels trigger jitter.
    print("\n\nDoes a fiducial actually cancel trigger jitter?")
    print("True signal-to-trigger delay is fixed at 120.000 ns.")
    print("The scope's trigger jitters by 500 ps RMS, which shifts the whole")
    print("record, fiducial and signal together.\n")

    true_delay = 120e-9
    raw, corrected = [], []
    for _ in range(300):
        jit = rng.normal(0, 500e-12)        # trigger jitter shifts the record
        v_fid = make_edge(-80e-9 - jit, 1e-9, noise=0.004)
        v_sig = make_edge(-80e-9 + true_delay - jit, 1e-9, noise=0.004)
        # Naive: trust the scope's t=0 and read the signal edge directly.
        raw.append(edge_time(t, v_sig) - (-80e-9))
        # With a fiducial: measure signal against the recorded trigger edge.
        corrected.append(delay_from_fiducial(t, v_sig, v_fid))

    for label, arr in (("against scope t=0", raw),
                       ("against fiducial ", corrected)):
        a = np.array(arr)
        print(f"  {label}  mean {np.mean(a)*1e9:8.3f} ns   "
              f"jitter {np.std(a)*1e12:7.1f} ps")
    print(f"\n  The fiducial removes the 500 ps trigger jitter entirely. What")
    print(f"  is left is just the edge-timing noise from the two readings.")

    print("\n\nCable delay reference:")
    for k, v in CABLE_NS_PER_M.items():
        print(f"  {k:<28} {v:.2f} ns/m   ({v*0.3048:.2f} ns/ft)")
    print(f"\n  1 m of RG-58 skew = {cable_delay(1)*1e9:.2f} ns, which is "
          f"{cable_delay(1)/dt:.1f} sample intervals")
