"""phases.md Phase 10's headline acceptance criterion: `make demo` produces identical output on
three consecutive runs (plan.md #21's determinism rule -- "It must produce identical output every
time. Never demo against a live model call.").

This runs the demo as a real subprocess three times, exactly as `make demo` would, rather than
calling `main()` in-process -- an in-process check could pass while the actual shipped command
differed, which is precisely the failure this criterion exists to catch on submission day.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_demo() -> str:
    result = subprocess.run(
        [sys.executable, "-m", "ledgerguard.demo"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, f"make demo failed:\n{result.stdout}\n{result.stderr}"
    return result.stdout


def test_three_consecutive_demo_runs_are_byte_identical():
    first, second, third = _run_demo(), _run_demo(), _run_demo()
    assert first == second
    assert second == third


def test_demo_shows_the_twin_case_refused_with_distinct_reason_codes():
    """The cold open's whole point (plan.md #21): both twins refused, told apart by reason code.
    Pinned here so a future change that silently auto-posts either one fails the suite rather
    than only being noticed while recording the video.
    """
    output = _run_demo()

    assert "DUPLICATE_UTR" in output
    assert "GENUINE_DOUBLE_SETTLEMENT" in output
    # Neither twin may ever appear as an auto-post; both must be flagged.
    assert output.count("FLAG_ANOMALY  DUPLICATE_UTR") == 1
    assert output.count("FLAG_ANOMALY  GENUINE_DOUBLE_SETTLEMENT") == 1


def test_demo_reports_the_negative_ablation_result_rather_than_burying_it():
    """PREREGISTRATION.md binds the demo to the same language the ablation's outcome band
    permits -- the demo must not quietly upgrade a NEGATIVE result into a claim.
    """
    output = _run_demo()
    assert "NEGATIVE" in output
    assert "negative result" in output
