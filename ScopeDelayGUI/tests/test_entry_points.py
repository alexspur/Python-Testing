"""The launch scripts import, and their settings stay consistent.

Nothing here constructs a window that connects to an instrument. main.py,
replay_main.py and wj_debug.py keep their start-up code under
`if __name__ == "__main__":`, so importing them only defines settings.
"""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_DIR.parent


def test_main_imports_and_settings():
    import main
    from gui.main_window import ScopeDelayMainWindow

    known = set(ScopeDelayMainWindow.DEFAULT_AUTO_CONNECT)
    assert set(main.AUTO_CONNECT) <= known, set(main.AUTO_CONNECT) - known
    assert main.OPTA_PORT == 502
    assert 0 < main.STARTUP_CHARGE_MA <= 6.0     # WJ supply limit noted in main.py
    assert main.PRESSURE_GAUGE_MIN_PSI < main.PRESSURE_GAUGE_MAX_PSI


def test_main_working_folder_is_repo_root():
    # main.py changes to the folder above itself so logs/ and the global shot
    # counter live at the repo root. That only holds while main.py stays one
    # level below the root, next to the GUI's connection_memory.json.
    import main
    assert Path(main.__file__).resolve().parent.parent == REPO_ROOT
    assert (REPO_ROOT / "connection_memory.json").is_file()


def test_replay_main_imports():
    import replay_main  # noqa: F401
    from gui.replay_window import ShotReplayWindow  # noqa: F401


def test_wj_debug_imports():
    import wj_debug
    assert callable(wj_debug.main)


def test_analysis_cli_entry():
    from analysis import process_shots
    assert callable(process_shots.main)
    assert process_shots.PIPELINE_VERSION
