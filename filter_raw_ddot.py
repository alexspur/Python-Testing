"""Notch-filter the raw (uncalibrated) D-dot channels and plot them.

Reads raw_<name>_t / raw_<name>_v from processed_shots/shot_NNNN.mat (the
fields process_shots saves for kind-raw channels in scope_channels.py),
removes the ~90 MHz ringing with a zero-phase notch, integrates raw and
filtered, and plots both side by side with the spectra.

    python filter_raw_ddot.py                       shots 77 78, NE and SW
    python filter_raw_ddot.py 77 78 80              other shots
    python filter_raw_ddot.py --notch 90.6 --q 8    notch center (MHz) and Q
    python filter_raw_ddot.py --lowpass 300         also a 300 MHz low-pass
    python filter_raw_ddot.py --factor 2.5e13       integrals in kV
    python filter_raw_ddot.py --baseline -1 -0.1    zero the integral just before pulse 1
    python filter_raw_ddot.py --auto                notch at the measured peak

Filtering is scipy.signal.filtfilt (forward and backward), so no time
shift is added. The notch width is f0/Q: Q = 10 at 90.6 MHz removes about
9 MHz around the ring. Integrals subtract the mean over the baseline window
(us from pulse 1) and are zeroed there too, like ltgs_gui4.

The PNG goes to processed_shots/filter_raw_shots<N>_<M>.png.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from scipy.io import loadmat
from scipy.signal import butter, filtfilt, iirnotch

BASELINE_US = (-6.0, -4.0)        # pre-pulse window for offset and integral zero
RING_WINDOW_US = (1.0, 3.0)        # where the spectrum / auto peak is measured
XLIM_US = (-0.1, 1.0)


def load_raw(mat_path: Path, name: str):
    """(t_us, v) of one raw channel, or None if the file lacks it."""
    S = loadmat(str(mat_path), squeeze_me=True)
    tk, vk = f"raw_{name}_t", f"raw_{name}_v"
    if tk not in S or vk not in S:
        return None
    t, v = np.asarray(S[tk], float).ravel(), np.asarray(S[vk], float).ravel()
    return t, v


def sample_rate(t_us):
    return 1.0 / ((t_us[-1] - t_us[0]) / (t_us.size - 1) * 1e-6)


def ring_peak_hz(t_us, v, fs, window=RING_WINDOW_US, fmin=20e6, fmax=400e6):
    """Frequency of the strongest line in the ring-down window."""
    m = (t_us > window[0]) & (t_us < window[1])
    x = v[m] - v[m].mean()
    x = x * np.hanning(x.size)
    F = np.fft.rfft(x, n=1 << 18)
    f = np.fft.rfftfreq(F.size * 2 - 2, 1.0 / fs)
    band = (f > fmin) & (f < fmax)
    return float(f[band][np.argmax(np.abs(F[band]))])


def spectrum(t_us, v, fs, window=RING_WINDOW_US):
    m = (t_us > window[0]) & (t_us < window[1])
    x = v[m] - v[m].mean()
    x = x * np.hanning(x.size)
    F = np.fft.rfft(x)
    f = np.fft.rfftfreq(x.size, 1.0 / fs)
    return f, np.abs(F) / x.size


def apply_filters(v, fs, notch_hz, q, lowpass_hz=None):
    out = v
    if notch_hz:
        b, a = iirnotch(notch_hz, q, fs=fs)
        out = filtfilt(b, a, out)
    if lowpass_hz:
        b, a = butter(4, lowpass_hz, btype="low", fs=fs)
        out = filtfilt(b, a, out)
    return out


def integrate(t_us, v, factor=None, baseline=BASELINE_US):
    """Baseline-subtracted cumulative integral. (y, unit): kV with a factor,
    nV*s without."""
    bm = (t_us > baseline[0]) & (t_us < baseline[1])
    if bm.sum() < 10:
        bm = t_us < t_us[0] + 1.0
    v0 = v - v[bm].mean()
    I = np.concatenate(([0.0], np.cumsum(0.5 * (v0[1:] + v0[:-1]) * np.diff(t_us) * 1e-6)))
    I -= I[bm].mean()
    if factor:
        return I * factor / 1e3, "kV"
    return I * 1e9, "nV*s"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("shots", nargs="*", type=int, default=[77, 78])
    ap.add_argument("--channels", nargs="+", default=["NE_Ddot", "SW_Ddot"])
    ap.add_argument("--logs", default="logs", help="logs folder (default .\\logs)")
    ap.add_argument("--notch", type=float, default=90.6, help="notch center, MHz (0 = none)")
    ap.add_argument("--q", type=float, default=10.0, help="notch Q; width is f0/Q")
    ap.add_argument("--auto", action="store_true", help="center the notch on the measured ring")
    ap.add_argument("--lowpass", type=float, default=None, help="extra low-pass, MHz")
    ap.add_argument("--factor", type=float, default=None, help="V/(V*s) factor: integrals in kV")
    ap.add_argument("--baseline", nargs=2, type=float, default=BASELINE_US, metavar=("T0", "T1"),
                    help="baseline window, us from pulse 1 (default -6 -4; try -1 -0.1)")
    ap.add_argument("--xlim", nargs=2, type=float, default=XLIM_US, metavar=("T0", "T1"))
    ap.add_argument("--no-show", action="store_true")
    a = ap.parse_args(argv)

    import matplotlib
    if a.no_show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pdir = Path(a.logs) / "processed_shots"
    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    nrow, ncol = len(a.channels), 3
    fig, axs = plt.subplots(nrow, ncol, figsize=(17, 4.2 * nrow), squeeze=False)
    notch_used = {}
    for r, name in enumerate(a.channels):
        axV, axI, axF = axs[r]
        unit = ""
        for i, shot in enumerate(a.shots):
            p = pdir / f"shot_{shot:04d}.mat"
            if not p.exists():
                print(f"shot {shot}: {p.name} not found", file=sys.stderr)
                continue
            got = load_raw(p, name)
            if got is None:
                print(f"shot {shot}: no raw_{name} in {p.name} (processed before the raw fields, "
                      f"or not a raw channel in its wiring)", file=sys.stderr)
                continue
            t, v = got
            fs = sample_rate(t)
            f0 = ring_peak_hz(t, v, fs) if a.auto else a.notch * 1e6
            notch_used[(shot, name)] = f0
            vf = apply_filters(v, fs, f0, a.q, a.lowpass * 1e6 if a.lowpass else None)
            c = colors[i % len(colors)]
            axV.plot(t, v, color=c, lw=0.6, alpha=0.35)
            axV.plot(t, vf, color=c, lw=1.2, label=f"#{shot:04d} filtered")
            Ir, unit = integrate(t, v, a.factor, tuple(a.baseline))
            If, _ = integrate(t, vf, a.factor, tuple(a.baseline))
            axI.plot(t, Ir, color=c, lw=0.8, ls="--", alpha=0.6, label=f"#{shot:04d} raw")
            axI.plot(t, If, color=c, lw=1.4, label=f"#{shot:04d} filtered")
            fr, Ar = spectrum(t, v, fs)
            ff, Af = spectrum(t, vf, fs)
            axF.semilogy(fr / 1e6, Ar, color=c, lw=0.7, alpha=0.5, label=f"#{shot:04d} raw")
            axF.semilogy(ff / 1e6, Af, color=c, lw=1.2, label=f"#{shot:04d} filtered")
            print(f"shot {shot} {name}: notch {f0/1e6:.1f} MHz, Q {a.q:g}"
                  + (f", low-pass {a.lowpass:g} MHz" if a.lowpass else "")
                  + f"  raw pk-pk {np.ptp(v):.3f} V -> filtered {np.ptp(vf):.3f} V"
                  + f"  |integral| max raw {np.abs(Ir).max():.3g} -> filtered {np.abs(If).max():.3g} {unit}")
        axV.set_xlim(a.xlim); axV.set_ylabel("Volts as recorded"); axV.grid(alpha=0.3)
        axV.set_title(f"{name}: raw (faint) and filtered")
        axI.set_xlim(a.xlim); axI.set_ylabel(f"Integral ({unit})"); axI.grid(alpha=0.3)
        axI.set_title(f"{name}: integral, raw (dashed) and filtered")
        axF.set_xlim(0, 400); axF.set_ylabel("|V(f)|, ring-down window"); axF.grid(alpha=0.3, which="both")
        axF.set_title(f"{name}: spectrum {RING_WINDOW_US[0]:g}-{RING_WINDOW_US[1]:g} us")
        for ax in (axV, axI):
            ax.set_xlabel("Time from pulse 1 (us)")
        axF.set_xlabel("MHz")
        for ax in axs[r]:
            ax.legend(fontsize=8, loc="best")
    shots_txt = "_".join(str(s) for s in a.shots)
    f0s = sorted({round(f / 1e6, 1) for f in notch_used.values()})
    fig.suptitle(f"Raw D-dots, notch {', '.join(str(x) for x in f0s)} MHz (Q {a.q:g})"
                 + (f", low-pass {a.lowpass:g} MHz" if a.lowpass else "")
                 + (f", factor {a.factor:g}" if a.factor else ", no factor"),
                 fontsize=13, fontweight="bold")
    fig.tight_layout()
    out = pdir / f"filter_raw_shots{shots_txt}.png"
    fig.savefig(out, dpi=110)
    print("saved", out)
    if not a.no_show:
        plt.show()
    return 0


if __name__ == "__main__":
    sys.exit(main())
