# Waveform analysis pipeline

The pipeline turns the three Rigol scope records of one shot into calibrated
traces, peaks and pulse spacing. It is a line-for-line Python port of
`process_waveforms()` in `matlab/process_shots.m` (the July 2026 pipeline).
The output `.mat` files keep the MATLAB struct layout, so `ltgs_gui3.m` still
opens them.

Code: `ScopeDelayGUI/analysis/`. Version tag: `PIPELINE_VERSION` in
`process_shots.py`. Shots processed by an older version are redone
automatically on the next run.

## Inputs

For each shot, one CSV per scope: time plus four channels. Session folders
look like this:

```
logs/<date>/experiment_log_<ts>/
    shot_log_<ts>.csv        one row per shot, with the three file names
    rigol1_<ts>[_shotNN].csv
    rigol2_<ts>[_shotNN].csv
    rigol3_<ts>[_shotNN].csv
```

## Channel assignment by shot number

`analysis/scope_channels.py` is the only place the wiring is written down.
Each entry of `WIRINGS` applies from its `from_shot` onward. Older shots keep
their wiring, so they reprocess the same way.

| Signal | Shots 0 to 64 | Shots 65 onward |
| --- | --- | --- |
| RVM1, RVM2 | scope 1, CH1 and CH2 | same |
| TrigMon, TrigOut | scope 1, CH3 and CH4 | same |
| LTGS2 D-dot | scope 2, CH1 | same |
| LTGS2 B-dot | scope 2, CH2 | not recorded |
| LTGS1 D-dot | scope 2, CH3 | same |
| LTGS1 B-dot | scope 2, CH4 | not recorded |
| A225 D-dot | not recorded | scope 2, CH4 |
| Q-switch 1, 2 | scope 3, CH1 and CH2 | not recorded |
| C315 B-dot | scope 3, CH3 | not recorded |
| B225 D-dot | not recorded | scope 3, CH3 |
| C225 D-dot | scope 3, CH4 | same |

Probe calibration factors (`PROBES`) come from the 2019 L-3 certificates.
`tests/test_calibration_constants.py` locks both tables. When cables move,
append a new `WIRINGS` entry. Do not edit an old one.

## Processing steps (`pipeline.process_waveforms`)

1. **Detection.** `detect_activity` finds the pulse window on the anchor
   channels. A shot with no activity raises `NoPulse` (dry shot).
2. **Windows.** Pre-pulse and post-pulse baseline windows are set around
   `tPulse` and `tEnd`.
3. **LTGS D-dots.** Offset removed, integrated with the probe factor, in kV.
4. **LTGS B-dots.** Offset removed, integrated with factor × `geom` ×
   `bScale`, in Z·I kV. Baseline fitted on quiet windows next to the pulse
   (`reconstruct_bdot`).
5. **Output probes.** C225 and the other 225 D-dots use `reconstruct_ddot`
   (ramped offset plus cubic baseline). C315 uses the B-dot path.
6. **Q-switch monitors.** Gated raw volts. `t_Qsw1` and `t_Qsw2` are the
   rise times.
7. **RVMs.** Divider-corrected and trimmed to the analysis span.
8. **RVM-referenced D-dot correction.** The D-dot baselines are corrected
   against the RVMs. The 2×2 gain matrix `G` and `G_consistency` record how
   well the two references agree.
9. **Peaks.** Collected in `S["peaks"]`.

Measured spacing:

* `spacing_from_rvm`: time between the two RVM collapse edges at half
  minimum, in ns.
* `spacing_from_qsw`: laser 2 Q-switch rise minus laser 1 rise, in ns.
* `pulse_spacing.py`: output pulse spacing on C225 at any edge level, rise
  to rise and fall to rise.

## Outputs

```
logs/processed_shots/shot_NNNN.mat     MATLAB struct S per shot
logs/processed_shots/shot_summary.csv  one row per shot (SUMMARY_COLS)
logs/processed_shots/summary.png       peaks and spacing over all shots
<session>/shot_NNNN_analysis.png       four-panel figure, fired shots
<session>/shot_NNNN_raw.png            all 12 channels
```

## Running it

From the `ScopeDelayGUI/` folder:

```
python -m analysis.process_shots                  all sessions under ./logs
python -m analysis.process_shots D:\data\logs     all sessions under a folder
python -m analysis.process_shots --session <dir>  one session
python -m analysis.process_shots --session <dir> --shot 18 --force
```

The GUI runs the same command after each shot through
`utils/analysis_runner.py`.

## Replay

`python ScopeDelayGUI/replay_main.py [logs_root] [shot]` opens Shot Replay.
It loads a recorded shot and reruns the analysis into
`ScopeDelayGUI/replay_output/`. It never writes to the session folders or to
`processed_shots`.

## Regression guard

`tests/test_shot43_regression.py` runs the pipeline on the real shot 43
record (`data/shots/shot0043_raw.npz`) and checks the peaks, RVM gains,
Q-switch times and both spacing estimates to a relative 1e-9. Any change
to the processing mathematics fails this test. When the change is intended,
bump `PIPELINE_VERSION` and update the expected values in the same commit.
