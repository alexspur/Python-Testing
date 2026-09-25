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


def plain(rich):
    import re
    return re.sub(r"<[^>]+>", "", rich).replace("&nbsp;", " ")


# Rigol #1 as read at arm time on 2026-09-24 (probe 20000x on CH1/CH2), with
# CH2 on 50 ohm, CH3's scale and offset unreadable, and CH4 switched off.
R1_SETTINGS = {
    "scope": {"timebase_scale_s_div": "5.000000E-7", "timebase_offset_s": "1.831083E-4",
              "sample_rate_sa_s": "2.500000E+9", "memory_depth": "1.0000E+06",
              "trigger_source": "CHAN1", "trigger_slope": "POS", "trigger_level_v": "1.5E+5"},
    "channels": {
        1: {"scale_v_div": "92E3", "offset_v": "28035E1", "probe_ratio": "20000",
            "coupling": "DC", "impedance": "OMEG", "label": "High", "display": "1"},
        2: {"scale_v_div": "104E3", "offset_v": "16306668E-2", "probe_ratio": "20000",
            "coupling": "DC", "impedance": "FIFT", "label": "Low", "display": "1"},
        3: {"scale_v_div": "UNKNOWN", "offset_v": "UNKNOWN", "probe_ratio": "100",
            "coupling": "DC", "impedance": "OMEG", "label": "Mid", "display": "1"},
        4: {"scale_v_div": "1", "offset_v": "0", "probe_ratio": "1",
            "coupling": "DC", "impedance": "FIFT", "label": "High2", "display": "0"},
    },
}


class FakeMain:
    """What the plot window reads from its parent: state, a scope, a log."""

    def __init__(self):
        from utils.system_state import SystemState
        self.system_state = SystemState()
        self.lines = []

    def log(self, message):
        self.lines.append(message)


class TestScopeStyleDisplay(unittest.TestCase):

    def setUp(self):
        from gui.scope_plot_window import ScopePlotWindow
        from utils.system_state import SOURCE_READBACK
        self.parent = FakeMain()
        self.parent.system_state.update("rigol1", {"settings": R1_SETTINGS}, source=SOURCE_READBACK)
        self.win = ScopePlotWindow(parent=self.parent)
        self.addCleanup(self.win.close)
        self.screen = self.win.screens[1]

    def _feed(self, volts_by_channel, n=5000):
        """A capture spanning the screen window: constant volts per channel,
        or an array."""
        t = np.linspace(1.806e-4, 1.856e-4, n)
        chans = []
        for ch in (1, 2, 3, 4):
            v = volts_by_channel.get(ch, 0.0)
            v = np.asarray(v, dtype=float) if np.ndim(v) else np.full(n, float(v))
            chans.append((t, v))
        data = tuple(chans)
        self.win.set_full_data(1, data)
        self.win.update_r1_four(data)
        app.processEvents()
        return data

    def test_scope_view_is_the_default(self):
        self.assertEqual(self.win.view_mode, "scope")
        self.assertTrue(self.screen.isVisibleTo(self.win))
        self.assertFalse(self.win.plot1.isVisibleTo(self.win))

    def test_a_channel_lands_at_its_division(self):
        """position = (V + offset) / scale: CH1's 0 V sits at +280350/92000
        div, CH2's 104 kV at (104e3 + 163066.68)/104e3 div."""
        self._feed({1: 0.0, 2: 104e3})
        self.assertTrue(np.allclose(self.screen.curves[1].yData, 280350 / 92000))
        self.assertTrue(np.allclose(self.screen.curves[2].yData, (104e3 + 163066.68) / 104e3))
        # The ground marker sits where the channel's zero level is.
        self.assertAlmostEqual(self.screen.zero_markers[1].value(), 280350 / 92000, places=6)
        self.assertAlmostEqual(self.screen.zero_markers[2].value(), 163066.68 / 104e3, places=6)

    def test_a_hidden_channel_is_not_drawn(self):
        self._feed({4: 1.0})
        self.assertFalse(self.screen.curves[4].isVisible())
        x = self.screen.curves[4].xData
        self.assertTrue(x is None or len(x) == 0, "a hidden channel holds no points")
        self.assertFalse(self.screen.zero_markers[4].isVisible())
        self.assertIsNone(self.screen.channel_lines(4), "no box in the bar either")
        self.assertNotIn(4, self.screen.boxes)
        self.assertNotIn("CH4", self.screen.info_text())
        self.assertNotIn(4, self.screen.readout_at(1.83e-4))

    def test_unknown_settings_autoscale_to_fill_eight_divisions(self):
        v3 = np.sin(np.linspace(0, 40, 5000)) * 3.0          # -3 .. +3 V
        self._feed({3: v3})
        y = self.screen.curves[3].yData
        self.assertAlmostEqual(float(y.min()), -4.0, places=6)
        self.assertAlmostEqual(float(y.max()), 4.0, places=6)
        self.assertTrue(self.screen.placements[3].auto)
        self.assertEqual(self.screen.channel_lines(3)[:2], ["CH3", "auto"],
                         "line 2 of an autoscaled channel's box says auto")
        self.assertIn("auto", self.screen.boxes[3].text())

    def test_info_bar_matches_the_settings(self):
        """One box per displayed channel - name, V/div, offset - then the
        timebase and trigger boxes. Nothing else, as on the scope's bar."""
        from gui.scope_screen import eng
        self._feed({})
        s = self.screen
        self.assertEqual(sorted(s.boxes), [1, 2, 3], "CH4 is off: no box")
        self.assertEqual(s.channel_lines(1), ["CH1", "92 kV/div", "Ofs 280 kV"])
        self.assertEqual(s.channel_lines(2), ["CH2", "104 kV/div", "Ofs 163 kV"])
        self.assertEqual(s.boxes[1].text(), "CH1\n92 kV/div\nOfs 280 kV")
        self.assertEqual(s.timebase_lines(), ["H 500 ns/div", f"Delay {eng(1.831083e-4, 's', 4)}"])
        self.assertEqual(s.trigger_lines(), ["T CH1 rising", "150 kV"])
        self.assertEqual(s.timebase_box.text(), "\n".join(s.timebase_lines()))
        self.assertEqual(s.trigger_box.text(), "\n".join(s.trigger_lines()))
        txt = s.info_text()
        for absent in ("probe", "DC", "Ω", "High", "Low", "Sa/s", "pts", "CH4"):
            self.assertNotIn(absent, txt, txt)
        # The boxes carry their channel's colour.
        from gui.scope_screen import CH_COLORS
        self.assertIn(CH_COLORS[1], s.boxes[1].styleSheet())
        self.assertIn(CH_COLORS[1], s.trigger_box.styleSheet(), "trigger box in CH1's colour")

    def test_trigger_box_names_ext_and_falling(self):
        from utils.system_state import SOURCE_READBACK
        settings = {"scope": dict(R1_SETTINGS["scope"], trigger_source="EXT",
                                  trigger_slope="NEG", trigger_level_v="0.5"),
                    "channels": R1_SETTINGS["channels"]}
        self.parent.system_state.update("rigol1", {"settings": settings}, source=SOURCE_READBACK)
        self._feed({})
        self.assertEqual(self.screen.trigger_lines(), ["T EXT falling", "500 mV"])
        self.assertIn("#606060", self.screen.trigger_box.styleSheet(), "no channel: neutral colour")

    def test_time_axis_is_ten_divisions_centred_on_the_offset(self):
        self._feed({})
        x0, x1 = self.screen.vb.viewRange()[0]
        self.assertAlmostEqual(x0, 1.831083e-4 - 5 * 5e-7, places=12)
        self.assertAlmostEqual(x1, 1.831083e-4 + 5 * 5e-7, places=12)
        y0, y1 = self.screen.vb.viewRange()[1]
        self.assertEqual((round(y0, 6), round(y1, 6)), (-4.0, 4.0))

    def test_trigger_level_marker_is_in_the_source_channels_colour(self):
        from gui.scope_screen import CH_COLORS
        self._feed({})
        self.assertTrue(self.screen.trig_marker.isVisible())
        self.assertEqual(self.screen.trig_marker.label.fill.color().name().upper(),
                         CH_COLORS[1].upper())
        # (150 kV + 280.35 kV) / 92 kV = 4.68 div: above the screen, so pinned.
        self.assertEqual(self.screen.trig_marker.value(), 4.0)

    def test_sign_convention_is_checked_against_the_preamble(self):
        """YORigin = VerticalOffset / YINCrement (guide 2-228), so the
        preamble's centre -yorigin*yincrement must equal -offset."""
        yinc = 92e3 / 25
        preamble = {"yorigin": 280350 / yinc, "yincrement": yinc}

        class FakeRigol:
            _last_channel_stats = {1: {"preamble": dict(preamble)}}
        self.parent.rigol1 = FakeRigol()

        self._feed({})
        self.assertTrue(any("ch1: sign convention confirmed" in m for m in self.parent.lines),
                        self.parent.lines)

        self.parent.lines.clear()
        FakeRigol._last_channel_stats[1]["preamble"]["yorigin"] = -280350 / yinc
        self._feed({})
        self.assertTrue(any("WARNING" in m and "ch1" in m for m in self.parent.lines),
                        self.parent.lines)

    def test_engineering_view_is_still_reachable(self):
        self.win.view_toggle.setCurrentIndex(1)
        self.assertEqual(self.win.view_mode, "engineering")
        self.assertTrue(self.win.plot1.isVisibleTo(self.win))
        self.assertFalse(self.screen.isVisibleTo(self.win))
        self.win.view_toggle.setCurrentIndex(0)
        self.assertEqual(self.win.view_mode, "scope")

    def test_hover_readout_reports_real_volts_not_divisions(self):
        self._feed({1: 0.0, 2: 104e3})
        r = self.screen.readout_at(1.83e-4)
        self.assertAlmostEqual(r[1], 0.0)
        self.assertAlmostEqual(r[2], 104e3)
        self.assertNotIn(4, r)

    def test_zoomed_scope_view_re_downsamples_in_divisions(self):
        from utils.downsample import DISPLAY_BINS, downsample_four
        n = 1_000_000
        t = np.linspace(1.806e-4, 1.856e-4, n)
        v1 = np.zeros(n)
        v1[500_000] = -92e3                                  # one sample, one division down
        data = tuple((t, v1 if ch == 1 else np.zeros(n)) for ch in (1, 2, 3, 4))
        self.win.set_full_data(1, data)
        self.win.update_r1_four(downsample_four(data))
        app.processEvents()
        base = 280350 / 92000
        self.assertAlmostEqual(float(self.screen.curves[1].yData.min()), base - 1.0, places=6,
                               msg="the spike survives the display downsample, in divisions")

        self.screen.vb.setXRange(t[499_950], t[500_050], padding=0)   # a user zoom
        self.win._refresh_visible(1)
        self.assertLess(len(self.screen.curves[1].xData), 2 * DISPLAY_BINS)
        self.assertAlmostEqual(float(self.screen.curves[1].yData.min()), base - 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
