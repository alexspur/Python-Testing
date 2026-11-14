# Application architecture

ScopeDelayGUI is a PyQt6 desktop application. It runs one shot of the
Marx-charged, water-dielectric pulse-forming line with laser-triggered gas
switches (LTGS). It sets up the delay generators, the lasers, the high-voltage
supplies and the scopes. It fires the shot, captures the three scopes, logs
the full system state and starts the post-shot analysis.

## Layers

```
ScopeDelayGUI/
  main.py            lab GUI entry point and start-up settings
  replay_main.py     offline Shot Replay entry point (no instruments)
  wj_debug.py        stand-alone WJ supply debug window
  gui/               Qt windows and panels
  instruments/       hardware drivers (serial, GPIB over Prologix, VISA, Modbus)
  utils/             workers, logging, state, export, small widgets
  analysis/          waveform processing, .mat export, replay helpers
  tests/             pytest suite (no hardware)
```

The packages import each other by top-level name (`from utils.status_lamp
import StatusLamp`). The `ScopeDelayGUI/` folder must therefore be on
`sys.path`. Running `python ScopeDelayGUI/main.py` puts it there. The pytest
configuration adds it too.

### gui/

`main_window.ScopeDelayMainWindow` owns every panel and every worker thread.
Each instrument has a panel:

| Panel | Instrument |
| --- | --- |
| `bnc575_panel` | BNC 575 pulse/delay generator (master trigger) |
| `dg535_panel` | SRS DG535 delay generator (laser timing) |
| `laser_panel` | Two Quantel CFR lasers, INT/INT or EXT/EXT |
| `rigol_panel`, `scope_plot_window`, `scope_screen` | Three Rigol DS7000 scopes |
| `wj_panel`, `wj_plot_window`, `wj_debug_window` | Two XP Glassman WJ HV supplies |
| `numato_relay_panel` | Charging and grounding relays |
| `sf6_panel`, `sf6_window`, `gauge_widget` | Opta pressure monitor and Marx pressure gauge |
| `analysis_window` | Post-shot analysis figures |
| `replay_window`, `replay_figures` | Shot Replay (offline) |

`analog_display.py`, `scope_plot_panel.py` and `wj_gui.py` are not imported
by the application. They are kept because they may be used from the
interpreter. See [repository_audit.md](repository_audit.md).

### instruments/

One driver per instrument. Drivers do I/O only. They do not import from
`utils` or `gui`. See [instruments.md](instruments.md) for transports and
defaults.

### utils/

| Module | Role |
| --- | --- |
| `system_state` | One thread-safe record of every instrument's state |
| `shot_snapshot` | Turns a frozen state copy into one shot row (pure data) |
| `shot_logger` | Global shot counter, per-session and master shot logs |
| `data_logger` | Event log (`experiment_log_<ts>.csv`) and session folders |
| `session_report` | Excel workbook per session, built from the logs |
| `capture_single_worker` | Background scope capture (full memory depth) |
| `csv_export_worker` | Fast background CSV export of captured waveforms |
| `downsample` | Peak-preserving min/max downsampling for plotting |
| `pressure_worker` | Polls the Opta over Modbus TCP on its own QThread |
| `relay_modes` | GROUND / FLOAT / CHARGE relay logic (pure logic) |
| `connect_memory` | Remembered COM ports and scope VISA resources |
| `analysis_runner` | Runs `python -m analysis` in a child QProcess |

### analysis/

| Module | Role |
| --- | --- |
| `scope_channels` | The only record of which probe sits on which scope channel, by shot number, with calibration factors |
| `pipeline` | `process_waveforms()`: D-dot, B-dot, RVM, Q-switch processing (Python port of the MATLAB July pipeline) |
| `process_shots` | Finds sessions, processes shots, writes `processed_shots/shot_NNNN.mat`, `shot_summary.csv` and plots |
| `plots` | Per-shot and summary figures |
| `replay` | Offline shot index and sandboxed reprocessing for Shot Replay |
| `pulse_spacing` | Output pulse spacing on C225 at any edge level |

See [analysis_pipeline.md](analysis_pipeline.md).

## Working folder and data locations

`main.py` changes the working folder to the repository root before it builds
the window. Everything the GUI writes is relative to that folder:

| Path (repo root) | Written by | In git |
| --- | --- | --- |
| `connection_memory.json` | `utils/connect_memory.py` | Yes, it records the lab PC's COM ports |
| `logs/<date>/experiment_log_<ts>/` | `utils/data_logger.py` | No |
| `logs/shot_counter.json`, `logs/shot_log_master.csv` | `utils/shot_logger.py` | No |
| `logs/processed_shots/` | `analysis/process_shots.py` | No |
| `ScopeDelayGUI/replay_output/` | Shot Replay | No |

`main.py` must stay one folder below the repository root. A test checks this.

## One shot, end to end

1. The operator sets delays, charge voltage and lasers in the panels.
2. The BNC 575 fires. `shot_logger` claims the next global shot number
   right after the trigger command returns.
3. `capture_single_worker` reads each scope. `csv_export_worker` writes
   `rigol<k>_<ts>.csv` into the session folder.
4. `system_state` is copied under its lock. `shot_snapshot` turns the copy
   into a row. `shot_logger` appends it to the session and master shot logs.
5. `analysis_runner` starts `python -m analysis` with the session. The
   pipeline writes `shot_NNNN.mat` and figures. `analysis_window` shows them.
6. On close, `session_report` writes the session workbook.

## Safety properties

* No instrument connects unless its `AUTO_CONNECT` flag in `main.py` is on
  or the operator presses Connect.
* The Rigol driver keeps a list of query-only SCPI commands. The test suite
  checks that every entry ends in `?`.
* The tests build the main window with every auto-connect flag off and
  replace hardware with fakes. CI never touches a port.
