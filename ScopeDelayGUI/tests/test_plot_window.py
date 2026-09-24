"""The scope plot window on its own, offscreen. No hardware, no main window."""

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PyQt6.QtWidgets import QApplication

from utils.downsample import DISPLAY_BINS, downsample_four

app = QApplication.instance() or QApplication([])


def capture(n=1_000_000, spike_at=123_456, spike=40.0):
    t = np.arange(n) * 1e-9
    chans = []
    for k in range(4):
        v = np.random.default_rng(k).standard_normal(n)
        if k == 0 and spike_at is not None:
            v[spike_at] = spike
        chans.append((t, v))
    return tuple(chans)


class TestDownsampledPlots(unittest.TestCase):

    def setUp(self):
        from gui.scope_plot_window import ScopePlotWindow
        self.win = ScopePlotWindow(parent=None)
        self.addCleanup(self.win.close)
        self.full = capture()
        self.display = downsample_four(self.full)
        self.win.set_full_data(1, self.full)
        self.win.update_r1_four(self.display)
        app.processEvents()

    def test_the_curve_holds_the_display_copy_not_the_million_points(self):
        for curve in self.win.r1_curves:
            self.assertLessEqual(len(curve.xData), 2 * DISPLAY_BINS + 2)
        self.assertEqual(len(self.full[0][1]), 1_000_000, "the full arrays are untouched")

    def test_a_single_sample_spike_is_in_the_plotted_data(self):
        self.assertGreaterEqual(self.win.r1_ch1.yData.max(), 40.0)

    def test_zooming_in_shows_real_samples_and_keeps_the_spike(self):
        vb = self.win.plot1.getViewBox()
        vb.setXRange(123_400e-9, 123_500e-9, padding=0)   # a user zoom: auto-range off
        self.win._refresh_visible(1)

        pts = len(self.win.r1_ch1.xData)
        self.assertLess(pts, 2 * DISPLAY_BINS, "few samples in view: real data, not an envelope")
        self.assertGreater(pts, 50)
        self.assertGreaterEqual(self.win.r1_ch1.yData.max(), 40.0)

    def test_the_zoom_refresh_is_driven_by_the_range_change_signal(self):
        from PyQt6.QtTest import QTest
        vb = self.win.plot1.getViewBox()
        vb.setXRange(123_400e-9, 123_500e-9, padding=0)
        QTest.qWait(150)                                  # past the 50 ms debounce
        self.assertLess(len(self.win.r1_ch1.xData), 2 * DISPLAY_BINS)

    def test_view_all_restores_the_full_display_copy(self):
        vb = self.win.plot1.getViewBox()
        vb.setXRange(123_400e-9, 123_500e-9, padding=0)
        self.win._refresh_visible(1)
        self.assertLess(len(self.win.r1_ch1.xData), 2 * DISPLAY_BINS)

        vb.enableAutoRange(x=True)                        # "View All"
        self.win._refresh_visible(1)

        self.assertEqual(len(self.win.r1_ch1.xData), len(self.display[0][1]))

    def test_hidden_channels_stay_hidden_through_a_zoom(self):
        self.win.ch_checkboxes[2].setChecked(False)       # CH3 off
        vb = self.win.plot1.getViewBox()
        vb.setXRange(1e-6, 2e-6, padding=0)
        self.win._refresh_visible(1)
        self.assertFalse(self.win.r1_ch3.isVisible())
        self.assertTrue(self.win.r1_ch1.isVisible())

    def test_clear_forgets_the_full_arrays(self):
        self.win.clear_plots()
        self.assertIsNone(self.win._full[1])
        self.win._refresh_visible(1)                      # must not raise with nothing held
        self.assertEqual(len(self.win.r1_ch1.xData or []), 0)


if __name__ == "__main__":
    unittest.main()
