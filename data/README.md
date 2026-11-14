# Data

Experimental records kept in the repository. These files are research data.
Do not edit or delete them. New shot data from the GUI goes to the `logs/`
folder at the repository root, which git ignores.

| Path | Contents | Source |
| --- | --- | --- |
| `marx_testing_2025-12/` | Marx and trigger-generator test sessions from 10 to 14 December 2025: two-channel Rigol CSV exports, experiment logs and handwritten test notes | Formerly `ScopeDelayGUI/Testing/` |
| `marx_testing_2025-12/post_test_analysis/` | `Test_Results_Summary.xlsx` and the 12 December 2025 test notes | Formerly `ScopeDelayGUI/Post Test Analysis/` |
| `experiment_logs_2025-12-15/` | GUI event logs from 15 December 2025, with a README that explains the log columns | Formerly `ScopeDelayGUI/logs/` |
| `shots/shot0043_raw.npz` | Raw three-scope record of shot 43, written by `tools/analysis/export_shot.py` | Formerly at the root |
| `shots/DemoRigol1.csv` | Four-channel Rigol demo export | Formerly at the root |
| `qsw_test_results/` | Q-switch spacing test runs from 16 October 2026 (`run.log`, `settings.json`, plots) | Written by `tools/calibration/qsw_spacing_test.py` |
| `ddot_plots/` | D-dot analysis plots for shot 43 | Written by `tools/analysis/ddot_analysis.py` |
| `analysis_outputs/pulse_spacing_out/` | Pulse-spacing figures for shots 43 to 46 | Written by `ScopeDelayGUI/analysis/pulse_spacing.py` |
| `instrument_surveys/` | BNC 575 capability scan and network or bench survey results | Written by the instrument check scripts |

Calibration records written by the bench tools (for example `timing_cal.json`)
stay next to the tools that read them, in `tools/calibration/`.

## Format notes

The December 2025 Rigol CSVs hold time plus two channels. The current
analysis pipeline expects time plus four channels per scope, so it does not
reprocess these files. They are kept as the record of those tests.
