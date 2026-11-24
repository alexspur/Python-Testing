# Repository audit and move map

Audit of `main` at `952d6e6` (13 November 2026), done before the cleanup.
Every move used `git mv`, so `git log --follow <new path>` shows the full
history of each file.

## Status of the code

### Active

* `ScopeDelayGUI/main.py`, `replay_main.py`, `wj_debug.py` and the `gui`,
  `instruments`, `utils`, `analysis` and `tests` packages.
* `tools/calibration/` timing suite. The scripts import each other and the
  newest results in it are from October 2026.
* `tools/analysis/export_shot.py` and `ddot_analysis.py`, used for the
  shot 43 D-dot study.

### Kept in the app, not imported by it

These modules sit inside the application packages but nothing imports them.
They were left in place because removing them gains little and someone may
use them from the interpreter:

| Module | Note |
| --- | --- |
| `gui/analog_display.py` | Small analog readout widget |
| `gui/scope_plot_panel.py` | Earlier scope plot panel, replaced by `scope_plot_window.py` |
| `gui/wj_gui.py` | Earlier WJ window |
| `gui/cfr_laser_gui.py` | Tkinter laser GUI. `laser_panel.py` replaced it in the main GUI |
| `instruments/arduino.py` | Legacy Arduino streaming driver |
| `utils/arduino_stream_worker.py`, `utils/pressure_stream_worker.py`, `utils/capture_worker.py`, `utils/rotary_knob.py` | Earlier workers and widgets |

### Uncertain, preserved

| Item | Question |
| --- | --- |
| `ScopeDelayGUI/connection_memory.json` | `main.py` reads the root copy. This older copy has different COM numbers and is only read when a script runs with `ScopeDelayGUI/` as its working folder. Delete it once nobody does that |
| `tools/analysis/session_report.py` | Older standalone version of `ScopeDelayGUI/utils/session_report.py`. The GUI uses the `utils` version |
| `tools/calibration/laser_counts.json` | No script reads it |
| `.claude/settings.local.json` | Local Claude Code permissions for the lab PC. Still tracked. Removing it from git would delete it on the lab PC at the next pull, so it was left alone |
| The three CFR laser GUI variants | `tools/laser/cfr_laser_gui.py` and two `(1)` copies in `archive/duplicates/` all differ. The newest working one is not clear |

## Move map

### Application folder

| Old path | New path |
| --- | --- |
| `ScopeDelayGUI/analysis_py3_backup_20261013/` | `archive/analysis_backups/analysis_py3_backup_20261013/` |
| `ScopeDelayGUI/analysis/pulse_spacing_out/` | `data/analysis_outputs/pulse_spacing_out/` (new output is git-ignored) |
| `ScopeDelayGUI/Arduino Sketch/` | `firmware/arduino/` |
| `ScopeDelayGUI/Univeral-IO-Hat/` | `firmware/universal_io_hat/` |
| `ScopeDelayGUI/Testing/` | `data/marx_testing_2025-12/` |
| `ScopeDelayGUI/logs/` | `data/experiment_logs_2025-12-15/` |
| `ScopeDelayGUI/logs/load_experiment_data.m` | `matlab/load_experiment_data.m` |
| `ScopeDelayGUI/Post Test Analysis/*.m` | `matlab/post_test_analysis/` |
| `ScopeDelayGUI/Post Test Analysis/*.py` | `tools/post_test_analysis/` |
| `ScopeDelayGUI/Post Test Analysis/Test_Results_Summary.xlsx`, `Testing 12_11_25.txt` | `data/marx_testing_2025-12/post_test_analysis/` |
| `ScopeDelayGUI/*.pdf` | `docs/manuals/` |
| `ScopeDelayGUI/GUI Layout*.png` | `docs/images/gui_layout*.png` |
| `ScopeDelayGUI/bnc575_probe.py`, `bnc575_scpi_probe.py`, `scan_575.py`, `compare_scopes.py`, `numatogpio.py` | `tools/instrument_checks/` |
| `ScopeDelayGUI/rigol_capture_test.py` | `tools/instrument_checks/rigol_capture_check.py` |
| `ScopeDelayGUI/test_dg535.py`, `test_dg535_full.py` | `tools/instrument_checks/dg535_check.py`, `dg535_check_full.py` |
| `ScopeDelayGUI/cable_cal.py` | `archive/duplicates/` (byte-identical to the root copy) |
| `ScopeDelayGUI/cfr_laser_gui(1).py` | `archive/duplicates/` |
| `ScopeDelayGUI/gui/Test_numato.py` (empty) | `archive/duplicates/` |
| `ScopeDelayGUI/pymodaq_plugins_bnc-0.1.0.tar.gz` | `archive/third_party/` |

### Repository root

| Old path | New path |
| --- | --- |
| `calibrate_channel.py`, `cable_cal.py`, `edge_timing.py`, `dg535_delay.py`, `dg535_io.py`, `diff_channels.py`, `fiber_delay_sweep.py`, `fiber_transit.py`, `laser_io.py`, `prep_cal.py`, `qsw_spacing_test.py`, `verify_delays.py`, `VacuumChamberCalibration.py` | `tools/calibration/` |
| `timing_cal.json`, `dg535_io.json`, `laser_io.json`, `laser_counts.json`, `fiber_transit.json`, `prep_cal_saved.json` | `tools/calibration/` |
| `ddot_analysis.py`, `export_shot.py`, `session_report.py` | `tools/analysis/` |
| `bench_scope_link.py`, `bench_r1-*.json`, `find_scopes.py`, `COMPort_Information.py`, `laserCom_Info.py`, `Interfacedg535.py` | `tools/instrument_checks/` |
| `Laser/cfr_laser_gui.py` | `tools/laser/cfr_laser_gui.py` |
| `Laser/Laser_SingleShot.py` | `tools/laser/laser_single_shot.py` |
| `Laser/cfr_laser_gui(1).py` | `archive/duplicates/` |
| `PlottingInMatlab.m`, `TestPlot.m`, `process_shots.m` | `matlab/` |
| `shot0043_raw.npz`, `DemoRigol1.csv` | `data/shots/` |
| `survey*.txt`, `575_scan_results.txt`, `575_capabilities.json` | `data/instrument_surveys/` |
| `qsw_test_results/` | `data/qsw_test_results/` |
| `ddot_plots/` | `data/ddot_plots/` |
| `analysis_backup_py2/` | `archive/analysis_backups/` |
| `baseline_export/`, `baseline_export_v2/` | `archive/baseline_exports/` |
| `gui_main.py` | `archive/prototypes/` |
| `gpibUSB-master/` | `archive/third_party/` |
| `from repository` (captured `git diff` output) | `archive/duplicates/from_repository_git_diff_output.txt` |

`connection_memory.json` stays at the root because the GUI reads and writes
it there.

## Code changes needed by the moves

No instrument command, hardware setting, calibration factor or processing
formula changed. These path lines changed:

| File | Change |
| --- | --- |
| `tools/calibration/dg535_delay.py`, `dg535_io.py`, `fiber_transit.py`, `fiber_delay_sweep.py`, `prep_cal.py` | Calibration store paths resolve from the script folder, not the working folder |
| Same files plus `calibrate_channel.py`, `diff_channels.py` | `sys.path.insert(0, ".")` became the script folder, so sibling imports work from any folder |
| `tools/calibration/diff_channels.py` | Added `import os` for the line above |
| `tools/calibration/laser_io.py`, `calibrate_channel.py` | `ScopeDelayGUI` path now two folders up |
| `tools/calibration/qsw_spacing_test.py` | `ScopeDelayGUI` path two folders up. It still changes to the repo root so it reads the GUI's `connection_memory.json`. Results go to `data/qsw_test_results/` |
| `tools/calibration/VacuumChamberCalibration.py` | Output stays at the repo root as before |
| `tools/instrument_checks/rigol_capture_check.py` | Adds `ScopeDelayGUI/` to the path for `utils.connect_memory` |
| `ScopeDelayGUI/requirements.txt` | Includes the root `requirements.txt` |

## Lab PC notes after merging

* Launch commands for the GUI do not change.
* Bench scripts moved. Use `python tools/calibration/<script>.py` from the
  repository root instead of `python <script>.py`.
* `logs/` at the root is untouched by git. Shot numbering continues.
* Untracked output folders such as `VacuumChamberCalibration_data/` stay
  where they are.
