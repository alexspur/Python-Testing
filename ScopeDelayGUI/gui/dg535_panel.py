# gui/dg535_panel.py
"""
DG535 Delay Control Panel

The GUI's DG535 is the laser DG535: externally triggered by BNC575 channel B,
driving both CFR lasers' lamp and Q-switch inputs. The only thing the GUI
writes to it is channel delays, and only the ones the operator edited.

What is deliberately absent: trigger mode, outputs and instrument memory. The
GUI never sends TM or SS, never writes output configuration, and never stores
or recalls a setup, because every one of those can change the delays or take
the unit out of external trigger mid-experiment. The trigger mode is set on
the front panel and only displayed here.

Layout: one row per channel, no tabs, so this panel fits beside the BNC575
without the main window scrolling.

BACKWARD COMPATIBLE: keeps get_delayA(), get_widthA() etc. for existing code.
"""

from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton,
    QLabel, QDoubleSpinBox, QComboBox,
)
from PyQt6.QtCore import Qt
from utils.status_lamp import StatusLamp


# Unit -> multiplier (to seconds)
_TIME_UNITS = [("s", 1.0), ("ms", 1e-3), ("μs", 1e-6), ("ns", 1e-9), ("ps", 1e-12)]


class DG535Panel(QGroupBox):
    """Delay control panel for the laser DG535."""

    def __init__(self):
        super().__init__("DG535 Digital Delay Generator")

        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(6, 6, 6, 6)
        self.setLayout(layout)

        # Connection row: lamp and buttons on one line to save height.
        conn_row = QHBoxLayout()
        self.lamp = StatusLamp(size=14)
        conn_row.addWidget(self.lamp)
        self.btn_connect = QPushButton("Connect DG535")
        self.btn_disconnect = QPushButton("Disconnect")
        conn_row.addWidget(self.btn_connect)
        conn_row.addWidget(self.btn_disconnect)
        conn_row.addStretch()
        layout.addLayout(conn_row)

        # Read-only: the laser DG535 is externally triggered by BNC575
        # channel B and the GUI never changes its trigger mode.
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("<b>Trigger mode (read-only):</b>"))
        self.trigger_mode_label = QLabel("---")
        self.trigger_mode_label.setStyleSheet("font-weight:bold; color:#1565C0;")
        mode_row.addWidget(self.trigger_mode_label)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        # Edit tracking. A channel counts as changed only when the operator
        # edits it after a readback - never by comparing the spin box to the
        # readback, because the instrument reports more digits than the box
        # displays and that would make every channel look dirty.
        self._dirty_channels = set()
        self._loading_readback = False

        self._build_delays(layout)

        # Actions
        action_row = QHBoxLayout()
        self.btn_apply_delays = QPushButton("Apply Changed Delays")
        # Enabled only once a readback has filled the fields, so "changed"
        # is always measured against the instrument, not the panel defaults.
        self.btn_apply_delays.setEnabled(False)
        self.btn_apply_delays.setToolTip(
            "Read the DG535 back first. Only channels whose delay or "
            "reference differs from that readback are written.")
        self.btn_read_all = QPushButton("Read All Settings")
        action_row.addWidget(self.btn_apply_delays)
        action_row.addWidget(self.btn_read_all)
        action_row.addStretch()
        layout.addLayout(action_row)

        self.status_label = QLabel("Status: Not connected")
        self.status_label.setStyleSheet("font-style: italic; color: #666;")
        layout.addWidget(self.status_label)

    # =========================================================================
    # Builders
    # =========================================================================
    def _make_time_field(self, default_value=0.0, default_unit="μs"):
        """Return (spinbox, unit_combo) for a time value. Combo data = seconds multiplier."""
        spin = QDoubleSpinBox()
        spin.setDecimals(6)
        spin.setRange(0, 999999999)
        spin.setValue(default_value)
        spin.setMaximumWidth(110)

        combo = QComboBox()
        for name, mult in _TIME_UNITS:
            combo.addItem(name, mult)
        idx = combo.findText(default_unit)
        combo.setCurrentIndex(idx if idx >= 0 else 2)
        combo.setMaximumWidth(60)
        return spin, combo

    @staticmethod
    def _value_in_seconds(spin: QDoubleSpinBox, combo: QComboBox) -> float:
        mult = combo.currentData()
        return spin.value() * (mult if mult is not None else 1e-6)

    def _build_delays(self, layout):
        """One compact row per channel: reference, delay, width."""
        grid = QGridLayout()
        grid.setSpacing(4)

        for col, head in enumerate(["Ch", "Reference", "Delay", "", "Width", ""]):
            lbl = QLabel(f"<b>{head}</b>" if head else "")
            grid.addWidget(lbl, 0, col)

        ref_options = ["T0", "A", "B", "C", "D"]
        self.delay_widgets = {}

        for row, (ch_name, ch_id) in enumerate(
                [("A", 2), ("B", 3), ("C", 5), ("D", 6)], start=1):
            grid.addWidget(QLabel(f"<b>{ch_name}</b>"), row, 0)

            ref_combo = QComboBox()
            ref_combo.addItems(ref_options)
            ref_combo.setCurrentText("T0")
            ref_combo.setMaximumWidth(70)
            grid.addWidget(ref_combo, row, 1)

            delay_spin, delay_combo = self._make_time_field(0.0, "μs")
            grid.addWidget(delay_spin, row, 2)
            grid.addWidget(delay_combo, row, 3)

            width_spin, width_combo = self._make_time_field(1.0, "μs")
            grid.addWidget(width_spin, row, 4)
            grid.addWidget(width_combo, row, 5)

            self.delay_widgets[ch_name] = {
                "id": ch_id,
                "reference": ref_combo,
                "delay": delay_spin,
                "delay_combo": delay_combo,
                "width": width_spin,
                "width_combo": width_combo,
            }

            # Any operator edit marks this channel dirty. Programmatic fills
            # from a readback do not (see set_delay_with_reference).
            delay_spin.valueChanged.connect(
                lambda _v, n=ch_name: self._mark_channel_dirty(n))
            delay_combo.currentIndexChanged.connect(
                lambda _i, n=ch_name: self._mark_channel_dirty(n))
            ref_combo.currentIndexChanged.connect(
                lambda _i, n=ch_name: self._mark_channel_dirty(n))

            # The GUI writes delays and references only. Width is not sent to
            # the DG535, so it must not look editable.
            width_spin.setEnabled(False)
            width_combo.setEnabled(False)
            width_spin.setToolTip("Not written by the GUI.")

            # Delays are always microseconds. The unit is locked because the
            # panel multiplies the spin box by whatever unit is selected when
            # the value is read: switching it would silently change the delay
            # that Apply writes, without the number on screen changing.
            _us_index = delay_combo.findData(1e-6)
            if _us_index >= 0:
                delay_combo.setCurrentIndex(_us_index)
            delay_combo.setEnabled(False)
            delay_combo.setToolTip("Delays are always entered in microseconds.")

        grid.setColumnStretch(6, 1)
        layout.addLayout(grid)

    # =========================================================================
    # BACKWARD COMPATIBLE API - matches existing main_window.py usage
    # =========================================================================
    def get_delayA(self) -> float:
        w = self.delay_widgets["A"]
        return self._value_in_seconds(w["delay"], w["delay_combo"])

    def get_widthA(self) -> float:
        w = self.delay_widgets["A"]
        return self._value_in_seconds(w["width"], w["width_combo"])

    def get_delayB(self) -> float:
        w = self.delay_widgets["B"]
        return self._value_in_seconds(w["delay"], w["delay_combo"])

    def get_widthB(self) -> float:
        w = self.delay_widgets["B"]
        return self._value_in_seconds(w["width"], w["width_combo"])

    def get_delayC(self) -> float:
        w = self.delay_widgets["C"]
        return self._value_in_seconds(w["delay"], w["delay_combo"])

    def get_widthC(self) -> float:
        w = self.delay_widgets["C"]
        return self._value_in_seconds(w["width"], w["width_combo"])

    def get_delayD(self) -> float:
        w = self.delay_widgets["D"]
        return self._value_in_seconds(w["delay"], w["delay_combo"])

    def get_widthD(self) -> float:
        w = self.delay_widgets["D"]
        return self._value_in_seconds(w["width"], w["width_combo"])

    def get_delay_with_reference(self, channel: str) -> tuple:
        """Return (reference_channel_name, delay_seconds) for a channel."""
        w = self.delay_widgets[channel]
        ref = w["reference"].currentText()
        delay = self._value_in_seconds(w["delay"], w["delay_combo"])
        return ref, delay

    def set_status(self, text: str):
        self.status_label.setText(f"Status: {text}")

    # =========================================================================
    # Readback helpers (filled from the instrument, not typed by the operator)
    # =========================================================================
    def set_trigger_mode_text(self, text: str):
        """Show the trigger mode read back from the instrument."""
        self.trigger_mode_label.setText(str(text))

    def set_delay_with_reference(self, channel: str, reference: str, delay_seconds: float):
        """Fill one channel's reference and delay from a readback.

        Shown in microseconds (6 decimals = 1 ps, finer than the DG535's 5 ps
        step). Filling never marks the channel dirty: only operator edits do.
        """
        w = self.delay_widgets.get(channel)
        if not w:
            return
        self._loading_readback = True
        try:
            idx = w["reference"].findText(str(reference))
            if idx >= 0:
                w["reference"].setCurrentIndex(idx)
            unit_idx = w["delay_combo"].findData(1e-6)      # microseconds
            if unit_idx >= 0:
                w["delay_combo"].setCurrentIndex(unit_idx)
            w["delay"].setValue(float(delay_seconds) * 1e6)
        finally:
            self._loading_readback = False
        self._dirty_channels.discard(channel)

    def _mark_channel_dirty(self, channel: str):
        """An operator edit on this channel. Ignored while loading a readback."""
        if not self._loading_readback:
            self._dirty_channels.add(channel)

    def dirty_channels(self):
        """Channels edited since the last readback, in A-D order."""
        return [c for c in ("A", "B", "C", "D") if c in self._dirty_channels]

    def clear_dirty(self):
        self._dirty_channels.clear()

    def set_apply_enabled(self, enabled: bool):
        """Apply stays disabled until a readback has filled the fields."""
        self.btn_apply_delays.setEnabled(bool(enabled))
