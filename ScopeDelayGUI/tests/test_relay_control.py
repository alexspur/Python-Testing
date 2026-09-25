"""Three-state HV relay control from the GUI.

A fake relay controller records every write with the relay picture after
it, so the safety rule (the charging relay is never on while the discharging
relay is off) is asserted after every single write. Fake WJ supplies feed
HV packets through the real packet handler. No hardware, no serial.
"""

import threading
import time
import unittest
from unittest.mock import patch

from utils import relay_modes as rm
from utils.relay_modes import CHARGE, CHARGING, DISCHARGING, FLOAT, GROUND, UNKNOWN
from tests.test_shot_logging import GuiWindowTestCase, event_types, read_rows

CH = {CHARGING: 1, DISCHARGING: 0}          # the channels the GUI has always used
NAME = {1: CHARGING, 0: DISCHARGING}


class FakeRelayController:
    """Records writes as (channel, on, outcome) and the picture after each."""

    def __init__(self, connected=True, fail_at=None):
        self.connected = connected
        self.fail_at = fail_at              # index of the write that raises
        self.writes = []
        self.snapshots = []
        self.states = {}
        self.closed = False
        self.port = None

    @property
    def is_connected(self):
        return self.connected

    def connect(self, port):
        self.connected, self.port = True, port

    def close(self):
        self.closed, self.connected = True, False

    def set_relay(self, channel, on):
        if self.fail_at is not None and len(self.writes) == self.fail_at:
            self.writes.append((channel, bool(on), "FAILED"))
            raise RuntimeError("serial write failed")
        self.states[channel] = bool(on)
        self.writes.append((channel, bool(on), "ok"))
        self.snapshots.append(dict(self.states))


class FakeWJ:
    def __init__(self, connected=True):
        self.connected = connected
        self.hv_off_sent = 0
        self.set_calls = []
        self.v_set_kv = 0.0

    @property
    def is_connected(self):
        return self.connected

    def hv_off_pulse(self):
        self.hv_off_sent += 1
        return {"type": "A"}

    def send_set(self, **kwargs):
        self.set_calls.append(kwargs)
        return {"type": "A"}

    def set_program(self, kv, ma):
        self.program = (kv, ma)
        self.v_set_kv = kv
        return {"type": "A"}


class RelayTestCase(GuiWindowTestCase):
    def setUp(self):
        super().setUp()
        self.relay = FakeRelayController()
        self.win.numato_relay = self.relay
        self.wj = [FakeWJ(), FakeWJ()]
        self.win.wj_units = self.wj
        self.now = 1000.0
        self.win._relay_clock = lambda: self.now
        self.win.relay_panel.set_connected(True, "COM7")

    def _packet(self, i, hv_on):
        self.win.on_wj_packet(i, {"type": "R", "kv": 0.0, "ma": 0.0,
                                  "hv_on": hv_on, "fault": False})

    def _hv(self, on):
        for i in (0, 1):
            self._packet(i, on)

    def _set(self, mode):
        """Put the GUI and the fake in a known mode without going through a
        transition, then forget the writes that got there."""
        self.win._relay_states = dict(rm.TARGET[mode])
        self.win._relay_set_mode(mode)
        self.relay.states = {CH[r]: on for r, on in rm.TARGET[mode].items()}
        self.relay.writes.clear()
        self.relay.snapshots.clear()
        for wj in self.wj:
            wj.hv_off_sent = 0
            wj.set_calls.clear()

    def _run(self, max_ticks=200):
        n = 0
        while self.win._relay_transition is not None and n < max_ticks:
            self.win._relay_tick()
            n += 1

    def _writes(self):
        return [(NAME[ch], on) for ch, on, ok in self.relay.writes if ok == "ok"]

    def _rule_held_at_every_write(self):
        for snap in self.relay.snapshots:
            rm.check({NAME[ch]: on for ch, on in snap.items()})   # raises otherwise

    def _mode_events(self):
        return [r for r in read_rows(self.dl.get_log_file_path()) if r["event_type"] == "RELAY_MODE"]

    def _log(self):
        return self.dl.gui_log_file.read_text(encoding="utf-8")


class TestRelayTransitions(RelayTestCase):

    def test_connect_button_grounds_right_after_connecting(self):
        """The GUI starts in GROUND: connecting the board runs the normal
        GROUND transition (HV off, readback, charging off, then discharging
        off) and the GROUND button is lit when it completes."""
        self.relay.connected = False
        self.win.relay_panel.port_combo.clear()
        self.win.relay_panel.port_combo.addItem("COM7")
        self.win.on_relay_connect()
        self.assertTrue(self.relay.connected)
        self.assertIsNotNone(self.win._relay_transition, "grounding starts at once")
        self.assertEqual([w.hv_off_sent for w in self.wj], [1, 1])
        self.assertEqual(self.relay.writes, [], "no write before HV off is confirmed")
        self._hv(False)
        self._run()
        self.assertEqual(self._writes(), [(CHARGING, False), (DISCHARGING, False)])
        self._rule_held_at_every_write()
        self.assertEqual(self.win._relay_mode, GROUND)
        self.assertEqual(self.win.relay_panel.lit, {GROUND: True, FLOAT: False, CHARGE: False})
        ev = self._mode_events()[-1]
        self.assertEqual((ev["param1"], ev["param2"], ev["param3"]), (UNKNOWN, GROUND, "ok"))
        self.assertIn("startup ground", ev["notes"])
        self.assertIn("[RELAY] startup ground", self._log())

    def test_startup_ground_runs_after_auto_connect_with_the_supplies_up(self):
        """At launch the ground runs at the end of auto-connect, after the
        supplies, so the HV-off readback confirms at once: no 5 s wait, no
        ERROR row on a normal launch."""
        self.relay.connected = False
        self.win.conn["RELAY_COM"] = "COM7"
        self.win.auto_connect_flags = {k: False for k in self.win.auto_connect_flags}
        self.win.auto_connect_flags["relay"] = True
        self._hv(False)                                   # the readers already report HV off
        self.win.auto_connect_all()
        self.assertTrue(self.relay.connected)
        self._run()
        self.assertEqual(self._writes(), [(CHARGING, False), (DISCHARGING, False)])
        self.assertEqual(self.win._relay_mode, GROUND)
        ev = self._mode_events()[-1]
        self.assertEqual((ev["param1"], ev["param2"], ev["param3"]), (UNKNOWN, GROUND, "ok"))
        self.assertIn("startup ground", ev["notes"])
        self.assertAlmostEqual(float(ev["param4"]), 0.0, places=1, msg="no wait when both confirm")
        self.assertEqual([r for r in read_rows(self.dl.get_log_file_path())
                          if r["event_type"] == "ERROR" and r["source"] == "Relay"], [])
        log = self._log()
        self.assertLess(log.index("=== Auto-connect done ==="), log.index("[RELAY] startup ground"))

    def test_startup_ground_with_a_missing_supply_still_grounds_with_an_error(self):
        self.relay.connected = False
        self.wj[1].connected = False
        self.win.relay_panel.port_combo.clear()
        self.win.relay_panel.port_combo.addItem("COM7")
        self.win.on_relay_connect()
        for _ in range(6):
            self.now += 1.0
            self._packet(0, False)
            self.win._relay_tick()
        self._run()
        self.assertEqual(self._writes(), [(CHARGING, False), (DISCHARGING, False)])
        self.assertEqual(self.win._relay_mode, GROUND)
        ev = self._mode_events()[-1]
        self.assertIn("startup ground", ev["notes"])
        self.assertIn("WJ2: not connected", ev["notes"])
        errors = [r for r in read_rows(self.dl.get_log_file_path())
                  if r["event_type"] == "ERROR" and r["source"] == "Relay"]
        self.assertTrue(errors and "WJ2: not connected" in errors[-1]["notes"])

    def test_no_relay_board_means_state_unknown_and_nothing_commanded(self):
        self.relay.connected = False
        self.win.auto_connect_flags = {k: False for k in self.win.auto_connect_flags}
        self.win.auto_connect_all()                       # relay flag off: never connects
        self.assertEqual(self.relay.writes, [])
        self.assertEqual(self.win._relay_mode, UNKNOWN)
        self.assertEqual(self.win.relay_panel.state_label.text(), "State unknown")
        self.assertIn("relay board not connected: state unknown", self._log())

    def test_every_transition_writes_in_the_specified_order(self):
        cases = [
            (GROUND, FLOAT,  [(DISCHARGING, True)]),
            (FLOAT, GROUND,  [(DISCHARGING, False)]),
            (FLOAT, CHARGE,  [(CHARGING, True)]),
            (GROUND, CHARGE, [(DISCHARGING, True), (CHARGING, True)]),
            (CHARGE, FLOAT,  [(CHARGING, False)]),
            (CHARGE, GROUND, [(CHARGING, False), (DISCHARGING, False)]),
        ]
        for current, target, expected in cases:
            with self.subTest(f"{current}->{target}"):
                self._set(current)
                self._hv(False)                               # fresh, HV off
                self.win.on_relay_mode_requested(target)
                self._run()
                self.assertEqual(self._writes(), expected)
                self._rule_held_at_every_write()
                self.assertEqual(self.win._relay_mode, target)
                self.assertEqual(self.win.relay_panel.mode, target)
                ev = self._mode_events()[-1]
                self.assertEqual((ev["param1"], ev["param2"], ev["param3"]),
                                 (current, target, "ok"))
                for relay, on in expected:
                    self.assertIn(f"{relay}={'ON' if on else 'OFF'} ok", ev["notes"])
                if current == CHARGE:
                    self.assertNotEqual(ev["param4"], "", "the HV-off wait is recorded")
                    self.assertEqual([w.hv_off_sent for w in self.wj], [1, 1])
                else:
                    self.assertEqual(ev["param4"], "")

    def test_resending_the_current_state_writes_both_relays(self):
        for mode in rm.MODES:
            with self.subTest(mode):
                self._set(mode)
                self._hv(False)
                self.win.on_relay_mode_requested(mode)
                self._run()
                self.assertEqual(sorted(self._writes()), sorted(rm.TARGET[mode].items()))
                self._rule_held_at_every_write()
                self.assertEqual(self.win._relay_mode, mode)

    def test_from_unknown_every_relay_is_written_in_the_safe_order(self):
        self.win._relay_states = {}
        self.win._relay_set_mode(UNKNOWN)
        self._hv(False)                                   # both confirm HV off
        self.win.on_relay_mode_requested(FLOAT)
        self._run()
        self.assertEqual(self._writes(), [(CHARGING, False), (DISCHARGING, True)])
        self._rule_held_at_every_write()
        self.assertEqual(self.win._relay_mode, FLOAT)
        self.assertEqual([w.hv_off_sent for w in self.wj], [1, 1],
                         "leaving UNKNOWN turns HV off first: it may be CHARGE")

    def test_leaving_unknown_needs_hv_off_like_leaving_charge(self):
        """An unknown state may physically be CHARGE, so FLOAT is refused
        without HV-off confirmation and GROUND completes with an ERROR."""
        self.win._relay_states = {}
        self.win._relay_set_mode(UNKNOWN)
        self.wj[1].connected = False
        self._packet(0, False)
        self.win.on_relay_mode_requested(FLOAT)
        for _ in range(6):
            self.now += 1.0
            self._packet(0, False)
            self.win._relay_tick()
        self.assertEqual(self.relay.writes, [])
        self.assertEqual(self.win._relay_mode, UNKNOWN)
        self.assertEqual(self._mode_events()[-1]["param3"], "timeout")
        self.assertEqual(self.popups[-1][0], "Still in UNKNOWN")
        self.win.on_relay_mode_requested(GROUND)
        for _ in range(6):
            self.now += 1.0
            self._packet(0, False)
            self.win._relay_tick()
        self._run()
        self.assertEqual(self._writes(), [(CHARGING, False), (DISCHARGING, False)])
        self.assertEqual(self.win._relay_mode, GROUND)
        self.assertIn("WJ2: not connected", self._mode_events()[-1]["notes"])

    def test_only_the_current_button_is_lit(self):
        """The buttons are the lamps: the current mode full colour with a
        thick dark border, the other two dimmed with grey text."""
        self._set(FLOAT)
        panel = self.win.relay_panel
        self.assertEqual(panel.lit, {GROUND: False, FLOAT: True, CHARGE: False})
        lit = panel.buttons[FLOAT].styleSheet()
        self.assertIn("#FFD400", lit)
        self.assertIn("3px solid", lit)
        dim = panel.buttons[GROUND].styleSheet()
        self.assertIn("#5A1E1E", dim)
        self.assertIn("#9A9A9A", dim)
        self.assertEqual(panel.state_label.text(),
                         "State: FLOAT (commanded, not read back)")
        self.assertEqual(panel.descriptions[FLOAT].text(), "isolated from supplies and ground")
        self.assertEqual(panel.descriptions[CHARGE].text(), "supplies connected to the Marx, HV on")

    # --------------------------------------------------------- HV gating
    def test_charge_is_refused_unless_both_supplies_report_hv_off_fresh(self):
        self._set(FLOAT)
        cases = {
            "HV on on WJ2": lambda: (self._packet(0, False), self._packet(1, True)),
            "stale packet": lambda: (self._hv(False), setattr(self, "now", self.now + 1.5)),
            "WJ2 disconnected": lambda: (self._hv(False), setattr(self.wj[1], "connected", False)),
            "no packet yet": lambda: None,
        }
        for label, setup in cases.items():
            with self.subTest(label):
                self.setUp()
                self._set(FLOAT)
                setup()
                self.win.on_relay_mode_requested(CHARGE)
                self._run()
                self.assertEqual(self.relay.writes, [], label)
                self.assertEqual(self.win._relay_mode, FLOAT)
                ev = self._mode_events()[-1]
                self.assertEqual((ev["param2"], ev["param3"]), (CHARGE, "refused"))
                self.assertIn("WJ", ev["notes"])
                self.assertTrue(self.popups and self.popups[-1][0] == "CHARGE refused")

    def test_charge_to_float_waits_for_hv_off_readback(self):
        self._set(CHARGE)
        self._hv(True)
        self.win.on_relay_mode_requested(FLOAT)
        self.assertEqual([w.hv_off_sent for w in self.wj], [1, 1])
        self.now += 0.5
        self.win._relay_tick()
        self.assertEqual(self.relay.writes, [], "no write while HV is still on")
        for btn in self.win.relay_panel.buttons.values():
            self.assertFalse(btn.isEnabled(), "buttons off during a transition")
        self.assertEqual(self.win._relay_mode, UNKNOWN, "no mode while relays move")
        panel = self.win.relay_panel
        self.assertEqual(panel.busy_target, FLOAT)
        self.assertTrue(panel._blink_timer.isActive(), "the target button blinks")
        self.assertEqual(panel.state_label.text(), "Changing to FLOAT ...")
        panel._blink()
        self.assertTrue(panel.lit[FLOAT])
        panel._blink()
        self.assertFalse(panel.lit[FLOAT])
        self.now += 0.7
        self._hv(False)
        self._run()
        self.assertEqual(self._writes(), [(CHARGING, False)])
        self.assertEqual(self.win._relay_mode, FLOAT)
        ev = self._mode_events()[-1]
        self.assertEqual(ev["param3"], "ok")
        self.assertAlmostEqual(float(ev["param4"]), 1.2, places=1)
        for btn in self.win.relay_panel.buttons.values():
            self.assertTrue(btn.isEnabled())
        self.assertFalse(panel._blink_timer.isActive())
        self.assertEqual(panel.lit, {GROUND: False, FLOAT: True, CHARGE: False})

    def test_float_timeout_stays_in_charge_with_an_error(self):
        self._set(CHARGE)
        self._hv(True)
        self.win.on_relay_mode_requested(FLOAT)
        for _ in range(6):
            self.now += 1.0
            self._hv(True)
            self.win._relay_tick()
        self.assertIsNone(self.win._relay_transition)
        self.assertEqual(self.relay.writes, [], "the charging relay must not open")
        self.assertEqual(self.win._relay_mode, CHARGE)
        ev = self._mode_events()[-1]
        self.assertEqual((ev["param2"], ev["param3"]), (FLOAT, "timeout"))
        self.assertIn("WJ1: HV on", ev["notes"])
        self.assertIn("ERROR", event_types(self.dl.get_log_file_path()))
        self.assertEqual(self.popups[-1][0], "Still in CHARGE")
        self.assertTrue(all(b.isEnabled() for b in self.win.relay_panel.buttons.values()))

    def test_ground_completes_on_timeout_with_an_error_and_a_warning(self):
        self._set(CHARGE)
        self._packet(0, False)
        self.wj[1].connected = False                     # WJ2 cannot confirm
        self.win.on_relay_mode_requested(GROUND)
        for _ in range(6):
            self.now += 1.0
            self._packet(0, False)
            self.win._relay_tick()
        self._run()
        self.assertEqual(self._writes(), [(CHARGING, False), (DISCHARGING, False)])
        self._rule_held_at_every_write()
        self.assertEqual(self.win._relay_mode, GROUND)
        ev = self._mode_events()[-1]
        self.assertEqual(ev["param3"], "ok")
        self.assertIn("HV-off NOT confirmed", ev["notes"])
        self.assertIn("WJ2: not connected", ev["notes"])
        errors = [r for r in read_rows(self.dl.get_log_file_path())
                  if r["event_type"] == "ERROR" and r["source"] == "Relay"]
        self.assertTrue(errors and "WJ2: not connected" in errors[-1]["notes"])
        self.assertEqual(self.popups[-1][0], "Grounded with HV not confirmed")

    # ------------------------------------------------------- failure path
    def test_partial_failure_stops_shows_unknown_and_leaves_only_ground(self):
        self._set(GROUND)
        self._hv(False)
        self.relay.fail_at = 1                            # the second write raises
        self.win.on_relay_mode_requested(CHARGE)
        self._run()
        self.assertEqual(self.relay.writes, [(0, True, "ok"), (1, True, "FAILED")])
        self.assertEqual(self.win._relay_mode, UNKNOWN)
        self.assertEqual(self.win.relay_panel.state_label.text(), "State unknown")
        enabled = {m for m, b in self.win.relay_panel.buttons.items() if b.isEnabled()}
        self.assertEqual(enabled, {GROUND})
        self.assertIn("charge_relay ON (CH1) FAILED", self._log())
        ev = self._mode_events()[-1]
        self.assertEqual(ev["param3"], "failed")
        self.assertIn("discharge_relay=ON ok, charge_relay=ON FAILED", ev["notes"])
        # GROUND still works, from unknown, in the safe order.
        self.relay.fail_at = None
        self.win.on_relay_mode_requested(GROUND)
        self._run()
        self.assertEqual(self._writes()[-2:], [(CHARGING, False), (DISCHARGING, False)])
        self.assertEqual(self.win._relay_mode, GROUND)
        self.assertTrue(all(b.isEnabled() for b in self.win.relay_panel.buttons.values()))

    def test_request_without_a_connection_is_refused(self):
        self.relay.connected = False
        self.win.on_relay_mode_requested(GROUND)
        self.assertEqual(self.relay.writes, [])
        self.assertEqual(self.popups[-1][0], "Relay not connected")

    # ---------------------------------------------------------- the rest
    # ------------------------------------------ HV buttons through the relays
    def _apply(self, kv=10.0, ma=1.0):
        self.win.wj_panel.voltage.setValue(kv)
        self.win.wj_panel.current.setValue(ma)
        self.win.on_wj_set_voltage()

    def _hv_on(self):
        self._apply()
        self.win.on_wj_hv_on()

    def _hv_on_sent(self):
        return [any(c.get("hv_on") for c in w.set_calls) for w in self.wj]

    def _hv_on_commands(self):
        return [r for r in read_rows(self.dl.get_log_file_path())
                if r["event_type"] == "WJ_COMMAND" and r["param1"] == "HV_ON"]

    def test_hv_on_from_ground_charges_in_the_safe_order_then_sends_hv_on(self):
        self._set(GROUND)
        self._hv(False)
        self._hv_on()
        self.assertEqual(self._hv_on_sent(), [False, False], "not before CHARGE completes")
        self._run()
        self.assertEqual(self._writes(), [(DISCHARGING, True), (CHARGING, True)])
        self._rule_held_at_every_write()
        self.assertEqual(self.win._relay_mode, CHARGE)
        self.assertEqual(self._hv_on_sent(), [True, True])
        self.assertEqual(len(self._hv_on_commands()), 2)
        ev = self._mode_events()[-1]
        self.assertEqual((ev["param1"], ev["param2"], ev["param3"]), (GROUND, CHARGE, "ok"))
        self.assertIn("by HV ON", ev["notes"])

    def test_hv_on_from_float_closes_the_charging_relay_then_sends_hv_on(self):
        self._set(FLOAT)
        self._hv(False)
        self._hv_on()
        self._run()
        self.assertEqual(self._writes(), [(CHARGING, True)])
        self._rule_held_at_every_write()
        self.assertEqual(self.win._relay_mode, CHARGE)
        self.assertEqual(self._hv_on_sent(), [True, True])
        self.assertIn("by HV ON", self._mode_events()[-1]["notes"])

    def test_hv_on_in_charge_sends_directly(self):
        self._set(CHARGE)
        self._hv(False)
        before = len(self._mode_events())
        self._hv_on()
        self.assertEqual(self.relay.writes, [])
        self.assertEqual(self._hv_on_sent(), [True, True])
        self.assertEqual(len(self._mode_events()), before, "no relay transition")

    def test_hv_on_refused_when_a_supply_is_disconnected_sends_nothing(self):
        self._set(GROUND)
        self._hv(False)
        self.wj[1].connected = False
        self._hv_on()
        self._run()
        self.assertEqual(self.relay.writes, [])
        self.assertEqual(self._hv_on_sent(), [False, False])
        self.assertEqual(self.win._relay_mode, GROUND)
        self.assertEqual(self._mode_events()[-1]["param3"], "refused")
        self.assertIn("[WJ] HV ON not sent: CHARGE was refused", self._log())
        errors = [r for r in read_rows(self.dl.get_log_file_path())
                  if r["event_type"] == "ERROR" and r["source"] == "WJ"]
        self.assertTrue(errors and "HV ON not sent" in errors[-1]["notes"])

    def test_hv_on_not_sent_when_a_write_fails_on_the_way_to_charge(self):
        self._set(GROUND)
        self._hv(False)
        self.relay.fail_at = 1
        self._hv_on()
        self._run()
        self.assertEqual(self._hv_on_sent(), [False, False])
        self.assertEqual(self.win._relay_mode, UNKNOWN)
        self.assertIn("HV ON not sent: the transition to CHARGE ended failed", self._log())

    def test_charge_button_charges_in_the_safe_order_then_turns_hv_on(self):
        self._set(GROUND)
        self._hv(False)
        self._apply()
        self.win.relay_panel.mode_requested.emit(CHARGE)
        self.assertEqual(self._hv_on_sent(), [False, False], "not before CHARGE completes")
        self._run()
        self.assertEqual(self._writes(), [(DISCHARGING, True), (CHARGING, True)])
        self._rule_held_at_every_write()
        self.assertEqual(self.win._relay_mode, CHARGE)
        self.assertEqual(self._hv_on_sent(), [True, True])
        ev = self._mode_events()[-1]
        self.assertEqual((ev["param1"], ev["param2"], ev["param3"]), (GROUND, CHARGE, "ok"))
        self.assertIn("CHARGE button", ev["notes"])

    def test_charge_button_in_charge_resends_the_relays_then_hv_on(self):
        self._set(CHARGE)
        self._hv(False)
        self._apply()
        self.win.relay_panel.mode_requested.emit(CHARGE)
        self._run()
        self.assertEqual(self._writes(), [(DISCHARGING, True), (CHARGING, True)])
        self._rule_held_at_every_write()
        self.assertEqual(self._hv_on_sent(), [True, True])
        self.assertEqual(self.win._relay_mode, CHARGE)

    def test_charge_button_refused_sends_no_hv_on(self):
        self._set(FLOAT)
        self._apply()
        self._packet(0, False)
        self._packet(1, True)                            # WJ2 still reads HV on
        self.win.relay_panel.mode_requested.emit(CHARGE)
        self._run()
        self.assertEqual(self.relay.writes, [])
        self.assertEqual(self._hv_on_sent(), [False, False])
        self.assertEqual(self.win._relay_mode, FLOAT)

    def test_charge_refused_without_an_applied_program(self):
        """Nothing applied since the last HV OFF: no relay moves, no HV ON."""
        self._set(FLOAT)
        self._hv(False)
        self.win.wj_panel.voltage.setValue(10.0)          # typed, never applied
        self.win.relay_panel.mode_requested.emit(CHARGE)
        self._run()
        self.assertEqual(self.relay.writes, [])
        self.assertEqual(self._hv_on_sent(), [False, False])
        self.assertEqual(self.win._relay_mode, FLOAT)
        self.assertIn("CHARGE refused: no program applied to WJ1, WJ2", self._log())
        self.assertEqual(self.popups[-1][0], "CHARGE refused")
        errors = [r for r in read_rows(self.dl.get_log_file_path())
                  if r["event_type"] == "ERROR" and r["source"] == "WJ"]
        self.assertTrue(errors and "no program applied" in errors[-1]["notes"])

    def test_hv_off_clears_the_applied_program(self):
        """HV OFF programs 0 kV / 0 mA, so CHARGE needs Apply Program again."""
        self._set(FLOAT)
        self._hv(False)
        self._apply()
        self.win.on_wj_hv_off()                            # FLOAT: HV OFF only
        self.win.relay_panel.mode_requested.emit(CHARGE)
        self._run()
        self.assertEqual(self.relay.writes, [])
        self.assertIn("since the last HV OFF", self._log())
        self._apply()
        self.win.relay_panel.mode_requested.emit(CHARGE)
        self._run()
        self.assertEqual(self._writes(), [(CHARGING, True)])
        self.assertEqual(self._hv_on_sent(), [True, True])

    def test_charge_refused_when_the_panel_no_longer_shows_the_applied_program(self):
        self._set(FLOAT)
        self._hv(False)
        self._apply(10.0, 1.0)
        self.win.wj_panel.voltage.setValue(20.0)          # edited, not applied
        self.win.relay_panel.mode_requested.emit(CHARGE)
        self._run()
        self.assertEqual(self.relay.writes, [])
        self.assertEqual(self._hv_on_sent(), [False, False])
        self.assertIn("the panel shows 20 kV / 1 mA but 10 kV / 1 mA was applied", self._log())

    def test_hv_on_sends_the_applied_values(self):
        self._set(CHARGE)
        self._hv(False)
        self._apply(12.5, 2.0)
        self.win.on_wj_hv_on()
        for wj in self.wj:
            self.assertEqual(wj.set_calls[-1], {"kv": 12.5, "ma": 2.0, "hv_on": True})

    def test_ground_and_float_buttons_never_turn_hv_on(self):
        self._set(CHARGE)
        self._hv(False)
        self.win.relay_panel.mode_requested.emit(FLOAT)
        self._run()
        self.win.relay_panel.mode_requested.emit(GROUND)
        self._run()
        self.assertEqual(self._hv_on_sent(), [False, False])
        self.assertEqual(self.win._relay_mode, GROUND)

    def test_hv_off_from_charge_ends_in_float(self):
        self._set(CHARGE)
        self._hv(True)
        self.win.on_wj_hv_off()
        self.assertEqual([w.hv_off_sent for w in self.wj], [1, 1])
        self.assertEqual(self.relay.writes, [], "the charging relay waits for the readback")
        self._hv(False)
        self._run()
        self.assertEqual(self._writes(), [(CHARGING, False)])
        self._rule_held_at_every_write()
        self.assertEqual(self.win._relay_mode, FLOAT)
        ev = self._mode_events()[-1]
        self.assertEqual((ev["param1"], ev["param2"], ev["param3"]), (CHARGE, FLOAT, "ok"))
        self.assertIn("by HV OFF", ev["notes"])

    def test_hv_off_outside_charge_sends_hv_off_and_leaves_the_relays(self):
        for mode in (GROUND, FLOAT, UNKNOWN):
            with self.subTest(mode):
                if mode == UNKNOWN:
                    self.win._relay_states = {}
                    self.win._relay_set_mode(UNKNOWN)
                    self.relay.writes.clear()
                    for wj in self.wj:
                        wj.hv_off_sent = 0
                else:
                    self._set(mode)
                before = len(self._mode_events())
                self.win.on_wj_hv_off()
                self.assertEqual([w.hv_off_sent for w in self.wj], [1, 1])
                self.assertEqual(self.relay.writes, [], f"HV OFF must not move the relays from {mode}")
                self.assertIsNone(self.win._relay_transition)
                self.assertEqual(self.win._relay_mode, mode)
                self.assertEqual(len(self._mode_events()), before)

    def test_hv_off_timeout_on_hv_off_stays_in_charge(self):
        self._set(CHARGE)
        self._hv(True)
        self.win.on_wj_hv_off()
        for _ in range(6):
            self.now += 1.0
            self._hv(True)
            self.win._relay_tick()
        self.assertEqual(self.relay.writes, [], "the charging relay stays closed under HV")
        self.assertEqual(self.win._relay_mode, CHARGE)
        ev = self._mode_events()[-1]
        self.assertEqual(ev["param3"], "timeout")
        self.assertIn("by HV OFF", ev["notes"])
        self.assertIn("ERROR", event_types(self.dl.get_log_file_path()))
        self.assertEqual(self.popups[-1][0], "Still in CHARGE")

    def test_disconnect_grounds_in_order_then_closes(self):
        self._set(CHARGE)
        self.win.on_relay_disconnect()
        self.assertEqual(self._writes(), [(CHARGING, False), (DISCHARGING, False)])
        self._rule_held_at_every_write()
        self.assertTrue(self.relay.closed)
        ev = self._mode_events()[-1]
        self.assertEqual((ev["param1"], ev["param2"], ev["param3"]), (CHARGE, GROUND, "ok"))
        self.assertIn("at disconnect", ev["notes"])
        self.assertEqual(self.win._relay_mode, UNKNOWN, "no link, nothing commandable")

    def test_gui_close_grounds_in_order_before_session_end(self):
        self._set(CHARGE)
        self.win.close()
        self.assertEqual(self._writes(), [(CHARGING, False), (DISCHARGING, False)])
        self._rule_held_at_every_write()
        self.assertTrue(self.relay.closed)
        types = event_types(self.dl.get_log_file_path())
        self.assertLess(len(types) - 1 - types[::-1].index("RELAY_MODE"),
                        types.index("SESSION_END"))

    def test_fire_requires_float(self):
        self._arm_fire_path()
        self._set(GROUND)
        before = self.win.shot_logger.peek_next_shot_number()
        self.win.on_bnc_fire()
        self.assertEqual(self.win.shot_logger.peek_next_shot_number(), before)
        blocked = [r for r in read_rows(self.dl.get_log_file_path()) if r["event_type"] == "FIRE_BLOCKED"]
        self.assertEqual(blocked[-1]["param1"], "relays_not_float")
        self.assertEqual(self.popups[-1][0], "Relays not FLOAT")
        self._set(FLOAT)
        self.win.on_bnc_fire()
        self.assertEqual(self.win.shot_logger.peek_next_shot_number(), before + 1)

    def test_fire_is_blocked_while_relays_are_moving(self):
        self._arm_fire_path()
        self._set(CHARGE)
        self._hv(True)
        self.win.on_relay_mode_requested(FLOAT)          # waiting on HV off
        before = self.win.shot_logger.peek_next_shot_number()
        self.win.on_bnc_fire()
        self.assertEqual(self.win.shot_logger.peek_next_shot_number(), before)

    def test_step_2_latches_on_float_and_drops_when_leaving(self):
        self._set(FLOAT)
        self.assertTrue(self.win.interlock_passed[2])
        self._set(CHARGE)
        self.assertFalse(self.win.interlock_passed[2])
        self._set(GROUND)
        self.assertFalse(self.win.interlock_passed[2])

    def test_shot_row_carries_the_mode_and_the_two_relays(self):
        self._arm_fire_path()
        self._set(FLOAT)
        self.win.on_bnc_fire()
        row = read_rows(self.win.shot_logger.session_file)[-1]
        self.assertEqual(row["relay_mode"], FLOAT)
        self.assertEqual((row["charge_relay"], row["discharge_relay"]), ("0", "1"))
        self.assertEqual(row["relay_state_source"], "commanded")

    def test_panel_has_exactly_three_mode_buttons_and_nothing_else(self):
        panel = self.win.relay_panel
        self.assertEqual(set(panel.buttons), set(rm.MODES))
        self.assertEqual(set(panel.descriptions), set(rm.MODES))
        for gone in ("switches", "btn_all_on", "btn_all_off", "btn_polling",
                     "poll_status_label", "lamps"):
            self.assertFalse(hasattr(panel, gone), gone)
        for keep in ("port_combo", "btn_refresh", "btn_connect", "btn_disconnect", "lamp"):
            self.assertTrue(hasattr(panel, keep), keep)
        for gone in ("on_relay_all_on", "on_relay_all_off", "_relay_poll_loop",
                     "on_relay_state_changed", "_relay_set"):
            self.assertFalse(hasattr(self.win, gone), gone)


class FakeSerial:
    """pyserial stand-in for the driver test: records every write."""
    instances = []

    def __init__(self, port, baudrate, timeout=1):
        self.port, self.is_open, self.writes = port, True, []
        FakeSerial.instances.append(self)

    def write(self, data):
        self.writes.append(bytes(data))

    def close(self):
        self.is_open = False


class TestRelayDriver(unittest.TestCase):
    def test_driver_sends_no_relay_command_at_connect_or_close(self):
        from instruments.numato_relay import NumatoRelayController
        with patch("instruments.numato_relay.serial.Serial", FakeSerial), \
                patch("instruments.numato_relay.time.sleep", lambda s: None):
            drv = NumatoRelayController()
            drv.connect("COM7")
            ser = FakeSerial.instances[-1]
            self.assertEqual(ser.writes, [], "nothing is commanded at connect")
            drv.relay_on(1)
            self.assertEqual(ser.writes, [b"relay on 1\r"])
            drv.close()
            self.assertEqual(ser.writes, [b"relay on 1\r"], "close sends nothing")
            self.assertFalse(ser.is_open)


class WJFakeSerial:
    """A WJ supply on a fake port. A write while the previous reply is still
    unread is a collision: the crossed reply ("R00000000000040\rA") seen in
    the log when the reader poll and a button shared the port."""

    def __init__(self):
        self.is_open = True
        self.pending = None
        self.collisions = 0
        self._guard = threading.Lock()

    def reset_input_buffer(self):
        with self._guard:
            if self.pending is not None:
                self.collisions += 1
                self.pending = None

    def write(self, pkt):
        body = pkt[1:-3]                        # SOH ... checksum CR
        with self._guard:
            if self.pending is not None:
                self.collisions += 1
            if body.startswith(b"Q"):
                self.pending = b"R00000000000040\r"
            elif body.startswith(b"V"):
                self.pending = b"B14xx\r"
            else:
                self.pending = b"A\r"
        time.sleep(0.0003)                      # the supply takes a moment to answer

    def readline(self):
        time.sleep(0.0003)
        with self._guard:
            reply, self.pending = self.pending, None
        return reply or b""

    def close(self):
        self.is_open = False


class TestWJPortLock(unittest.TestCase):
    def test_reader_polls_and_commands_never_interleave(self):
        """The reader thread polls Q while the GUI thread sends S. Every
        transaction holds the port lock, so no write lands while another
        transaction's reply is still unread."""
        from instruments.wj import WJPowerSupply
        wj = WJPowerSupply()
        fake = WJFakeSerial()
        wj.ser = fake
        bad = []

        def poll():
            for _ in range(300):
                r = wj.query()
                if r.get("type") != "R":
                    bad.append(("Q", r))

        def command():
            for _ in range(60):
                r = wj.send_set(kv=1.0, ma=1.0, hv_on=True)
                if r.get("type") != "A":
                    bad.append(("S", r))

        threads = [threading.Thread(target=poll), threading.Thread(target=command),
                   threading.Thread(target=poll)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(20)
        self.assertEqual(fake.collisions, 0)
        self.assertEqual(bad, [])
