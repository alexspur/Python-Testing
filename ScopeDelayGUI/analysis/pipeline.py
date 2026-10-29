"""Double-pulse waveform pipeline.

Python port of process_waveforms() in process_shots.m (the July pipeline).
The math is the same line for line. Differences from MATLAB are limited to
indexing (0-based here) and library calls, and each helper below names the
MATLAB function it reproduces so the two can be checked side by side.

Time axes of the outputs are in microseconds with pulse 1 at t = 0.
Voltages are in kV. Q-switch monitors stay in volts.
"""

from __future__ import annotations

import numpy as np
from scipy.integrate import cumulative_trapezoid
from scipy.ndimage import maximum_filter1d

# ---------------------------------------------------------------------------
# Calibration and channel map.
# Source: Multipulse_Calibrations_and_Connections.xlsx, "Calibration Matrix"
# and "Scope Connections" sheets (L-3 certificates, 2019). The 20 dB pads are
# already in the scope probe ratio (x10), so exported volts include them.
# ---------------------------------------------------------------------------
CAL = {
    # rigol2
    "CF_CH1": 1.85e11,   # CH1 LTGS2-232 D-dot, FC011
    "CF_CH2": -6.51e8,   # CH2 LTGS2-007 B-dot, FC013
    "CF_CH3": 1.83e11,   # CH3 LTGS1-232 D-dot, FC017
    "CF_CH4": -6.70e8,   # CH4 LTGS1-007 B-dot, FC016
    # rigol3
    "CF3_CH3": -6.96e8,  # CH3 C315 B-dot, FC027
    "CF3_CH4": 1.56e11,  # CH4 C225 D-dot, FC032
    "geom": 2 * np.pi * 7.5,
    "bScale": -4.5,
    # rigol1 RVM divider corrections (scope probe ratio is 20000:1)
    "DIV_CH1": 19588.6 / 20000,
    "DIV_CH2": 19970.7 / 20000,
}

# B-dot baseline windows (all B-dots: LTGS1, LTGS2, C315). Not the July
# windows: see reconstruct_bdot for why and for what they were tested on.
BDOT_PRE_S = 1.0e-6         # offset / zero window: this long, ending 50 ns before pulse 1
BDOT_POST_GAP_S = 0.3e-6    # post window starts this long after the last activity
BDOT_POST_LEN_S = 1.0e-6    # and is this long; the trace ends with it

# Signal names per scope channel, for the raw-channel plot.
CHANNEL_NAMES = {
    1: ["RVM 1", "RVM 2", "Trig monitor", "Trig gen out"],
    2: ["LTGS2-232 D-dot", "LTGS2-007 B-dot", "LTGS1-232 D-dot", "LTGS1-007 B-dot"],
    3: ["L1 Q-switch", "L2 Q-switch", "C315 B-dot", "C225 D-dot"],
}


class NoPulse(Exception):
    """No pulse on any anchor channel: a dry run or a shot that did not fire."""


# ===================== MATLAB equivalents =====================
def mround(x):
    """MATLAB round(): halves go away from zero (Python rounds to even)."""
    return int(np.sign(x) * np.floor(abs(x) + 0.5))


def movmax(x, k):
    """MATLAB movmax(x, k) with shrinking end windows.

    Odd k is centered. Even k spans k/2 samples back and k/2 - 1 forward,
    which is what maximum_filter1d does with origin 0. mode='nearest' gives
    the same result as a shrinking window for a max.
    """
    return maximum_filter1d(np.asarray(x, dtype=float), size=int(k), mode="nearest")


def movmean(x, k):
    """MATLAB movmean(x, k) for odd k, shrinking at the ends."""
    x = np.asarray(x, dtype=float)
    h = (int(k) - 1) // 2
    c = np.concatenate(([0.0], np.cumsum(x)))
    i = np.arange(x.size)
    lo = np.maximum(i - h, 0)
    hi = np.minimum(i + h + 1, x.size)
    return (c[hi] - c[lo]) / (hi - lo)


def interp_extrap(xq, x, y):
    """MATLAB interp1(x, y, xq, 'linear', 'extrap') for increasing x."""
    out = np.interp(xq, x, y)
    lo = xq < x[0]
    hi = xq > x[-1]
    if lo.any():
        out[lo] = y[0] + (xq[lo] - x[0]) * (y[1] - y[0]) / (x[1] - x[0])
    if hi.any():
        out[hi] = y[-1] + (xq[hi] - x[-1]) * (y[-1] - y[-2]) / (x[-1] - x[-2])
    return out


def cumtrapz(t, v):
    return cumulative_trapezoid(v, t, initial=0.0)


def polyfit_mu(x, y, deg):
    """MATLAB [p, ~, mu] = polyfit(x, y, deg). Returns a callable fit."""
    mu0 = x.mean()
    mu1 = x.std(ddof=1)
    p = np.polyfit((x - mu0) / mu1, y, deg)
    return lambda xx: np.polyval(p, (xx - mu0) / mu1)


def inwin(t, w):
    """Open window (w0 < t < w1), as the MATLAB code writes most masks."""
    return (t > w[0]) & (t < w[1])


def sample_dt(t):
    """Sample interval from the whole record, not t[1] - t[0]. Some July
    exports repeat a time value (limited digits), which made t[1] - t[0]
    zero and crashed the run. Same value as t[1] - t[0] on a clean record."""
    n = len(t)
    dt = (t[-1] - t[0]) / (n - 1) if n > 1 else 0.0
    if not np.isfinite(dt) or dt <= 0:
        raise ValueError("time column does not increase")
    return float(dt)


# ===================== file reading =====================
def read_rigol(path):
    """Rigol export: time plus four channels, one header line.

    Handles both headers the GUI has written ("time_s,ch1_v,..." and
    "Time (s),Voltage_CH1 (V),..."). Rows with a non-finite time are dropped,
    as in read_rigol.m.
    """
    try:
        import pandas as pd
        M = pd.read_csv(path, header=0, dtype=float, engine="c").to_numpy()
    except ImportError:
        M = np.loadtxt(path, delimiter=",", skiprows=1)
    if M.ndim != 2 or M.shape[1] < 5:
        raise ValueError(f"{path} has {M.shape[1] if M.ndim == 2 else 1} columns, "
                         "expected time plus 4 channels")
    return M[np.isfinite(M[:, 0])]


# ===================== pipeline helpers =====================
def gate_qsw(t, v, min_dur=100e-9, pad=60e-9, thr_frac=0.5, smooth_s=20e-9):
    """Gate the Q-switch sync pulse and return its rise time.

    One change from July: the pulse height "hi" is the peak of a 20 ns
    moving mean, not the 98th percentile. On a 1,000,000-point record
    (400 us) the ~1 us sync pulse is 0.25% of the samples, so the 98th
    percentile lands in the baseline noise and the pulse is missed or
    thresholded at noise level. The moving mean keeps single-sample spikes
    from setting the height. Everything else is the July logic.
    """
    dt = sample_dt(t)
    lo = np.median(v)
    hi = movmean(v, 2 * mround(smooth_s / dt / 2) + 1).max()
    vg = np.zeros_like(v, dtype=float)
    if (hi - lo) < 0.3:
        return vg, np.nan
    thr = lo + thr_frac * (hi - lo)
    above = (v > thr).astype(np.int8)
    d = np.diff(np.concatenate(([0], above, [0])))
    run_start = np.flatnonzero(d == 1)
    run_end = np.flatnonzero(d == -1) - 1
    if run_start.size == 0:
        return vg, np.nan
    lens = run_end - run_start + 1
    ib = int(np.argmax(lens))
    if lens[ib] * dt < min_dur:
        return vg, np.nan
    a0, b0 = run_start[ib], run_end[ib]
    padn = mround(pad / dt)
    a = max(0, a0 - padn)
    b = min(v.size - 1, b0 + padn)
    vg[a:b + 1] = v[a:b + 1] - lo
    return vg, t[a0]


def first_edge(t, v, frac=0.5, smooth_s=5e-9, min_snr=10.0):
    """Time of the first sample where the 5 ns mean of v reaches frac of its
    largest excursion from the median, either polarity. NaN when the largest
    excursion is under min_snr times the noise (robust, from the MAD), i.e.
    no pulse on the channel."""
    dt = sample_dt(t)
    med = np.median(v)
    dev = np.abs(movmean(v, 2 * mround(smooth_s / dt / 2) + 1) - med)
    noise = 1.4826 * np.median(np.abs(v - med))
    top = dev.max()
    if top <= 0 or top < min_snr * noise:
        return np.nan
    return float(t[np.flatnonzero(dev >= frac * top)[0]])


def detect_activity(t, v, k=10, env_s=200e-9, noise_s=500e-9):
    """Returns (tStart, tEnd, above). tStart is None when nothing is found."""
    v0 = v - np.median(v)
    dt = sample_dt(t)
    wn = max(8, mround(noise_s / dt))
    nb = v0.size // wn
    blk = v0[:nb * wn].reshape(nb, wn)
    s = np.sort(blk.std(axis=1, ddof=1))
    sig = s[max(1, mround(0.25 * s.size)) - 1]
    env = movmax(np.abs(v0), max(3, mround(env_s / dt)))
    above = env > k * sig
    if not above.any():
        return None, None, above
    idx = np.flatnonzero(above)
    return t[idx[0]], t[idx[-1]], above


def remove_offset_step(t, v, pre_win, post_win, tPulse, tEnd):
    vp = v[inwin(t, pre_win)].mean()
    vq = v[inwin(t, post_win)].mean()
    off = np.full(v.shape, vp)
    r = (t >= tPulse) & (t <= tEnd)
    off[r] = vp + (vq - vp) * (t[r] - tPulse) / (tEnd - tPulse)
    off[t > tEnd] = vq
    return v - off


def reconstruct(ti, vi, CF, zero_win, droop_pre, droop_post):
    integ = cumtrapz(ti, vi)
    pm = inwin(ti, droop_pre) | inwin(ti, droop_post)
    p = np.polyfit(ti[pm], integ[pm], 1)
    integ = integ - np.polyval(p, ti)
    integ = integ - integ[inwin(ti, zero_win)].mean()
    return CF * integ


def reconstruct_quiet(ti, vi, CF, zero_win, act_mask, deg):
    integ = cumtrapz(ti, vi)
    q = ~act_mask
    fit = polyfit_mu(ti[q], integ[q], deg)
    integ = integ - fit(ti)
    integ = integ - integ[inwin(ti, zero_win)].mean()
    return CF * integ


def reconstruct_bdot(t, v, CF, tPulse, tEnd):
    """Z*I from a B-dot record: offset removed, integrated, baseline fitted
    on quiet windows right next to the pulse. Returns (t, Z*I in volts,
    warning or "").

    Used for the LTGS B-dots and C315. C225 uses reconstruct_ddot, the same
    windows with a cubic baseline.

    Changed from July (py-3). The July code took the raw offset from 4-8 us
    before the pulse, zeroed on 0.3-0.05 us before, and fitted the integral
    baseline through 3-8 us after the pulse (C315: pre-pulse only, then
    integrated to the end of the 400 us record). These channels sit at
    25-50 V/div with ~1 V of noise and a baseline that wanders ~0.15 V on a
    microsecond scale, and after the pulse the raw offset steps by up to
    ~0.2 V. Integrated at CF*geom*bScale ~ 1.4e11, 0.1 V of offset error is
    ~14 kV per us, so distant windows left 13-18 kV of tilt/offset after the
    pulse (median over the 2026-09-24 fired shots) and let C315 ramp to
    thousands of kV. With 1 us windows either side of the pulse the offset
    left after the pulse is under 1 kV, the noise floor on dry shots drops
    from 12-15 kV to 4-6 kV, and the peaks move by under 2 %.
    """
    pre = (max(tPulse - BDOT_PRE_S, t[0]), tPulse - 0.05e-6)
    post = (tEnd + BDOT_POST_GAP_S, tEnd + BDOT_POST_GAP_S + BDOT_POST_LEN_S)
    v = remove_offset_step(t, v, pre, post, tPulse, tEnd) if inwin(t, post).sum() >= 10         else v - v[inwin(t, pre)].mean()
    # The trace stops at the end of the post window: past it nothing pins the
    # baseline, and the wander integrates into tens of kV of false drift
    # within a few us.
    im = (t >= pre[0]) & (t <= min(post[1], t[-1]))
    ti = t[im]
    integ = cumtrapz(ti, v[im])
    pm, qm = inwin(ti, pre), inwin(ti, post)
    warn = ""
    if qm.sum() >= 10:
        p = np.polyfit(ti[pm | qm], integ[pm | qm], 1)
        integ = integ - np.polyval(p, ti)
    else:
        warn = "record ends before the post-pulse baseline window; pre-pulse zero only"
    integ = integ - integ[pm].mean()
    return ti, CF * integ, warn


def reconstruct_ddot(t, v, CF, tPulse, tEnd):
    """C225 D-dot (py-5). Same windows as reconstruct_bdot: 1 us before the
    pulse and 1 us after the last activity. The raw offset is ramped from
    the pre window mean to the post window mean, the signal is integrated,
    and a cubic in time is fitted through the integral in both windows and
    subtracted. The cubic matches the level and the slope on each side, so
    an offset that drifts during the pulses no longer leaves a step or a
    tilt after them. Tested on shots 43, 49, 50 and 51 against C315: rms
    difference outside the pulses 2 kV (straight line: 3 kV, pre-only zero:
    up to 28 kV on shot 51). Returns (t, integral * CF, warning or "")."""
    pre = (max(tPulse - BDOT_PRE_S, t[0]), tPulse - 0.05e-6)
    post = (tEnd + BDOT_POST_GAP_S, tEnd + BDOT_POST_GAP_S + BDOT_POST_LEN_S)
    if inwin(t, post).sum() >= 10:
        v = remove_offset_step(t, v, pre, post, tPulse, tEnd)
    else:
        v = v - v[inwin(t, pre)].mean()
    im = (t >= pre[0]) & (t <= min(post[1], t[-1]))
    ti = t[im]
    integ = cumtrapz(ti, v[im])
    pm, qm = inwin(ti, pre), inwin(ti, post)
    warn = ""
    x = (ti - tPulse) * 1e6          # us from pulse 1, keeps the fit well scaled
    if qm.sum() >= 10:
        p = np.polyfit(x[pm | qm], integ[pm | qm], 3)
        integ = integ - np.polyval(p, x)
    else:
        warn = "record ends before the post-pulse baseline window; pre-pulse zero only"
    integ = integ - integ[pm].mean()
    return ti, CF * integ, warn


# ===================== main pipeline =====================
def process_waveforms(fr, fd, f3, cal=CAL):
    """Process one shot. fr, fd, f3 are the rigol1, rigol2 and rigol3 files,
    or already-loaded arrays. Returns a dict with the same field names as
    the MATLAB struct S. Raises NoPulse for a dry shot."""
    c = cal
    Md = fd if isinstance(fd, np.ndarray) else read_rigol(fd)
    M3 = f3 if isinstance(f3, np.ndarray) else read_rigol(f3)
    Mr = fr if isinstance(fr, np.ndarray) else read_rigol(fr)
    td, t3, tr = Md[:, 0], M3[:, 0], Mr[:, 0]

    # ---- detection ----
    starts, ends = [], []
    for tt, vv in ((td, Md[:, 3]), (td, Md[:, 4]), (t3, M3[:, 4])):
        s0, e0, _ = detect_activity(tt, vv)
        if s0 is not None:
            starts.append(s0)
            ends.append(e0)
    if not starts:
        raise NoPulse("no pulse detected on any anchor channel")
    tPulse = float(np.median(starts))
    tEnd = float(max(ends))

    # ---- windows ----
    base_win = (tPulse - 8e-6, tPulse - 4e-6)
    droop_pre = base_win
    droop_post = (tEnd + 3e-6, min(tEnd + 8e-6, td[-1]))
    int_win = (tPulse - 6e-6, droop_post[1])
    evt_win = (tPulse - 1e-6, tEnd + 1e-6)
    r3_pre = (max(tPulse - 2e-6, t3[0] + 0.1e-6), tPulse - 0.3e-6)
    c3_zero = (max(tPulse - 0.9e-6, t3[0]), tPulse - 0.1e-6)

    S = {"tPulse": tPulse, "tEnd": tEnd, "peaks": {}, "warnings": []}
    pk = S["peaks"]

    # ---- D-dots (rigol2): LTGS1 = CH3, LTGS2 = CH1 ----
    S["Dt"], S["Dv"], S["Dv_raw"] = [None, None], [None, None], [None, None]
    for k, (col, CF) in enumerate(((3, c["CF_CH3"]), (1, c["CF_CH1"]))):
        v = remove_offset_step(td, Md[:, col], base_win, droop_post, tPulse, tEnd)
        im = (td >= int_win[0]) & (td <= int_win[1])
        ti, vi = td[im], v[im]
        Vr = reconstruct(ti, vi, CF, base_win, droop_pre, droop_post)
        S["Dt"][k] = (ti - tPulse) * 1e6
        S["Dv_raw"][k] = Vr / 1e3

    # ---- B-dots (rigol2), Z*I: LTGS1 = CH4, LTGS2 = CH2 ----
    S["Bt"], S["Bv"] = [None, None], [None, None]
    for k, (col, CF, tag) in enumerate(((4, c["CF_CH4"], "LTGS1_Bdot"),
                                        (2, c["CF_CH2"], "LTGS2_Bdot"))):
        ti, Vr, warn = reconstruct_bdot(td, Md[:, col], CF * c["geom"] * c["bScale"],
                                        tPulse, tEnd)
        if warn:
            S["warnings"].append(f"{tag}: {warn}")
        S["Bt"][k] = (ti - tPulse) * 1e6
        S["Bv"][k] = Vr / 1e3
        pk[tag] = np.abs(Vr[inwin(ti, evt_win)]).max() / 1e3

    # ---- rigol3: C225 and C315, both with the B-dot pre/post baseline ----
    # Both need rigol3 samples before pulse 1. When scope 3's record starts
    # too late (its own timebase delay), C225 and C315 are skipped with a
    # warning instead of failing the whole shot. The LTGS and RVM results
    # above do not depend on them.
    #
    # C225 (py-5): reconstruct_ddot, the B-dot windows with a cubic baseline
    # through both windows, D-dot factor only (no geom, no bScale). It used the whole-record cubic (reconstruct_quiet), and before
    # that a zero set only before the pulse. C225 sits at 25 V/div, 1.075 V
    # per count, so a 0.1 V offset error is 15.6 kV per us. On shot 51
    # (13 Oct 2026) the raw offset sagged about 0.10 V during the pulses and
    # the pre-only zero turned that into a 15 to 25 kV false step after
    # pulse 1, while C315 stayed at zero. Pinning a window after the pulse
    # as well removes it. Edges move under 2 ns, peaks up to 16 kV.
    # See reconstruct_ddot.
    bm = inwin(t3, r3_pre)
    if bm.sum() < 10 or inwin(t3, c3_zero).sum() < 10:
        S["warnings"].append(
            f"C225/C315 skipped: scope 3 record starts at {t3[0] * 1e6:.2f} us, "
            f"after the pre-pulse window (pulse 1 at {tPulse * 1e6:.2f} us)")
        S["C225_t"], S["C225"] = np.array([]), np.array([])
        S["C315_t"], S["C315"] = np.array([]), np.array([])
        pk["C225_Ddot"] = np.nan
        pk["C315_Bdot"] = np.nan
    else:
        ti3c, C225, warn = reconstruct_ddot(t3, M3[:, 4], c["CF3_CH4"], tPulse, tEnd)
        if warn:
            S["warnings"].append(f"C225_Ddot: {warn}")
        S["C225_t"] = (ti3c - tPulse) * 1e6
        S["C225"] = C225 / 1e3
        pk["C225_Ddot"] = np.abs(C225[inwin(ti3c, evt_win)]).max() / 1e3

        ti3, C315, warn = reconstruct_bdot(t3, M3[:, 3],
                                           c["CF3_CH3"] * c["geom"] * c["bScale"], tPulse, tEnd)
        if warn:
            S["warnings"].append(f"C315_Bdot: {warn}")
        S["C315_t"] = (ti3 - tPulse) * 1e6
        S["C315"] = C315 / 1e3
        # Peak over the event only, like every other channel. It was the max
        # over the whole integrated record, i.e. wherever the drift ended up.
        pk["C315_Bdot"] = np.abs(C315[inwin(ti3, evt_win)]).max() / 1e3

    # ---- rigol3 Q-switch monitors: CH1 = Laser1, CH2 = Laser2 ----
    S["Qt"], S["Qv"] = [None, None], [None, None]
    for k, (col, tag) in enumerate(((1, "Qsw1"), (2, "Qsw2"))):
        vg, tRise = gate_qsw(t3, M3[:, col])
        S["Qt"][k] = (t3 - tPulse) * 1e6
        S["Qv"][k] = vg
        pk["t_" + tag] = (tRise - tPulse) * 1e6 if np.isfinite(tRise) else np.nan

    # ---- RVMs (rigol1), trimmed to the analysis span ----
    S["Rt"], S["Rv"] = [None, None], [None, None]
    imr = (tr >= int_win[0]) & (tr <= int_win[1])
    bmr = inwin(tr, base_win)
    for k, (col, div, tag) in enumerate(((1, c["DIV_CH1"], "RVM1"),
                                         (2, c["DIV_CH2"], "RVM2"))):
        v = Mr[:, col]
        Vr = div * (v - v[bmr].mean())
        S["Rt"][k] = (tr[imr] - tPulse) * 1e6
        S["Rv"][k] = Vr[imr] / 1e3
        pk[tag] = np.abs(Vr[inwin(tr, evt_win)]).max() / 1e3

    # ---- trigger signals (rigol1), raw volts as recorded, same span as the
    # RVMs: CH3 trig monitor, CH4 trig gen out. For viewing, plus the time of
    # the trig gen out edge (us from pulse 1, NaN if there is no pulse).
    S["Trig_t"] = (tr[imr] - tPulse) * 1e6
    S["TrigMon_v"] = Mr[imr, 3]
    S["TrigOut_v"] = Mr[imr, 4]
    pk["t_TrigOut"] = (first_edge(tr[imr], Mr[imr, 4]) - tPulse) * 1e6

    # ---- RVM-referenced baseline correction for the D-dots ----
    S["rvm_gain"] = np.zeros(2)
    S["rvm_ref"] = np.zeros(2)
    S["rvm_rampRMS"] = np.zeros(2)
    G = np.zeros((2, 2))
    for k, tag in enumerate(("LTGS1_Ddot", "LTGS2_Ddot")):
        Dt, Dr = S["Dt"][k], S["Dv_raw"][k]
        rampm = (Dt > -3) & (Dt < -0.2)
        best, Vref = np.inf, None
        for r in range(2):
            Vr0 = interp_extrap(Dt, S["Rt"][r], S["Rv"][r])
            gg = (Vr0[rampm] @ Dr[rampm]) / (Vr0[rampm] @ Vr0[rampm])
            G[k, r] = gg
            rms = np.sqrt(np.mean((Dr[rampm] - gg * Vr0[rampm]) ** 2))
            if rms < best:
                best, Vref = rms, gg * Vr0
                S["rvm_gain"][k] = gg
                S["rvm_ref"][k] = r + 1
        S["rvm_rampRMS"][k] = best
        g = S["rvm_gain"][k]
        if g < 0.5 or g > 1.6 or best > 60:
            Dv = Dr.copy()
            S["rvm_gain"][k] = np.nan
        else:
            dtu = Dt[1] - Dt[0]
            w = max(3, 2 * int(np.floor(0.4 / dtu)) + 1)
            cc = movmean(Dr - Vref, w)
            gl = int(np.flatnonzero(Dt >= -0.3)[0])
            ghi = np.flatnonzero(Dt >= (tEnd - tPulse) * 1e6 + 0.8)
            gh = int(ghi[0]) if ghi.size else cc.size - 1
            cc[gl:gh + 1] = np.linspace(cc[gl], cc[gh], gh - gl + 1)
            Dv = Dr - cc
        S["Dv"][k] = Dv
        wm = (Dt > -1) & (Dt < (tEnd - tPulse) * 1e6 + 1)
        pk[tag] = np.abs(Dv[wm]).max()

    # ---- 2x2 gain factorization ----
    S["G"] = G
    if np.all(G > 0):
        L = np.log(G)
        S["ddot_factor"] = np.exp(L.mean(axis=1) - L.mean())
        S["rvm_factor"] = np.exp(L.mean(axis=0) - L.mean())
        S["G_consistency"] = G[0, 0] * G[1, 1] / (G[0, 1] * G[1, 0])
    else:
        S["ddot_factor"] = np.array([np.nan, np.nan])
        S["rvm_factor"] = np.array([np.nan, np.nan])
        S["G_consistency"] = np.nan
    return S


# ===================== measured spacing =====================
def spacing_from_rvm(S):
    """Time between the two RVM collapse edges (half-minimum crossing), ns."""
    if "Rt" not in S:
        return np.nan
    e = [np.nan, np.nan]
    for r in range(2):
        t = S["Rt"][r]
        v = movmean(S["Rv"][r], 51)
        if v.size == 0:
            continue
        imin = int(np.argmin(v))
        vmin = v[imin]
        if vmin < -50:
            thr = 0.5 * vmin
            j = np.flatnonzero(v[imin:] > thr)
            if j.size and j[0] + imin > 0:
                j = int(j[0] + imin)
                if v[j] == v[j - 1]:
                    e[r] = t[j]
                else:
                    e[r] = t[j - 1] + (thr - v[j - 1]) * (t[j] - t[j - 1]) / (v[j] - v[j - 1])
    return abs(e[1] - e[0]) * 1e3


def spacing_from_qsw(S):
    """Laser 2 Q-switch rise minus laser 1 Q-switch rise, ns."""
    pk = S.get("peaks", {})
    if "t_Qsw1" in pk and "t_Qsw2" in pk:
        return (pk["t_Qsw2"] - pk["t_Qsw1"]) * 1e3
    return np.nan


# ---- kept from py-3: used by logs/shot_timing.py (reconstruct_local; logs/export_pwl.py and LTSpice/export_pwl.py require it) ----
# Output probes on rigol3 (C225 D-dot, C315 B-dot). Baseline local to the
# pulse. The two windows are in seconds BEFORE the pulse onset found on that
# probe: (start, end) = (t_on - OUT_PRE[0], t_on - OUT_PRE[1]).
OUT_PRE = (2.0e-6, 0.15e-6)    # raw-signal baseline window
OUT_ZERO = (60e-9, 20e-9)      # the integral is zeroed here
OUT_ONSET_FRAC = 0.3           # onset: first sample at this fraction of the peak
OUT_PRE_MIN_SAMPLES = 100      # fewer samples in the baseline window: skip probe


def output_onset(t, raw):
    """Pulse onset on one output probe. Returns (t_on, index) or (None, None).

    dev = |raw - median(raw)|, kept only where detect_activity flags
    activity, and the onset is the first sample at OUT_ONSET_FRAC of its max.
    """
    _, _, act = detect_activity(t, raw)
    dev = np.abs(raw - np.median(raw))
    dev[~act] = 0.0
    top = dev.max()
    if not act.any() or top <= 0:
        return None, None
    i = int(np.flatnonzero(dev >= OUT_ONSET_FRAC * top)[0])
    return float(t[i]), i


def reconstruct_local(t, raw, CF):
    """Output probe with a baseline local to the pulse.

    Returns (trace in volts, t_on), or (None, reason) when the probe cannot
    be built. The baseline is the mean of raw over
    t_on - OUT_PRE[0] <= t < t_on - OUT_PRE[1]. raw minus that baseline is
    integrated over the whole record (trapezoid), and the integral is zeroed
    by its mean over t_on - OUT_ZERO[0] < t < t_on - OUT_ZERO[1].
    """
    t_on, _ = output_onset(t, raw)
    if t_on is None:
        return None, "no activity found"
    bm = (t >= t_on - OUT_PRE[0]) & (t < t_on - OUT_PRE[1])
    if bm.sum() < OUT_PRE_MIN_SAMPLES:
        return None, (f"{int(bm.sum())} samples in the baseline window "
                      f"{(t_on - OUT_PRE[0]) * 1e6:.2f} to {(t_on - OUT_PRE[1]) * 1e6:.2f} us "
                      f"(record starts at {t[0] * 1e6:.2f} us)")
    zm = inwin(t, (t_on - OUT_ZERO[0], t_on - OUT_ZERO[1]))
    if not zm.any():
        return None, "no samples in the zero window"
    integ = cumtrapz(t, raw - raw[bm].mean())
    integ = integ - integ[zm].mean()
    return CF * integ, t_on


# ---- kept from py-3: used by tests/test_analysis.py and baseline_export_v2/make_export_v2.py ----
def _xcross(t, ys, a, b, thr):
    """xcross() in ltgs_gui3_5.m."""
    if ys[b] == ys[a]:
        return float(t[b])
    return float(t[a] + (thr - ys[a]) * (t[b] - t[a]) / (ys[b] - ys[a]))


def out_edges(t, y, frac, win):
    """Port of outEdges() in ltgs_gui3_5.m, same math, 0-based indexing.

    Edges of the first two output pulses at frac (0..1) of each pulse's own
    peak, either polarity. t in us. A 5 ns moving mean smooths the trace,
    samples outside the open window win are set to zero, pulses are runs
    above 50% of the largest peak lasting at least 30 ns, crossings are
    linearly interpolated. Returns lead[2], trail[2], A[2] (signed peaks),
    NaN where not found.
    """
    lead, trail, A = [np.nan, np.nan], [np.nan, np.nan], [np.nan, np.nan]
    t = np.asarray(t, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    if t.size < 10:
        return lead, trail, A
    dt = float(np.median(np.diff(t[:1000])))
    ys = movmean(y, max(1, 2 * mround(0.005 / dt / 2) + 1))
    w = (t > win[0]) & (t < win[1])
    if not w.any():
        return lead, trail, A
    yw = ys[w]
    s = np.sign(yw[int(np.argmax(np.abs(yw)))])
    if s == 0:
        return lead, trail, A
    ys = s * ys
    ys[~w] = 0.0
    g = ys.max()
    b = (ys > 0.5 * g).astype(np.int8)
    d = np.diff(np.concatenate(([0], b, [0])))
    rs, re = np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1
    keep = (re - rs + 1) * dt >= 0.03
    rs, re = rs[keep], re[keep]
    N = ys.size
    lo = 0
    for p in range(min(2, rs.size)):
        seg = np.arange(rs[p], re[p] + 1)
        Ap = ys[seg].max()
        thr = frac * Ap
        A[p] = float(s * Ap)
        above = seg[ys[seg] >= 0.5 * Ap]
        i50, i50t = int(above[0]), int(above[-1])
        # leading edge
        if frac <= 0.5:
            k = np.flatnonzero(ys[lo:i50 + 1] < thr)
            if k.size:
                a = lo + int(k[-1])
                lead[p] = _xcross(t, ys, a, a + 1, thr)
        else:
            k = np.flatnonzero(ys[i50:re[p] + 1] >= thr)
            if k.size and i50 + int(k[0]) > 0:
                bb = i50 + int(k[0])
                lead[p] = _xcross(t, ys, bb - 1, bb, thr)
        # trailing edge
        hi = int(rs[p + 1]) if p + 1 < rs.size else N - 1
        if frac >= 0.5:
            k = np.flatnonzero(ys[rs[p]:i50t + 1] >= thr)
            if k.size and int(rs[p]) + int(k[-1]) < N - 1:
                a = int(rs[p]) + int(k[-1])
                trail[p] = _xcross(t, ys, a, a + 1, thr)
        else:
            k = np.flatnonzero(ys[i50t:hi + 1] < thr)
            if k.size and i50t + int(k[0]) > 0:
                bb = i50t + int(k[0])
                trail[p] = _xcross(t, ys, bb - 1, bb, thr)
        lo = int(re[p])
    return lead, trail, A


def edge_summary(t, y, frac, win):
    """out_edges plus widths and spacing, for S["edges"][probe]."""
    lead, trail, A = out_edges(t, y, frac, win)
    return {
        "level": float(frac),
        "lead_us": np.array(lead), "trail_us": np.array(trail),
        "peak_kV": np.array(A),
        "width_ns": (np.array(trail) - np.array(lead)) * 1e3,
        "gap_ns": (lead[1] - trail[0]) * 1e3,
        "start_to_start_ns": (lead[1] - lead[0]) * 1e3,
    }
