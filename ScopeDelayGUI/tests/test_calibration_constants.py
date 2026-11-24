"""Lock the scope wiring and probe calibration factors.

These values are research constants. If one of these tests fails, a probe
factor or a channel assignment changed. That is only correct when the
hardware changed too. In that case add a new WIRINGS entry in
analysis/scope_channels.py (old shots must keep their wiring) and update
the expected values here in the same commit.
"""

import pytest

from analysis import pipeline as P
from analysis import scope_channels as SC


# probe serial -> calibration factor, as written in scope_channels.PROBES
EXPECTED_PROBES = {
    "2019FC011": 1.85e11,    # LTGS2-232 D-dot
    "2019FC013": -6.51e8,    # LTGS2-007 B-dot
    "2019FC016": -6.70e8,    # LTGS1-007 B-dot
    "2019FC017": 1.83e11,    # LTGS1-232 D-dot
    "2019FC027": -6.96e8,    # C315 B-dot
    "2019FC030": 1.64e11,
    "2019FC032": 1.56e11,    # C225 D-dot
    "2019FC033": 1.56e11,    # A225 D-dot
    "RVM1": 0.97943,
    "RVM2": 0.998535,
}

# signal -> (scope, column, factor) for each wiring, by its first shot
EXPECTED_CHANNELS = {
    0: {
        "LTGS2_Ddot": (2, 1, 1.85e11), "LTGS2_Bdot": (2, 2, -6.51e8),
        "LTGS1_Ddot": (2, 3, 1.83e11), "LTGS1_Bdot": (2, 4, -6.70e8),
        "RVM1": (1, 1, 0.97943), "RVM2": (1, 2, 0.998535),
        "TrigMon": (1, 3, 1.0), "TrigOut": (1, 4, 1.0),
        "Qsw1": (3, 1, 1.0), "Qsw2": (3, 2, 1.0),
        "C315": (3, 3, -6.96e8), "C225": (3, 4, 1.56e11), "A225": None,
    },
    65: {
        "LTGS2_Ddot": (2, 1, 1.85e11), "LTGS2_Bdot": None,
        "LTGS1_Ddot": (2, 3, 1.83e11), "LTGS1_Bdot": None,
        "RVM1": (1, 1, 0.97943), "RVM2": (1, 2, 0.998535),
        "TrigMon": (1, 3, 1.0), "TrigOut": (1, 4, 1.0),
        "Qsw1": None, "Qsw2": None,
        "C315": None, "C225": (3, 4, 1.56e11), "A225": (2, 4, 1.56e11),
    },
}

EXPECTED_ANCHORS = {
    0: [("rigol2", 3), ("rigol2", 4), ("rigol3", 4)],
    65: [("rigol2", 3), ("rigol2", 1), ("rigol3", 4)],
}

EXPECTED_OUTPUTS = {
    0: [("C225", "ddot", 3, 4, 1.56e11), ("C315", "bdot", 3, 3, -6.96e8)],
    65: [("A225", "ddot", 2, 4, 1.56e11), ("B225", "ddot", 3, 3, 1.64e11),
         ("C225", "ddot", 3, 4, 1.56e11)],
}


def test_probe_factors_unchanged():
    assert set(SC.PROBES) == set(EXPECTED_PROBES)
    for serial, cf in EXPECTED_PROBES.items():
        assert SC.PROBES[serial] == pytest.approx(cf, rel=1e-12), serial


def test_wiring_boundaries():
    assert [w["from_shot"] for w in SC.WIRINGS] == [0, 65]
    assert SC.wiring_for(1)["from_shot"] == 0
    assert SC.wiring_for(64)["from_shot"] == 0
    assert SC.wiring_for(65)["from_shot"] == 65
    assert SC.wiring_for(400)["from_shot"] == 65
    assert SC.wiring_for(float("nan"))["from_shot"] == 0
    assert SC.wiring_for("not a number")["from_shot"] == 0


@pytest.mark.parametrize("from_shot", sorted(EXPECTED_CHANNELS))
def test_channel_assignments(from_shot):
    w = SC.wiring_for(from_shot)
    for signal, want in EXPECTED_CHANNELS[from_shot].items():
        got = SC.scope_channel(w, signal)
        if want is None:
            assert got is None, signal
        else:
            assert got[:2] == want[:2], signal
            assert got[2] == pytest.approx(want[2], rel=1e-12), signal
    assert [tuple(a) for a in w["anchors"]] == EXPECTED_ANCHORS[from_shot]


@pytest.mark.parametrize("from_shot", sorted(EXPECTED_OUTPUTS))
def test_output_probes(from_shot):
    got = SC.output_probes(SC.wiring_for(from_shot))
    want = EXPECTED_OUTPUTS[from_shot]
    assert [g[:4] for g in got] == [w[:4] for w in want]
    for g, w in zip(got, want):
        assert g[4] == pytest.approx(w[4], rel=1e-12)


def test_bdot_geometry_constants():
    assert P.CAL["geom"] == pytest.approx(47.12388980384689, rel=1e-12)
    assert P.CAL["bScale"] == -4.5
