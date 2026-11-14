"""Hardware-free checks on the standalone scripts in tools/.

Each import runs in a fresh interpreter started from a temporary folder, so
a script that depends on the working folder shows up here. Scripts that
touch hardware at import time are never imported (see tools/README.md).
"""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS = REPO_ROOT / "tools"
NPZ = REPO_ROOT / "data" / "shots" / "shot0043_raw.npz"

# Scripts whose module level only defines things. Importing them is safe.
IMPORT_SAFE = [
    "analysis/ddot_analysis.py", "analysis/export_shot.py", "analysis/session_report.py",
    "calibration/VacuumChamberCalibration.py", "calibration/cable_cal.py",
    "calibration/calibrate_channel.py", "calibration/dg535_delay.py",
    "calibration/dg535_io.py", "calibration/diff_channels.py",
    "calibration/edge_timing.py", "calibration/fiber_delay_sweep.py",
    "calibration/fiber_transit.py", "calibration/laser_io.py",
    "calibration/prep_cal.py", "calibration/qsw_spacing_test.py",
    "calibration/verify_delays.py",
    "instrument_checks/COMPort_Information.py", "instrument_checks/bench_scope_link.py",
    "instrument_checks/compare_scopes.py", "instrument_checks/dg535_check.py",
    "instrument_checks/dg535_check_full.py", "instrument_checks/find_scopes.py",
    "instrument_checks/laserCom_Info.py",
    "post_test_analysis/parse_test_log.py",
]

# Tkinter GUIs. Imported only where tkinter exists.
IMPORT_SAFE_TK = [
    "instrument_checks/numatogpio.py", "laser/cfr_laser_gui.py", "laser/laser_single_shot.py",
]

IMPORT_SCRIPT = textwrap.dedent("""
    import importlib.util, json, os, sys
    path = sys.argv[1]
    spec = importlib.util.spec_from_file_location("tool_under_test", path)
    m = importlib.util.module_from_spec(spec)
    sys.modules["tool_under_test"] = m
    spec.loader.exec_module(m)
    out = {k: getattr(m, k) for k in ("STORE", "CAL", "SAVED", "OUT_ROOT", "GUI_DIR",
                                       "REPO_ROOT") if isinstance(getattr(m, k, None), str)}
    print(json.dumps(out))
""")


def _env():
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", MPLBACKEND="Agg")
    env.pop("PYTHONPATH", None)
    return env


def _import(rel, tmp_path):
    r = subprocess.run([sys.executable, "-c", IMPORT_SCRIPT, str(TOOLS / rel)],
                       cwd=tmp_path, env=_env(), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"{rel}\n{r.stderr[-2000:]}"
    return json.loads(r.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("rel", IMPORT_SAFE)
def test_tool_imports_from_any_folder(rel, tmp_path):
    paths = _import(rel, tmp_path)
    for name, p in paths.items():
        p = Path(p).resolve()
        assert tmp_path not in p.parents, f"{rel}: {name} follows the working folder"
        assert REPO_ROOT in p.parents or p == REPO_ROOT, f"{rel}: {name} = {p}"
    assert not any(tmp_path.iterdir()), f"{rel} wrote files on import"


@pytest.mark.parametrize("rel", IMPORT_SAFE_TK)
def test_tk_tool_imports(rel, tmp_path):
    pytest.importorskip("tkinter")
    _import(rel, tmp_path)


def test_calibration_records_resolve():
    cal = TOOLS / "calibration"
    for name in ("timing_cal.json", "dg535_io.json", "laser_io.json",
                 "fiber_transit.json", "prep_cal_saved.json"):
        json.loads((cal / name).read_text())


def test_qsw_paths(tmp_path):
    paths = _import("calibration/qsw_spacing_test.py", tmp_path)
    assert Path(paths["REPO_ROOT"]) == REPO_ROOT
    assert Path(paths["GUI_DIR"]) == REPO_ROOT / "ScopeDelayGUI"
    assert Path(paths["OUT_ROOT"]) == REPO_ROOT / "data" / "qsw_test_results"


def test_edge_timing_values():
    sys.path.insert(0, str(TOOLS / "calibration"))
    try:
        import edge_timing as E
    finally:
        sys.path.remove(str(TOOLS / "calibration"))
    fit = E.fit_delay_sweep([1e-6, 2e-6, 3e-6, 4e-6], [1.1e-6, 2.1e-6, 3.12e-6, 4.1e-6])
    assert fit["slope"] == pytest.approx(1.002, rel=1e-12)
    assert fit["offset"] == pytest.approx(1e-7, rel=1e-9)
    assert fit["n"] == 4
    assert E.cable_delay(10.0) == pytest.approx(5.05e-8, rel=1e-12)


def test_ddot_analysis_shot43(tmp_path):
    if not NPZ.exists():
        pytest.skip("shot 43 record missing")
    r = subprocess.run([sys.executable, str(TOOLS / "analysis" / "ddot_analysis.py"),
                        str(NPZ), "--out", str(tmp_path / "plots")],
                       cwd=tmp_path, env=_env(), capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    out = r.stdout
    assert "tPulse 184.012 us, tEnd 185.682 us" in out
    for row in ("LTGS1-232  july      473.7   184.107   1.234   1.236     6.6    1.78      nan",
                "LTGS2-232  july      468.1   184.851   1.067   1.069    14.3   -2.35      nan",
                "LTGS1/LTGS2 ramp ratio, july: 1.156"):
        assert row in out, row
    assert (tmp_path / "plots" / "shot0043_ddot.png").exists()
