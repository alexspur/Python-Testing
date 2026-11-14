# Safe repository reorganization plan

Status: **planning only**. No executable modules or measurement files should be moved until the baseline is tested.

## Current architecture

The primary application lives in `ScopeDelayGUI/` and has distinct `gui/`, `instruments/`, `analysis/`, `utils/`, and `tests/` packages. Its `main.py` imports `gui.main_window` and changes the working directory to the repository root before creating the GUI. These details make an immediate package rename or directory move risky.

## Phases

1. **Establish a baseline:** record the main commit SHA; run pytest and offline replay; record known failures; save representative processed shot outputs and expected numerical values.
2. **Documentation and hygiene:** add root README and developer documentation; audit existing ignore rules; identify generated data and local configuration files. Do not remove tracked measurement records solely because they match ignore patterns.
3. **Dependency audit:** enumerate static and dynamic imports, module execution, subprocess commands, configuration lookups, file paths, working-directory assumptions, MATLAB references, and tests importing historical code.
4. **Standalone tool migration:** consider `tools/calibration/`, `tools/timing/`, `tools/diagnostics/`, and `tools/acquisition/`. Move one tool at a time, update callers, and test after each change.
5. **Historical material:** review `analysis_backup_py2/`, `ScopeDelayGUI/analysis_py3_backup_20261013/`, `baseline_export/`, `baseline_export_v2/`, and `qsw_test_results/`. Archive only after checking callers and confirming data retention.
6. **Optional packaging:** consider a stable installable package and CLI entry points with compatibility wrappers. Preserve existing entry points until validated.
7. **Release gate:** test offline analysis and GUI startup; compare numerical shot outputs; verify live instrument workflows under approved laboratory procedures; merge only after review.

## Proposed top-level layout

```text
README.md
pyproject.toml              # future, after packaging/dependency audit
.github/workflows/          # future, after hardware-free tests are isolated
ScopeDelayGUI/              # preserve current working application
tools/                      # future standalone utilities
docs/
examples/                   # future sanitized fixtures
archive/                    # future historical implementations
matlab/                     # future MATLAB references
```

## Specific risks to verify

- `ScopeDelayGUI/main.py` currently sets the process working directory to the repository root for logs and shot counters.
- `ScopeDelayGUI/analysis/pipeline.py` depends on `scope_channels.py` for shot-specific channel mappings and calibrations.
- Relative paths may be used by GUI resources, test fixtures, JSON configurations, CSV exports, and MATLAB scripts.
- Backup code and old exports may be imported by tests or used as comparison references.
- Instrument communication must not run during automated CI tests unless explicitly mocked.
- Existing experiment logs and calibration files may have scientific retention value.

## Acceptance criteria

- Existing tests are green or all pre-existing failures are documented.
- Offline GUI/replay entry points continue to import and launch.
- No unapproved instrument connections occur in automated tests.
- Shot channel mappings, calibration constants, units, D-dot/B-dot baselines, RVM and Q-switch timing, and exported fields are preserved.
- Representative shot results agree within explicit tolerances.
- Output directories, shot counters, and experiment logs remain consistent.
- Historical records are retained or archived with provenance.

Do not delete or rewrite original experimental data as part of the cleanup.
