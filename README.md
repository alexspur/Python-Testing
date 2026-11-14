# LTGS Pulsed-Power Control and Shot Analysis

Control, data capture and shot analysis software for the laser-triggered gas
switch (LTGS) test stand at the Texas Tech Center for Pulsed Power and Power
Electronics (P3E), developed for pulse-forming line work with Los Alamos
National Laboratory.

The stand is a Marx-charged, water-dielectric pulse-forming line switched by
SF6-insulated laser-triggered gas switches. This repository holds the
operator GUI that runs a shot, the waveform pipeline that turns scope records
into calibrated voltages and pulse timing, and the bench tools used to
calibrate the timing chain.

## Capabilities

* **One-window shot control.** Delay generators, both CFR lasers, both WJ HV
  supplies, the charge and ground relays, Marx pressure and three scopes.
* **Shot logging.** A global shot number that never repeats, a full system
  snapshot per shot, per-session and master shot logs, and an Excel report
  per session.
* **Waveform capture.** Full-depth four-channel capture from three Rigol
  DS7000 scopes, with fast CSV export and peak-preserving plots.
* **Post-shot analysis.** D-dot and B-dot integration, RVM-referenced
  baseline correction, Q-switch timing and pulse spacing. Output is
  MATLAB-compatible `.mat` files plus figures.
* **Shot Replay.** Reruns the analysis on any recorded shot without touching
  instruments or production results.
* **Timing calibration tools.** Cable and fiber delays, DG535 and laser I/O
  delays, scope channel offsets and Q-switch spacing tests.

## Supported instruments

| Instrument | Role | Link |
| --- | --- | --- |
| BNC 575 pulse/delay generator | Master trigger | USB serial |
| SRS DG535 delay generator | Laser lamp and Q-switch timing | Prologix GPIB-USB |
| Rigol DS7000 / MSO7000 (×3) | RVM, D-dot, B-dot and Q-switch records | VISA over LAN |
| XP Glassman WJ 70-125 kV (×2) | Marx charging, negative and positive | USB / RS-232 |
| Quantel CFR lasers (×2) | Gas switch triggering | RS-232 over USB |
| Numato 4-channel USB relay | Charging and grounding relays | USB serial |
| Arduino Opta | Marx pressure monitor | Modbus TCP over fiber |

Details, default ports and addresses: [docs/instruments.md](docs/instruments.md).

## Installation

Python 3.11 or newer. Windows is the lab platform. The analysis and the tests
also run on Linux and macOS.

```
git clone https://github.com/alexspur/Python-Testing.git
cd Python-Testing
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # Linux / macOS
python -m pip install -r requirements.txt
```

For development and tests, install `requirements-dev.txt` instead.

Instrument access also needs the vendor drivers on the lab PC: a VISA
backend (NI-VISA or Keysight IO Libraries) for the scopes, and the USB serial
drivers for the Prologix adapter, the BNC 575 and the lasers.

## Running

| Task | Command (from the repository root) |
| --- | --- |
| Lab GUI | `python ScopeDelayGUI/main.py` |
| Shot Replay (no instruments) | `python ScopeDelayGUI/replay_main.py [logs_folder] [shot]` |
| WJ supply debug window | `cd ScopeDelayGUI` then `python wj_debug.py` |
| Process all shots | `cd ScopeDelayGUI` then `python -m analysis.process_shots ..\logs` |
| Process one session | `cd ScopeDelayGUI` then `python -m analysis.process_shots --session <dir>` |
| Export one shot to `.npz` | `python tools/analysis/export_shot.py --help` |
| D-dot study on a shot | `python tools/analysis/ddot_analysis.py data/shots/shot0043_raw.npz` |
| Timing calibration | `python tools/calibration/<script>.py --help` |

Before launching away from the lab, set every entry of `AUTO_CONNECT` in
`ScopeDelayGUI/main.py` to `False`. The GUI then opens without opening any
port.

> **Hardware warning.** The GUI and most scripts in `tools/` command real
> high-voltage and laser equipment. Read [tools/README.md](tools/README.md)
> before running a tool.

## Repository structure

```
ScopeDelayGUI/             the application
    main.py                lab GUI entry point and start-up settings
    replay_main.py         Shot Replay entry point
    gui/                   Qt windows and instrument panels
    instruments/           instrument drivers
    utils/                 workers, state, shot logging, export
    analysis/              waveform pipeline and replay
    tests/                 pytest suite (no hardware)
tools/
    calibration/           timing calibration suite and its records
    analysis/              offline shot export and D-dot study
    instrument_checks/     one-off instrument probes
    laser/                 standalone CFR laser GUIs
    post_test_analysis/    December 2025 report generators
matlab/                    MATLAB pipeline and post-test scripts
firmware/                  Arduino, Opta and Universal IO Hat firmware
data/                      experimental records kept in git
docs/                      documentation, manuals, GUI layout images
archive/                   backups, duplicates and third-party code
connection_memory.json     the GUI's remembered COM ports (lab PC)
logs/                      shot data written by the GUI (git-ignored)
```

## Waveform analysis pipeline

```
3 × Rigol CSV ─► scope_channels.wiring_for(shot) ─► pipeline.process_waveforms
                                                     ├─ detect pulse window
                                                     ├─ D-dot / B-dot integration
                                                     ├─ RVM divider and RVM-referenced correction
                                                     ├─ Q-switch timing
                                                     └─ peaks, gains, spacing
              ─► process_shots ─► processed_shots/shot_NNNN.mat, shot_summary.csv, figures
```

Channel assignments depend on the shot number. Shots 0 to 64 use the July
2026 wiring. Shots 65 onward use the November 2026 wiring. The full table,
the steps and the outputs are in
[docs/analysis_pipeline.md](docs/analysis_pipeline.md).

## Tests

```
python -m pip install -r requirements-dev.txt
python -m pytest
```

Set `QT_QPA_PLATFORM=offscreen` on a machine without a display. GitHub
Actions runs lint, a compile check and the full suite on Python 3.11 to 3.13
for every push and pull request. No test touches hardware.

A regression test runs real shot 43 through the pipeline and locks the
results, so any change to the processing math shows up. Four tests that
already failed before the cleanup are marked as known failures. See
[docs/testing.md](docs/testing.md).

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `ModuleNotFoundError: No module named 'gui'` | Start the GUI as `python ScopeDelayGUI/main.py`, or run Python from inside `ScopeDelayGUI/` |
| GUI starts shot numbers at 1 again | It was started from a copy in another folder. `logs/` lives at the repository root next to `connection_memory.json` |
| Instrument fails to connect | COM numbers move on Windows. Run `python tools/instrument_checks/COMPort_Information.py` and update the port in the panel. The GUI saves it to `connection_memory.json` |
| Scopes do not answer | Check the static IP on the scope network (192.168.10.x) and that a VISA backend is installed. `python tools/instrument_checks/find_scopes.py` scans the subnet |
| Opta pressure reads nothing | The PC NIC must be static on 192.168.10.0/24. Check `OPTA_HOST` in `main.py` |
| `pymodbus` keyword errors | Use pymodbus 3.6 to 3.x, as pinned in `requirements.txt` |
| Qt fails to start on Linux CI or SSH | `export QT_QPA_PLATFORM=offscreen` |
| A calibration script cannot find its records | Records live in `tools/calibration/`. The scripts find them by their own location |

## Documentation

* [docs/architecture.md](docs/architecture.md): how the GUI, drivers,
  workers, logging and analysis fit together
* [docs/analysis_pipeline.md](docs/analysis_pipeline.md): processing steps,
  wiring and outputs
* [docs/instruments.md](docs/instruments.md): instruments, transports and
  start-up settings
* [docs/testing.md](docs/testing.md): tests, known failures and the cleanup
  verification record
* [docs/repository_audit.md](docs/repository_audit.md): file status and the
  old-to-new path map
* [tools/README.md](tools/README.md), [data/README.md](data/README.md),
  [archive/README.md](archive/README.md)

## Contact

Ethan Spurbeck, Center for Pulsed Power and Power Electronics, Texas Tech
University.
