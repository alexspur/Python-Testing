# utils/relay_modes.py
"""Three-state HV relay control on two Numato relays. Pure logic, no I/O.

Relays: the CHARGING relay connects the WJ supplies to the Marx; the
DISCHARGING relay is the grounding relay, so disengaged (Numato OFF) ties
the Marx to ground. "Engaged" means the coil is energized (Numato ON).

States, as (charging, discharging):
    GROUND   off, off   the Marx is grounded
    FLOAT    off, on    isolated from the supplies and from ground
    CHARGE   on,  on    the supplies are connected to the Marx
    UNKNOWN             nothing commanded yet, or a write failed part way

Safety rule, checked on the state every write would produce before it is
sent: the charging relay is never on while the discharging relay is off.
That would connect a supply straight to ground.

The state is commanded, never read back: the Numato only reports its own
software cache, so nothing here claims a relay was confirmed.
"""

GROUND, FLOAT, CHARGE, UNKNOWN = "GROUND", "FLOAT", "CHARGE", "UNKNOWN"
MODES = (GROUND, FLOAT, CHARGE)

# Shot-log names of the two relays. The channel each sits on is the main
# window's business (it has always been channel 1 charging, channel 0
# discharging); this module never sees a channel number.
CHARGING = "charge_relay"
DISCHARGING = "discharge_relay"

TARGET = {
    GROUND: {CHARGING: False, DISCHARGING: False},
    FLOAT:  {CHARGING: False, DISCHARGING: True},
    CHARGE: {CHARGING: True,  DISCHARGING: True},
}

LAMP = {GROUND: "red", FLOAT: "yellow", CHARGE: "green"}

# HV must be off, and confirmed by a fresh packet from a connected supply,
# before the charging relay may close (entering CHARGE). Leaving CHARGE
# turns HV off first and waits for the same confirmation.
HV_OFF_WAIT_S = 5.0
HV_FRESH_S = 1.0


class SafetyViolation(RuntimeError):
    """A write would leave the charging relay on with the discharging relay off."""


def check(states):
    """Raise SafetyViolation if `states` ({relay: on}) breaks the rule.
    An unknown relay counts as engaged for the charging relay (worst case)
    and as disengaged for the discharging relay (worst case)."""
    charging = states.get(CHARGING)
    discharging = states.get(DISCHARGING)
    if (charging is None or charging) and not discharging:
        raise SafetyViolation(
            f"charging relay {'on' if charging else 'unknown'} while the discharging relay is "
            f"{'off' if discharging is False else 'unknown'}: the supply would be tied to ground")


def state_of(states):
    """The mode a {relay: on} dict corresponds to, or UNKNOWN."""
    for mode, target in TARGET.items():
        if all(states.get(r) is on for r, on in target.items()):
            return mode
    return UNKNOWN


def writes_for(current, target):
    """Ordered (relay, on) writes that take `current` to `target`.

    Known-to-known transitions send only what changes, in the safe order.
    From UNKNOWN, or when the target is the current state (a resend to
    resync after an unknown start), every relay of the target is written,
    still in the safe order: a relay that opens ground goes last, a relay
    that disconnects the supply goes first.
    """
    if target not in TARGET:
        raise ValueError(f"not a relay mode: {target!r}")
    full = {
        GROUND: [(CHARGING, False), (DISCHARGING, False)],
        FLOAT:  [(CHARGING, False), (DISCHARGING, True)],
        CHARGE: [(DISCHARGING, True), (CHARGING, True)],
    }
    if current not in TARGET or current == target:
        return list(full[target])
    exact = {
        (GROUND, FLOAT):  [(DISCHARGING, True)],
        (FLOAT, GROUND):  [(DISCHARGING, False)],
        (FLOAT, CHARGE):  [(CHARGING, True)],
        (GROUND, CHARGE): [(DISCHARGING, True), (CHARGING, True)],
        (CHARGE, FLOAT):  [(CHARGING, False)],
        (CHARGE, GROUND): [(CHARGING, False), (DISCHARGING, False)],
    }
    return list(exact[(current, target)])


def apply_checked(states, relay, on):
    """The state after one write, having checked the rule on it first.
    Raises SafetyViolation before the caller sends anything."""
    after = dict(states)
    after[relay] = bool(on)
    check(after)
    return after


def needs_hv_off(current, target):
    """Leaving CHARGE turns HV off and waits for confirmation first. So does
    leaving UNKNOWN: a failed write, or a fresh start, may physically be
    CHARGE, and the charging relay must not open under HV."""
    return current in (CHARGE, UNKNOWN) and target != CHARGE


def hv_off_confirmed(supply):
    """One supply's cached state -> (confirmed off?, reason if not).

    supply: {"connected": bool, "hv_on": bool|None, "age_s": float|None}.
    Off counts only from a connected supply whose last packet is under
    HV_FRESH_S old and says HV is off. Anything else is not confirmation.
    """
    if not supply.get("connected"):
        return False, "not connected"
    age = supply.get("age_s")
    if age is None:
        return False, "no packet yet"
    if age > HV_FRESH_S:
        return False, f"last packet {age:.1f} s old"
    if supply.get("hv_on"):
        return False, "HV on"
    return True, ""


def hv_all_off(supplies):
    """(all confirmed off?, [reason per supply that is not])."""
    reasons = []
    for name, supply in supplies.items():
        ok, why = hv_off_confirmed(supply)
        if not ok:
            reasons.append(f"{name}: {why}")
    return not reasons, reasons
