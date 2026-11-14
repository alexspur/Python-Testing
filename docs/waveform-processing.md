# Double-pulse waveform processing

The `ScopeDelayGUI/analysis/` package contains waveform processing, plotting, shot processing, scope channel assignments, and pulse spacing utilities.

## Inputs and outputs

The pipeline's documented Rigol input format is a time column in seconds followed by four scope channels in volts. Its processed time axes are expressed in microseconds relative to pulse 1, reconstructed voltages in kV, and Q-switch monitor signals in volts.

## Processing stages

1. Load Rigol waveform files and select shot-specific wiring/calibration definitions from `scope_channels.py`.
2. Detect pulse activity and establish pulse timing.
3. Apply baseline/offset corrections and integrate D-dot and B-dot signals.
4. Reconstruct output probes using probe-type-specific methods and calibration factors.
5. Gate Q-switch monitors and derive timing.
6. Process RVM signals and apply reference-based D-dot baseline corrections.
7. Calculate peak and pulse-spacing metrics.

The current pipeline contains local pre/post-pulse baseline logic for B-dot signals and a cubic-fit baseline correction for output D-dot signals. Historical MATLAB and Python implementations remain valuable regression references.

## Scientific validation

A structural cleanup must not silently change calibration factors, baseline windows, channel mapping, peak definitions, time alignment, or sign conventions. Before modifying the processing algorithms, compare representative shots, including pulse peaks, baseline levels, rise times, Q-switch spacing, and RVM spacing, using explicit tolerances.

See `ScopeDelayGUI/analysis/pipeline.py`, `ScopeDelayGUI/analysis/process_shots.py`, and `ScopeDelayGUI/analysis/scope_channels.py` for implementation details.
