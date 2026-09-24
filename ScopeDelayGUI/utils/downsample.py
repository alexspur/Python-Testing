# utils/downsample.py
"""
Peak-preserving min/max downsampling for scope traces.

A 1,000,000-point channel drawn at full resolution costs about half a second
of path building per curve on the GUI thread, and three scopes of four
channels queue up behind each other on it. Drawing two points per screen
column - each bin's minimum and its maximum - looks identical at that width
and keeps every spike: a single-sample excursion is one bin's max, so it is
still drawn at full height.

Never an average (a spike a few samples wide would shrink toward the
baseline) and never plain decimation (it would be dropped outright).

Pure numpy, no Qt: meant to run on the capture worker thread, and to be
re-run on the visible slice when the view is zoomed.
"""

import numpy as np

# Two points per bin, so bins are roughly pixel columns. 1200 covers a wide
# plot; a zoomed view with fewer than 2*bins samples in it shows real samples.
DISPLAY_BINS = 1200


def minmax_downsample(t, v, bins=DISPLAY_BINS):
    """Return (t_ds, v_ds): at most 2*bins (+2) points, min and max per bin.

    Inputs of 2*bins samples or fewer come back unchanged - they are already
    cheap, and a zoomed-in view should show real samples, not an envelope.

    Each bin contributes its min then its max, both stamped with the bin's
    first time, so the drawn envelope is exact and the peak of any spike
    survives. Samples left over after the last whole bin become one extra
    min/max pair so the trace reaches the true end of the record.
    """
    t = np.asarray(t)
    v = np.asarray(v)
    n = len(v)
    if n == 0 or n <= 2 * bins or len(t) != n:
        return t, v

    per = n // bins                     # samples per bin
    m = per * bins                      # samples covered by whole bins
    vv = v[:m].reshape(bins, per)
    lo = vv.min(axis=1)
    hi = vv.max(axis=1)
    tt = t[:m:per]                      # first time of each bin

    out_v = np.empty(2 * bins, dtype=float)
    out_v[0::2] = lo
    out_v[1::2] = hi
    out_t = np.repeat(np.asarray(tt, dtype=float), 2)

    if m < n:
        tail = v[m:]
        out_t = np.append(out_t, [t[m], t[m]])
        out_v = np.append(out_v, [tail.min(), tail.max()])
    return out_t, out_v


def downsample_four(data, bins=DISPLAY_BINS):
    """minmax_downsample over a 4-channel ((t, v), (t, v), ...) tuple."""
    return tuple(minmax_downsample(t, v, bins) for t, v in data)


def visible_downsample(t, v, x0, x1, bins=DISPLAY_BINS):
    """The part of (t, v) inside [x0, x1], downsampled for display.

    For zooming: the plot keeps the full arrays and re-downsamples only the
    visible range, so zooming in reveals real samples once fewer than 2*bins
    of them are in view. t must be ascending (capture time axes are). One
    sample of margin is kept on each side so the trace reaches the edges.
    """
    t = np.asarray(t)
    v = np.asarray(v)
    if len(t) == 0 or len(t) != len(v):
        return t, v
    if x1 < x0:
        x0, x1 = x1, x0
    lo = int(np.searchsorted(t, x0, side="left"))
    hi = int(np.searchsorted(t, x1, side="right"))
    lo = max(lo - 1, 0)
    hi = min(hi + 1, len(t))
    return minmax_downsample(t[lo:hi], v[lo:hi], bins)
