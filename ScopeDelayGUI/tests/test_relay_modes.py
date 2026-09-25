"""The relay state machine: write order per transition, the safety rule
after every single write, and HV-off confirmation. Pure logic, no GUI."""

import itertools

import pytest

from utils import relay_modes as rm
from utils.relay_modes import CHARGE, CHARGING, DISCHARGING, FLOAT, GROUND, UNKNOWN


def walk(current, target):
    """Apply the writes for current -> target one at a time, checking the
    rule after each, and return the write list and the final state."""
    states = dict(rm.TARGET[current]) if current in rm.TARGET else {}
    writes = rm.writes_for(current, target)
    for relay, on in writes:
        states = rm.apply_checked(states, relay, on)      # raises on a violation
    return writes, states


@pytest.mark.parametrize("current,target,expected", [
    (GROUND, FLOAT,  [(DISCHARGING, True)]),
    (FLOAT, GROUND,  [(DISCHARGING, False)]),
    (FLOAT, CHARGE,  [(CHARGING, True)]),
    (GROUND, CHARGE, [(DISCHARGING, True), (CHARGING, True)]),
    (CHARGE, FLOAT,  [(CHARGING, False)]),
    (CHARGE, GROUND, [(CHARGING, False), (DISCHARGING, False)]),
])
def test_every_transition_has_the_specified_write_order(current, target, expected):
    writes, final = walk(current, target)
    assert writes == expected
    assert final == rm.TARGET[target]


@pytest.mark.parametrize("current,target", list(itertools.product(rm.MODES, rm.MODES)))
def test_the_safety_rule_holds_after_every_single_write(current, target):
    walk(current, target)                       # apply_checked raises otherwise


@pytest.mark.parametrize("target", rm.MODES)
def test_from_unknown_every_relay_is_written_in_the_safe_order(target):
    writes, final = walk(UNKNOWN, target)
    assert sorted(r for r, _ in writes) == sorted([CHARGING, DISCHARGING])
    assert final == rm.TARGET[target]
    if target == CHARGE:
        assert writes[0] == (DISCHARGING, True), "ground opens only after the discharge relay is on"
    else:
        assert writes[0] == (CHARGING, False), "the supply is disconnected first"


@pytest.mark.parametrize("mode", rm.MODES)
def test_resending_the_current_state_writes_every_relay(mode):
    writes, final = walk(mode, mode)
    assert len(writes) == 2 and final == rm.TARGET[mode]


def test_the_rule_itself():
    rm.check({CHARGING: False, DISCHARGING: False})
    rm.check({CHARGING: True, DISCHARGING: True})
    rm.check({CHARGING: False, DISCHARGING: True})
    with pytest.raises(rm.SafetyViolation):
        rm.check({CHARGING: True, DISCHARGING: False})
    with pytest.raises(rm.SafetyViolation):
        rm.check({DISCHARGING: False})              # charging unknown: worst case
    with pytest.raises(rm.SafetyViolation):
        rm.check({CHARGING: True})                  # discharging unknown: worst case
    with pytest.raises(rm.SafetyViolation):
        rm.apply_checked({CHARGING: True, DISCHARGING: True}, DISCHARGING, False)


def test_state_of_and_needs_hv_off():
    assert rm.state_of({CHARGING: False, DISCHARGING: False}) == GROUND
    assert rm.state_of({CHARGING: False, DISCHARGING: True}) == FLOAT
    assert rm.state_of({CHARGING: True, DISCHARGING: True}) == CHARGE
    assert rm.state_of({CHARGING: True, DISCHARGING: False}) == UNKNOWN
    assert rm.state_of({}) == UNKNOWN
    assert rm.needs_hv_off(CHARGE, FLOAT) and rm.needs_hv_off(CHARGE, GROUND)
    assert rm.needs_hv_off(UNKNOWN, FLOAT) and rm.needs_hv_off(UNKNOWN, GROUND)
    assert not rm.needs_hv_off(CHARGE, CHARGE) and not rm.needs_hv_off(UNKNOWN, CHARGE)
    assert not rm.needs_hv_off(FLOAT, GROUND) and not rm.needs_hv_off(GROUND, CHARGE)
    with pytest.raises(ValueError):
        rm.writes_for(GROUND, "OFF")


def test_hv_off_counts_only_from_a_connected_fresh_packet():
    ok, why = rm.hv_off_confirmed({"connected": True, "hv_on": False, "age_s": 0.2})
    assert ok and why == ""
    assert rm.hv_off_confirmed({"connected": False, "hv_on": False, "age_s": 0.2}) == (False, "not connected")
    assert rm.hv_off_confirmed({"connected": True, "hv_on": False, "age_s": None}) == (False, "no packet yet")
    assert rm.hv_off_confirmed({"connected": True, "hv_on": False, "age_s": 1.5}) == (False, "last packet 1.5 s old")
    assert rm.hv_off_confirmed({"connected": True, "hv_on": True, "age_s": 0.1}) == (False, "HV on")
    ok, reasons = rm.hv_all_off({"WJ1": {"connected": True, "hv_on": False, "age_s": 0.1},
                                 "WJ2": {"connected": True, "hv_on": True, "age_s": 0.1}})
    assert not ok and reasons == ["WJ2: HV on"]
    assert rm.hv_all_off({"WJ1": {"connected": True, "hv_on": False, "age_s": 0.1}}) == (True, [])
