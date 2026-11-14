# Pulsed Power Laboratory Instrumentation and Waveform Analysis

Python utilities for laboratory instrument control, oscilloscope acquisition, timing calibration, experiment logging, and double-pulse waveform analysis.

> **Research software:** This repository contains programs that can communicate with laboratory hardware, including high-voltage supplies and triggering equipment. Review instrument settings, interlocks, and laboratory procedures before connecting or operating hardware. Offline analysis and replay are recommended for development.

## Main application

`ScopeDelayGUI/` contains a PyQt6-based application for coordinating laboratory instruments, capturing oscilloscope data, logging shots, and reviewing results.

- `ScopeDelayGUI/main.py`: main GUI entry point
- `ScopeDelayGUI/replay_main.py`: replay entry point
- `ScopeDelayGUI/gui/`: interface panels and windows
- `ScopeDelayGUI/instruments/`: instrument interfaces (including Rigol, DG535, BNC575, CFR laser, WJ supply, Opta, and relay modules)
- `ScopeDelayGUI/analysis/`: waveform processing, plots, shot processing, channel assignments, and spacing analysis
- `ScopeDelayGUI/utils/`: capture workers, logging, state, reporting, and shared utilities
- `ScopeDelayGUI/tests/`: existing automated tests

The repository also contains standalone calibration, timing, acquisition, diagnostic, MATLAB, and historical analysis utilities. These remain in their original locations until import and file-path dependencies have been audited.

## Getting started (Windows)

Python and the appropriate instrument drivers must be installed. A supported Python version has not yet been formally pinned.

```powershell
git clone https://github.com/alexspur/Python-Testing.git
cd Python-Testing
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r ScopeDelayGUI/requirements.txt
```

To launch the main GUI from the repository root:

```powershell
python ScopeDelayGUI/main.py
```

**Hardware caution:** The GUI's current `AUTO_CONNECT` settings in `ScopeDelayGUI/main.py` default to enabled for multiple instruments. Review these settings and the connected equipment before launching on a laboratory control computer.

The application deliberately sets its working directory to the repository root at startup. Do not change this without auditing log paths, shot counters, and relative file references.

## Tests

The existing test suite is under `ScopeDelayGUI/tests/`. To run it after installing pytest:

```powershell
python -m pip install pytest
python -m pytest ScopeDelayGUI/tests
```

Some tests may require specific dependencies, fixtures, or a configured environment. A clean-machine, hardware-free test baseline has not yet been verified. Test results should be recorded before reorganizing code.

## Waveform processing

The analysis package includes shot-dependent scope channel assignments and probe calibration, D-dot/B-dot reconstruction, RVM analysis, Q-switch timing, and pulse-spacing measurements. See [waveform processing](docs/waveform-processing.md) and [repository migration plan](docs/reorganization-plan.md).

Do not change calibration constants, integration windows, shot mappings, or signal units as part of a purely structural cleanup. Compare representative shot outputs before and after any processing changes.

## Documentation

- [Architecture and reorganization plan](docs/reorganization-plan.md)
- [Hardware and safety notes](docs/hardware.md)
- [Waveform processing overview](docs/waveform-processing.md)
- [Development and verification](docs/development.md)
- [Existing experiment log format](ScopeDelayGUI/logs/README.md)

## Project status

This is an actively developed research repository, not a packaged or safety-certified instrument control product. Historical backups, datasets, and experiment logs are retained pending a dependency and data-retention review.

No license has been specified in the repository documentation. Do not assume redistribution rights for included third-party manuals, archives, or software.
