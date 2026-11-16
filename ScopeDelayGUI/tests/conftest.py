"""Shared pytest settings.

KNOWN_FAILURES lists tests that already failed on main at commit 952d6e6,
before the repository cleanup. They are marked xfail so CI stays useful
while the cause is decided. They are not fixed here, because fixing them
means changing either the analysis output or the test's expectation, and
that is a research decision. See docs/testing.md.

strict=True means CI turns red if one of them starts passing, as a reminder
to remove it from this list.
"""

import pytest

KNOWN_FAILURES = {
    # The test expects c225_gap_ns / c315_gap_ns summary columns that
    # process_shots.SUMMARY_COLS does not write.
    "tests/test_analysis.py::test_late_scope3_record_skips_c225_c315_not_the_shot":
        ("summary has no c225_gap_ns column", True),
    # The test expects an 'edges' record in the saved .mat that the pipeline
    # does not produce.
    "tests/test_analysis.py::test_output_probe_edges_saved":
        ("saved struct has no 'edges' field", True),
    # The test sets a DIV_CH1 calibration override that pipeline.CAL does
    # not define.
    "tests/test_replay.py::test_cal_override_applies_to_one_run_only":
        ("CAL has no DIV_CH1 key", True),
    # Pixel budget. Depends on the fonts installed (Times New Roman on the
    # lab PC), so it can pass on Windows and fail on Linux.
    "tests/test_shot_logging.py::TestSimplifiedPanels::test_instrument_panels_fit_without_scrolling":
        ("panel height depends on installed fonts", False),
}


def pytest_collection_modifyitems(config, items):
    for item in items:
        for nodeid, (reason, strict) in KNOWN_FAILURES.items():
            if item.nodeid.endswith(nodeid):
                item.add_marker(pytest.mark.xfail(
                    reason=f"known failure on main 952d6e6: {reason}", strict=strict))
