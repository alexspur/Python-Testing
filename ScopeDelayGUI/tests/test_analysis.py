"""Tests for the shot analysis package. Synthetic data only, no hardware."""

import csv

import numpy as np
import pytest
from scipy.io import loadmat

from analysis import pipeline as P
from analysis import process_shots as PS

CF = P.CAL
HDR = ["Time (s)", "Voltage_CH1 (V)", "Voltage_CH2 (V)", "Voltage_CH3 (V)", "Voltage_CH4 (V)"]


def _line(t, tc, amp, T=3e-6):
    v = np.zeros_like(t)
    r = (t > tc - T) & (t <= tc)
    v[r] = amp * (1 - np.cos(np.pi * (t[r] - (tc - T)) / T)) / 2
    a = t > tc
    v[a] = amp * np.exp(-(t[a] - tc) / 15e-9) * np.cos(2 * np.pi * (t[a] - tc) / 80e-9)
    return v


def _write(path, M):
    np.savetxt(path, M, delimiter=",", fmt="%.9e", header=",".join(HDR), comments="")


def make_shot(folder, stamp, idx, spacing_ns, fired=True, seed=0):
    """Three rigol CSVs. Pulse 1 at 10 us, Q-switches 2.5 us earlier."""
    rng = np.random.default_rng(seed)
    t = np.arange(-20e-6, 25e-6, 1e-9)
    n = t.size
    t1, t2 = 10e-6, 10e-6 + spacing_ns * 1e-9
    g = 1.0 if fired else 0.0
    V1, V2 = g * _line(t, t1, -500e3), g * _line(t, t2, -495e3)
    I1 = np.where(t > t1, g * 5e3 * np.exp(-(t - t1) / 60e-9), 0)
    I2 = np.where(t > t2, g * 5e3 * np.exp(-(t - t2) / 60e-9), 0)
    bk = CF["geom"] * CF["bScale"]
    r2 = np.column_stack([
        t,
        np.gradient(V2, t) / CF["CF_CH1"] + rng.normal(0, .5, n),
        np.gradient(I2, t) / (CF["CF_CH2"] * bk) + rng.normal(0, .05, n),
        np.gradient(V1, t) / CF["CF_CH3"] * 1.05 + rng.normal(0, .5, n),
        np.gradient(I1, t) / (CF["CF_CH4"] * bk) + rng.normal(0, .05, n)])
    q1 = np.where((t > t1 - 2.5e-6) & (t < t1 - 2.0e-6), 3.5, 0.0)
    q2 = np.where((t > t2 - 2.5e-6) & (t < t2 - 2.0e-6), 3.5, 0.0)
    r3 = np.column_stack([
        t, q1 + rng.normal(0, .02, n), q2 + rng.normal(0, .02, n),
        np.gradient((I1 + I2) / 2, t) / (CF["CF3_CH3"] * bk) + rng.normal(0, .05, n),
        np.gradient((V1 + V2) / 2, t) / CF["CF3_CH4"] + rng.normal(0, .5, n)])
    r1 = np.column_stack([
        t, V1 / CF["DIV_CH1"] + rng.normal(0, 300, n), V2 / CF["DIV_CH2"] + rng.normal(0, 300, n),
        rng.normal(0, .1, n), np.where(t > 0, 2.4, 0)])
    names = []
    for k, M in ((1, r1), (2, r2), (3, r3)):
        nm = PS.default_name(k, stamp, idx)
        _write(folder / nm, M)
        names.append(nm)
    return names


def make_session(root, stamp, shots):
    """shots: list of (shot_number, spacing_ns, kind) with kind in
    fired, dry, missing."""
    sdir = root / "2026.09.25" / f"experiment_log_{stamp}"
    sdir.mkdir(parents=True)
    hdr = ["shot_number", "session_shot_index", "datetime", "pressure_psi",
           "wj1_charge_kv", "wj2_charge_kv", "pulse_spacing_ns",
           "rigol1_file", "rigol2_file", "rigol3_file", "notes"]
    rows = [hdr]
    for idx, (num, sp, kind) in enumerate(shots, start=1):
        if kind == "missing":
            names = [PS.default_name(k, stamp, idx) for k in (1, 2, 3)]
        else:
            names = make_shot(sdir, stamp, idx, sp, fired=(kind == "fired"), seed=num)
        rows.append([num, idx, "2026-09-25 10:00:00.000", 67.6, 70.0, 70.1, sp,
                     *names, "note, with comma"])
    with open(sdir / f"shot_log_{stamp}.csv", "w", newline="") as f:
        csv.writer(f).writerows(rows)
    return sdir


@pytest.fixture
def logs(tmp_path):
    root = tmp_path / "logs"
    make_session(root, "20260925_100000",
                 [(40, 200, "fired"), (41, 500, "fired"), (42, 200, "dry"), (43, 200, "missing")])
    return root


def test_matlab_helpers():
    x = np.array([3., 1, 4, 1, 5, 9, 2, 6])
    # even window: k/2 back, k/2 - 1 forward (MATLAB movmax)
    assert list(P.movmax(x, 4)) == [3, 4, 4, 5, 9, 9, 9, 9]
    assert np.allclose(P.movmean(x, 3), [2, 8 / 3, 2, 10 / 3, 5, 16 / 3, 17 / 3, 4])
    assert P.mround(2.5) == 3 and P.mround(-2.5) == -3


def test_statuses_spacing_and_outputs(logs):
    counts = PS.run(root=logs)
    assert counts == {"ok": 2, "no_fire": 1, "missing_waveforms": 1, "failed": 0, "cached": 0}
    out = logs / "processed_shots"
    rows = {r["shot_number"]: r for r in csv.DictReader(open(out / "shot_summary.csv"))}
    assert rows["40"]["status"] == "ok" and rows["42"]["status"] == "no_fire"
    assert rows["43"]["status"] == "missing_waveforms"
    for n, sp in (("40", 200), ("41", 500)):
        assert abs(float(rows[n]["spacing_qsw_ns"]) - sp) < 1.5
        assert abs(float(rows[n]["spacing_rvm_ns"]) - sp) < 1.5
        assert 1.0 < float(rows[n]["rvm_gain_1"]) < 1.1   # 5 % gain injected on LTGS1
    # dry shot still measures the laser timing
    assert abs(float(rows["42"]["spacing_qsw_ns"]) - 200) < 1.5
    sdir = next(logs.glob("*/experiment_log_*"))
    assert (sdir / "shot_0040_analysis.png").exists()
    assert (sdir / "shot_0042_raw.png").exists()
    assert not (sdir / "shot_0042_analysis.png").exists()
    assert (out / "summary.png").exists()


def test_mat_file_matches_ltgs_gui3_layout(logs):
    PS.run(root=logs, plots=False)
    S = loadmat(logs / "processed_shots" / "shot_0040.mat", squeeze_me=True)
    for f in ("shot_number", "status", "peaks", "settings", "Dt", "Dv", "Bt", "Bv",
              "Rt", "Rv", "Qt", "Qv", "C225_t", "C225", "C315_t", "C315",
              "rvm_gain", "spacing_rvm_ns", "spacing_qsw_ns", "files", "meta"):
        assert f in S, f
    assert S["status"] == "ok" and S["shot_number"] == 40
    assert S["Dt"].shape == (2,) and S["Dt"][0].ndim == 1
    assert S["settings"]["pulse_spacing_cmd_ns"] == 200
    assert "with comma" in str(S["meta"]["notes"])


def test_second_run_uses_cache_and_force_redoes(logs):
    PS.run(root=logs, plots=False)
    c = PS.run(root=logs, plots=False)
    assert c["cached"] == 3 and c["ok"] == 0          # missing shots are always retried
    c = PS.run(root=logs, plots=False, force=True)
    assert c["ok"] == 2


def test_single_shot_mode(logs):
    sdir = next(logs.glob("*/experiment_log_*"))
    c = PS.run(session=sdir, shot=41, plots=False)
    assert c["ok"] == 1 and sum(c.values()) == 1
    assert (logs / "processed_shots" / "shot_0041.mat").exists()


def test_cli_exit_code_and_prefix(logs, capsys):
    rc = PS.main([str(logs), "--no-plots"])
    assert rc == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines and all(ln.startswith("[ANALYSIS]") for ln in lines)
    import json
    res = [json.loads(ln.split("result ", 1)[1]) for ln in lines if ln.startswith("[ANALYSIS] result ")]
    assert {r["shot_number"]: r["status"] for r in res} == {
        40: "ok", 41: "ok", 42: "no_fire", 43: "missing_waveforms"}


def test_killed_run_leaves_nothing_ltgs_gui3_would_load(logs):
    out = logs / "processed_shots"
    out.mkdir(parents=True)
    (out / "partial_shot_0040.mat.tmp").write_bytes(b"half written")
    PS.run(root=logs, plots=False)
    assert not list(out.glob("partial_*"))
    assert sorted(p.name for p in out.glob("shot_*.mat")) == [
        "shot_0040.mat", "shot_0041.mat", "shot_0042.mat", "shot_0043.mat"]


def test_repeated_time_value_does_not_crash(tmp_path):
    """A July export repeated its first time value: t[1] - t[0] was zero."""
    t = np.arange(-20e-6, 25e-6, 1e-9)
    t[1] = t[0]
    v = np.where((t > 5e-6) & (t < 5.5e-6), 3.5, 0.0)
    vg, tr = P.gate_qsw(t, v)
    assert abs(tr - 5e-6) < 3e-9


def test_late_scope3_record_skips_c225_c315_not_the_shot(tmp_path):
    root = tmp_path / "logs"
    sdir = make_session(root, "20260925_110000", [(50, 200, "fired")])
    f3 = sdir / PS.default_name(3, "20260925_110000", 1)
    M = np.loadtxt(f3, delimiter=",", skiprows=1)
    M = M[M[:, 0] > 9.9e-6]                  # scope 3 starts 0.1 us before pulse 1
    _write(f3, M)
    counts = PS.run(root=root, plots=True)
    assert counts["ok"] == 1 and counts["failed"] == 0
    row = next(csv.DictReader(open(root / "processed_shots" / "shot_summary.csv")))
    assert row["status"] == "ok" and row["C225_Ddot_kV"] == "" and row["C315_Bdot_kV"] == ""
    assert "C225/C315 skipped" in row["error"]
    assert float(row["LTGS1_Ddot_kV"]) > 400


def test_one_bad_shot_does_not_stop_the_run(logs, monkeypatch):
    real = PS.process_one

    def boom(sh, *a, **k):
        if sh["shot_number"] == 40:
            raise OverflowError("synthetic")
        return real(sh, *a, **k)
    monkeypatch.setattr(PS, "process_one", boom)
    c = PS.run(root=logs, plots=False)
    assert c["failed"] == 1 and c["ok"] == 1 and c["no_fire"] == 1


def test_scope_files_without_a_shot_row_are_processed(tmp_path):
    """The scopes triggered but no GUI Fire happened, so the shot log has only
    its header. The files are still found and processed, unnumbered."""
    root = tmp_path / "logs"
    stamp = "20260924_164325"
    sdir = root / "2026.09.24" / f"experiment_log_{stamp}"
    sdir.mkdir(parents=True)
    make_shot(sdir, stamp, 1, 200, fired=True, seed=7)
    (sdir / f"shot_log_{stamp}.csv").write_text("shot_number,session_shot_index,datetime\n")
    c = PS.run(root=root, plots=False)
    assert c["ok"] == 1
    assert (root / "processed_shots" / f"shot_{stamp}.mat").exists()


def test_extra_files_beside_logged_shots_are_picked_up(logs):
    sdir = next(logs.glob("*/experiment_log_*"))
    stamp = sdir.name.replace("experiment_log_", "")
    for k in (1, 2, 3):   # a set of files no shot row names
        src = sdir / PS.default_name(k, stamp, 1)
        (sdir / f"rigol{k}_{stamp}_read01.csv").write_bytes(src.read_bytes())
    c = PS.run(root=logs, plots=False)
    assert c["ok"] == 3                     # shots 40, 41 and the extra set
    assert (logs / "processed_shots" / f"shot_{stamp}_read01.mat").exists()
