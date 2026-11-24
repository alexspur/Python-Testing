# Tools

Standalone scripts that sit beside the ScopeDelayGUI application. Most of
them talk to laboratory hardware. Read a script's docstring before you run
it.

> **Hardware warning.** Scripts in `calibration/`, `instrument_checks/` and
> `laser/` open serial, GPIB, VISA or Modbus connections. Some fire the
> BNC 575, arm scopes or prep the CFR lasers. Run them only on the lab PC
> with the system in a safe state.

## Folders

| Folder | Purpose | Talks to hardware |
| --- | --- | --- |
| `calibration/` | Timing calibration suite: cable and fiber delays, DG535 and laser I/O delays, scope channel offsets, Q-switch spacing tests. The scripts import each other (`edge_timing`, `calibrate_channel`, `cable_cal`) and keep their calibration records (`*.json`) in this folder. | Yes, except `edge_timing.py` and `cable_cal.py` |
| `analysis/` | Offline analysis of saved shots: `export_shot.py` (shot to `.npz`), `ddot_analysis.py` (D-dot study), `session_report.py` (older standalone session report, see note) | No |
| `instrument_checks/` | One-off probes and bench checks for the BNC 575, DG535, Rigol scopes, Numato relay and COM ports | Yes, except `find_scopes.py` which only scans the network |
| `laser/` | Standalone Tkinter GUIs for the Quantel CFR lasers | Yes |
| `post_test_analysis/` | Turns December 2025 test notes into Excel and PowerPoint summaries | No |

## Running

Run any tool from the repository root:

```
python tools/calibration/edge_timing.py
python tools/analysis/ddot_analysis.py data/shots/shot0043_raw.npz
python tools/calibration/dg535_io.py --help
```

Each calibration script finds its sibling modules and its `*.json` records
by its own location, so the current folder does not matter for those.
Scripts that read `connection_memory.json` through the GUI's
`utils.connect_memory` (`qsw_spacing_test.py` and
`instrument_checks/rigol_capture_check.py`) must start from the repository
root, where the GUI keeps that file. `qsw_spacing_test.py` changes to the
repository root on its own.

## Import safety

These scripts run hardware code at import time, so never import them from
tests or CI: `instrument_checks/rigol_capture_check.py`,
`instrument_checks/scan_575.py`, `instrument_checks/bnc575_probe.py`,
`instrument_checks/bnc575_scpi_probe.py`, `instrument_checks/Interfacedg535.py`
and `post_test_analysis/create_powerpoint.py`. Every other script keeps its
work under `if __name__ == "__main__":`.

## Renamed files

| Old path | New path | Reason |
| --- | --- | --- |
| `ScopeDelayGUI/test_dg535.py` | `instrument_checks/dg535_check.py` | A `test_` name let pytest collect a script that opens COM4 |
| `ScopeDelayGUI/test_dg535_full.py` | `instrument_checks/dg535_check_full.py` | Same |
| `ScopeDelayGUI/rigol_capture_test.py` | `instrument_checks/rigol_capture_check.py` | A `_test` name let pytest collect a script that arms the scopes on import |
| `Laser/Laser_SingleShot.py` | `laser/laser_single_shot.py` | Naming consistency |

`calibration/qsw_spacing_test.py` keeps its name because lab notes refer to
it. The pytest configuration in `pyproject.toml` restricts collection to
`ScopeDelayGUI/tests`, so pytest never imports it.

## Records without a known reader

`calibration/laser_counts.json` is not read by any script in this
repository. It is kept as a record.
