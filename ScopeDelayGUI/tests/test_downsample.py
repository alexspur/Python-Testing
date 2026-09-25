"""Peak-preserving display downsampling. Pure numpy, no Qt, no hardware."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.downsample import (DISPLAY_BINS, downsample_four, minmax_downsample,
                              visible_downsample)


def trace(n=1_000_000, seed=0):
    t = np.arange(n) * 1e-9
    v = np.random.default_rng(seed).standard_normal(n)
    return t, v


class TestMinMaxDownsample(unittest.TestCase):

    def test_a_million_points_become_two_per_bin(self):
        t, v = trace()
        td, vd = minmax_downsample(t, v)
        self.assertLessEqual(len(vd), 2 * DISPLAY_BINS + 2)
        self.assertEqual(len(td), len(vd))
        self.assertTrue(np.all(np.diff(td) >= 0), "time must stay monotonic")

    def test_a_single_sample_spike_survives(self):
        """A spike a few samples wide is exactly what an average would
        shrink and a decimation would drop. It is one bin's max here."""
        t, v = trace()
        v[123_456] = 40.0
        v[777_777] = -35.0
        _, vd = minmax_downsample(t, v)
        self.assertGreaterEqual(vd.max(), 40.0)
        self.assertLessEqual(vd.min(), -35.0)

    def test_every_bin_keeps_its_true_min_and_max(self):
        t, v = trace(n=DISPLAY_BINS * 10)
        _, vd = minmax_downsample(t, v)
        per = len(v) // DISPLAY_BINS
        for b in range(DISPLAY_BINS):
            chunk = v[b * per:(b + 1) * per]
            self.assertEqual(vd[2 * b], chunk.min())
            self.assertEqual(vd[2 * b + 1], chunk.max())

    def test_short_input_passes_through_unchanged(self):
        t, v = trace(n=2 * DISPLAY_BINS)
        td, vd = minmax_downsample(t, v)
        self.assertIs(vd, v)
        self.assertIs(td, t)

    def test_leftover_samples_reach_the_end_of_the_record(self):
        n = 1_000_003
        t = np.arange(n) * 1.0
        v = np.arange(n) * 1.0                # rising, so the last sample is the max
        td, vd = minmax_downsample(t, v)
        self.assertEqual(len(vd), 2 * DISPLAY_BINS + 2)
        self.assertEqual(vd[-1], n - 1)
        self.assertEqual(td[-1], t[(n // DISPLAY_BINS) * DISPLAY_BINS])

    def test_empty_and_mismatched_inputs_are_returned_as_is(self):
        e = np.array([])
        self.assertEqual(len(minmax_downsample(e, e)[1]), 0)
        t, v = trace(n=10_000)
        td, vd = minmax_downsample(t[:-1], v)
        self.assertEqual(len(vd), len(v))

    def test_four_channel_wrapper(self):
        t, v = trace()
        out = downsample_four(tuple((t, v) for _ in range(4)))
        self.assertEqual(len(out), 4)
        self.assertTrue(all(len(x[1]) <= 2 * DISPLAY_BINS + 2 for x in out))


class TestVisibleDownsample(unittest.TestCase):

    def test_zoomed_in_shows_real_samples(self):
        t, v = trace()
        v[123_456] = 40.0
        td, vd = visible_downsample(t, v, 123_400e-9, 123_500e-9)
        self.assertLess(len(vd), 2 * DISPLAY_BINS, "few enough in view: raw samples")
        self.assertGreaterEqual(vd.max(), 40.0, "the spike in view is real data")
        self.assertLessEqual(td[0], 123_400e-9, "one sample of margin on the left")
        self.assertGreaterEqual(td[-1], 123_500e-9, "one sample of margin on the right")

    def test_zoomed_out_is_downsampled_again(self):
        t, v = trace()
        td, vd = visible_downsample(t, v, 0.0, 1e-3)
        self.assertLessEqual(len(vd), 2 * DISPLAY_BINS + 2)

    def test_reversed_range_is_tolerated(self):
        t, v = trace(n=50_000)
        a = visible_downsample(t, v, 30e-6, 10e-6)[1]
        b = visible_downsample(t, v, 10e-6, 30e-6)[1]
        self.assertEqual(len(a), len(b))


if __name__ == "__main__":
    unittest.main()
