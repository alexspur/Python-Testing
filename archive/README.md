# Archive

Historical, duplicate and third-party files kept for reference. Nothing in
this folder is imported by the ScopeDelayGUI application or by the tools.
Files were moved here with `git mv`, so `git log --follow <file>` still shows
their full history.

| Path | What it is | Why it is here |
| --- | --- | --- |
| `analysis_backups/analysis_backup_py2/` | Earlier Python port of the shot analysis, with its session PNGs and summary cache | Superseded by `ScopeDelayGUI/analysis/` |
| `analysis_backups/analysis_py3_backup_20261013/` | Snapshot of `ScopeDelayGUI/analysis/` taken 2026-10-13 | Superseded by the current package |
| `baseline_exports/baseline_export/` | Before/after export used to check the C225 rework, with frozen source copies | Historical verification record |
| `baseline_exports/baseline_export_v2/` | Second before/after export (`checks.json`, `what_changed.txt`) | Historical verification record |
| `duplicates/Laser_cfr_laser_gui(1).py` | Download copy of the CFR laser GUI | Differs from `tools/laser/cfr_laser_gui.py`, kept in case it holds needed changes |
| `duplicates/ScopeDelayGUI_cfr_laser_gui(1).py` | A third CFR laser GUI variant | Same reason |
| `duplicates/ScopeDelayGUI_cable_cal.py` | Byte-identical copy of `tools/calibration/cable_cal.py` | Exact duplicate |
| `duplicates/gui_Test_numato_empty.py` | Empty file from `ScopeDelayGUI/gui/` | Empty, unused |
| `duplicates/from_repository_git_diff_output.txt` | Captured `git diff --stat` output saved by accident as a file | Not code or data |
| `prototypes/gui_main.py` | First single-file mock-up of the Scope + Delay + SF6 GUI | Replaced by `ScopeDelayGUI/main.py` |
| `third_party/gpibUSB-master/` | Vendored copy of the gpibUSB project (DG535, BNC577, DS345 drivers) | Third-party reference code, not used by the app |
| `third_party/pymodaq_plugins_bnc-0.1.0.tar.gz` | PyMoDAQ BNC plugin source archive | Third-party reference code, not used by the app |

If something here turns out to be needed, move it back with `git mv`.
