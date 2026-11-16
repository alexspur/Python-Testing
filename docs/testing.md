# Testing

## Running the tests

```
python -m pip install -r requirements-dev.txt
python -m pytest
```

Run from the repository root. `pyproject.toml` limits collection to
`ScopeDelayGUI/tests` and adds `ScopeDelayGUI/` to the import path.

On a machine without a display, set `QT_QPA_PLATFORM=offscreen` first.
CI does this for you.

Useful subsets:

```
python -m pytest ScopeDelayGUI/tests/test_shot43_regression.py   real-shot regression
python -m pytest ScopeDelayGUI/tests/test_calibration_constants.py
python -m pytest -k "not shot_logging"                            skip the slow GUI tests
ruff check .                                                     error-only lint
```

No test opens a serial port, a VISA resource or a Modbus connection. The GUI
tests build the main window with every auto-connect flag off and replace
instruments with fakes.

## What the suite covers

| File | Covers |
| --- | --- |
| `test_analysis.py` | Pipeline helpers, session discovery, statuses, `.mat` and summary output on synthetic shots |
| `test_replay.py` | Shot Replay indexing and sandboxed reruns |
| `test_shot43_regression.py` | Real shot 43 through the pipeline, values locked to main `952d6e6` |
| `test_calibration_constants.py` | Probe factors, B-dot geometry, shot-dependent channel assignments |
| `test_shot_logging.py` | Main window, shot numbering, shot rows, panels, workers |
| `test_session_report.py` | Session Excel workbook |
| `test_relay_modes.py`, `test_relay_control.py` | GROUND / FLOAT / CHARGE logic and relay commands |
| `test_downsample.py`, `test_plot_window.py` | Plot downsampling and scope plot window |
| `test_analysis_gui.py` | Analysis runner and analysis window |
| `test_entry_points.py` | `main.py`, `replay_main.py`, `wj_debug.py` and the analysis CLI |
| `test_tools.py` | Tools import from any folder, stores resolve, `edge_timing` and `ddot_analysis` results |

## Known failures

Four tests already failed on `main` at `952d6e6`, before the cleanup.
`tests/conftest.py` marks them `xfail` with a reason. They need a decision
from the researcher, not a code cleanup:

| Test | Failure | Likely cause |
| --- | --- | --- |
| `test_analysis.py::test_late_scope3_record_skips_c225_c315_not_the_shot` | `KeyError: 'c225_gap_ns'` | Test expects summary columns that `SUMMARY_COLS` does not have |
| `test_analysis.py::test_output_probe_edges_saved` | `KeyError: 'edges'` | Test expects an `edges` record the pipeline does not save |
| `test_replay.py::test_cal_override_applies_to_one_run_only` | `KeyError: 'DIV_CH1'` | Test overrides a `CAL` key that no longer exists |
| `test_shot_logging.py::TestSimplifiedPanels::test_instrument_panels_fit_without_scrolling` | 1016 px > 1010 px | Pixel budget depends on installed fonts. May pass on the lab PC |

The first three look like tests written ahead of, or behind, a pipeline
change. Either the pipeline gains those outputs or the tests drop them. When
one is fixed, remove it from `KNOWN_FAILURES`. The `strict=True` marks make
CI fail if a test starts passing while still listed.

## Cleanup verification record

The repository cleanup (branch `cleanup/repo-reorganization`) was checked
against `main` at `952d6e6` like this:

1. **Test baseline.** Full suite on `main`: 326 passed, 4 failed (the table
   above). After the cleanup the same 330 tests give the same pass/fail
   result. 52 tests were added (382 in total). Three of them skip when
   Tkinter is missing.
2. **Pipeline outputs.** A snapshot script ran the pipeline before and after
   the moves and hashed every output array (rounded to 1e-9) and every
   scalar:
   * real shot 43 under the shot-43 wiring and under every `WIRINGS` entry,
   * a synthetic session through `process_shots.run()`: statuses, the
     summary CSV and every field of every `.mat` file,
   * `wiring_for()` for shots 0 to 399, `PROBES`, `WIRINGS` and `CAL`.

   Result: identical.
3. **Bench tool outputs.** `ddot_analysis.py` on shot 43 (printed table and
   summary CSV) and `edge_timing` on all twelve shot 43 channels: identical
   before and after.
4. **Imports.** All 56 application modules import headless.
   `gui/cfr_laser_gui.py` needs Tkinter, which the CI image may lack. Every
   import-safe tool imports from an unrelated working folder.

The December 2025 Rigol CSVs in `data/marx_testing_2025-12/` hold only two
channels per scope. The current pipeline rejects them before and after the
cleanup in the same way, so they serve as a record, not as a regression
input.

## Not testable without hardware

See the list at the end of [instruments.md](instruments.md).
