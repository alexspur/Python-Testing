"""Shot Replay: lookup, sandboxed reruns, overrides. Synthetic data only."""

import numpy as np
import pytest

from analysis import process_shots as PS
from analysis import replay as R
from tests.test_analysis import make_session


@pytest.fixture
def logs(tmp_path):
    root = tmp_path / "logs"
    make_session(root, "20260925_100000", [(44, 200, "fired"), (45, 500, "dry"), (46, 300, "fired")])
    PS.run(root=root, plots=False)
    return root


def _listing(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def test_find_shot_by_number(logs):
    idx = R.index_shots(logs)
    assert [r.number for r in idx] == [44, 45, 46]
    assert R.find_shot(idx, 46).key == "shot_0046"
    assert R.find_shot(idx, 99) is None


def test_replay_matches_stored_and_writes_only_to_the_sandbox(logs, tmp_path):
    before = _listing(logs)
    ref = R.find_shot(R.index_shots(logs), 46)
    res = R.run_shot(ref, cache=R.WaveformCache(), plots=False, out_base=tmp_path / "out")
    stored = R.stored_results(logs)["shot_0046"]
    for c, a, b, d in R.compare_rows(stored, res.row):
        if c != "error":
            assert a == b, c
    assert (tmp_path / "out" / "shot_0046" / "shot_0046.mat").exists()
    assert _listing(logs) == before


def test_cal_override_applies_to_one_run_only(logs, tmp_path):
    ref = R.find_shot(R.index_shots(logs), 46)
    cal0 = dict(R.P.CAL)
    base = R.run_shot(ref, plots=False, out_base=tmp_path)
    hot = R.run_shot(ref, plots=False, out_base=tmp_path,
                     cal_overrides={"DIV_CH1": cal0["DIV_CH1"] * 1.1})
    assert float(hot.row["RVM1_kV"]) == pytest.approx(float(base.row["RVM1_kV"]) * 1.1, rel=1e-3)
    assert R.P.CAL == cal0


def test_scope_settings_from_row():
    meta = {"rigol2_settings_source": "readback", "rigol2_timebase_scale_s_div": "2e-06",
            "rigol2_ch3_scale_v_div": "5"}
    s = R.scope_settings(meta, 2)
    assert s["scope"]["timebase_scale_s_div"] == "2e-06"
    assert s["channels"][3]["scale_v_div"] == "5"
    assert R.scope_settings({"rigol2_settings_source": "UNKNOWN"}, 2) == {}


def test_parse_shot_range():
    assert R.parse_shot_range("40-42, 46;50") == [40, 41, 42, 46, 50]
    assert np.all(np.diff(R.parse_shot_range("5-3")) == 1)


def test_mat_result_traces_and_group_stats(logs):
    S = R.load_mat_result(logs / "processed_shots" / "shot_0044.mat")
    assert S["status"] == "ok"
    for key in R.TRACE_KEYS:
        t, y = R.trace_xy(S, key)
        assert t.size == y.size and t.min() >= -12 and t.max() <= 12
    rows = list(R.stored_results(logs).values())
    assert [R.is_healthy(r) for r in sorted(rows, key=lambda r: r["shot_number"])] == [
        True, False, True]
    stats = {s["spacing_cmd_ns"]: s for s in R.group_stats(rows)}
    assert stats[500]["n"] == 1 and stats[500]["n_ok"] == 0
    assert abs(stats[300]["spacing_qsw_ns"][0]) < 1.5         # measured - commanded
