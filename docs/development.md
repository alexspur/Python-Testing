# Development and verification

## Environment

From the repository root on Windows:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r ScopeDelayGUI/requirements.txt
python -m pip install pytest
```

The current requirements include PyQt6, pyqtgraph, pyserial, pyvisa, numpy, pandas, pymodbus, openpyxl, scipy, and matplotlib. Driver backends and additional dependencies may be required for real hardware. Python version compatibility and reproducible dependency pins remain to be verified.

## Launch

```powershell
python ScopeDelayGUI/main.py
```

Review `AUTO_CONNECT` in `ScopeDelayGUI/main.py` first: it currently enables automatic connections to several instruments. Run on an appropriate control computer only when safe.

## Test baseline

```powershell
python -m pytest ScopeDelayGUI/tests -q
```

The command is documented but has **not** been run as part of this documentation-only cleanup. Classify tests as hardware-free, mocked-hardware, or hardware-in-the-loop before enabling automated CI.

## Code change rules

1. Use a feature branch and keep commits narrowly scoped.
2. Preserve units and calibration provenance in analysis changes.
3. Avoid changing import paths, working directories, and output paths without tests.
4. Compare numerical results from representative shots before merging waveform changes.
5. Keep captured data and logs separate from source code, without deleting historical records.
6. Never run hardware-control tests unattended.

## Follow-up work

Audit import paths, verify replay entry points, establish known-good shot fixtures, document platform-specific VISA backends, and create a hardware-free CI job once tests have been classified.
