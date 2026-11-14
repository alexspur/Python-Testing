"""Regression check on a real shot: shot 43, three Rigol scopes.

data/shots/shot0043_raw.npz is the raw record written by
tools/analysis/export_shot.py. The expected numbers below come from the
pipeline at commit 952d6e6 (main before the repository cleanup). They cover
D-dot and B-dot integration, the RVM reference and gains, Q-switch timing
and both pulse-spacing estimates.

A failure means the processing mathematics changed. If that change is
intended, bump PIPELINE_VERSION in analysis/process_shots.py and update
these numbers in the same commit.
"""

from pathlib import Path

import numpy as np
import pytest

from analysis import pipeline as P
from analysis import scope_channels as SC

NPZ = Path(__file__).resolve().parents[2] / "data" / "shots" / "shot0043_raw.npz"

EXPECTED_PEAKS = {
    "LTGS1_Ddot": 473.27684315664027,
    "LTGS2_Ddot": 455.1997158104723,
    "LTGS1_Bdot": 196.8250394197866,
    "LTGS2_Bdot": 184.83890148477013,
    "C225_Ddot": 199.4758156971989,
    "C315_Bdot": 196.86544566030432,
    "RVM1": 397.74457272452696,
    "RVM2": 432.6278353877649,
    "t_Qsw1": 0.09146000000000132,
    "t_Qsw2": 1.0902599999999958,
    "t_TrigOut": -3.5114500000000053,
}

EXPECTED_ARRAYS = {
    "G": [[1.234069960242405, 1.2360247470981527],
          [1.0669789692446168, 1.0689281855412993]],
    "ddot_factor": [1.0753891235400284, 0.92989595869088],
    "rvm_factor": [0.9991483749033286, 1.0008523509801572],
    "rvm_gain": [1.2360247470981527, 1.0689281855412993],
    "rvm_rampRMS": [6.61862676527523, 14.267520849805331],
    "rvm_ref": [2.0, 2.0],
}

RTOL = 1e-9


@pytest.fixture(scope="module")
def shot43():
    if not NPZ.exists():
        pytest.skip(f"{NPZ} not found")
    z = np.load(NPZ, allow_pickle=True)
    scopes = [np.column_stack([z[f"r{k}_t"][:len(z[f"r{k}_v"])],
                               z[f"r{k}_v"].astype(float)]) for k in (1, 2, 3)]
    return P.process_waveforms(*scopes, wiring=SC.wiring_for(43))


def test_pulse_window(shot43):
    assert shot43["tPulse"] == pytest.approx(0.00018401214, rel=RTOL)
    assert shot43["tEnd"] == pytest.approx(0.000185682, rel=RTOL)
    assert shot43["G_consistency"] == pytest.approx(1.0002424551139628, rel=RTOL)


def test_peaks(shot43):
    peaks = shot43["peaks"]
    assert set(peaks) == set(EXPECTED_PEAKS)
    for name, want in EXPECTED_PEAKS.items():
        assert float(peaks[name]) == pytest.approx(want, rel=RTOL), name


@pytest.mark.parametrize("name", sorted(EXPECTED_ARRAYS))
def test_rvm_reference_and_gains(shot43, name):
    np.testing.assert_allclose(np.asarray(shot43[name], dtype=float),
                               EXPECTED_ARRAYS[name], rtol=RTOL)


def test_pulse_spacing(shot43):
    assert P.spacing_from_rvm(shot43) == pytest.approx(980.2786724690526, rel=RTOL)
    assert P.spacing_from_qsw(shot43) == pytest.approx(998.7999999999945, rel=RTOL)
