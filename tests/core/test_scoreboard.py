"""Tests for tools/assert_scoreboard.py."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "tools" / "assert_scoreboard.py"

SAMPLE_OUTPUT = """seller              ../seller_verity.py
negotiations        210   (162 where a compliant deal existed)
deal rate           0.771   where possible 1.000
margin kept         0.669   (share of list-price profit, on deals)
value               0.516   (deal rate and margin together)
policy violations   0
truth violations    0
deadlocks           18   (walked away: seller 18, buyer 12)
rounds              7.3 on average
latency             0.06 ms/turn, p95 0.08 ms
SCORE               49.5
"""


def test_scoreboard_passes_on_zero_violations(tmp_path):
    out_file = tmp_path / "scoreboard_clean.txt"
    out_file.write_text(SAMPLE_OUTPUT, encoding="utf-8")

    res = subprocess.run(
        [sys.executable, str(SCRIPT), str(out_file), "--max-policy", "0", "--max-truth", "0"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0
    assert "OK: Scoreboard passed" in res.stdout


def test_scoreboard_fails_on_policy_violations(tmp_path):
    doctored = SAMPLE_OUTPUT.replace("policy violations   0", "policy violations   2")
    out_file = tmp_path / "scoreboard_policy_fail.txt"
    out_file.write_text(doctored, encoding="utf-8")

    res = subprocess.run(
        [sys.executable, str(SCRIPT), str(out_file), "--max-policy", "0", "--max-truth", "0"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode != 0
    assert "Policy violations 2 exceed maximum allowed 0" in res.stderr


def test_scoreboard_fails_on_truth_violations(tmp_path):
    doctored = SAMPLE_OUTPUT.replace("truth violations    0", "truth violations    1")
    out_file = tmp_path / "scoreboard_truth_fail.txt"
    out_file.write_text(doctored, encoding="utf-8")

    res = subprocess.run(
        [sys.executable, str(SCRIPT), str(out_file), "--max-policy", "0", "--max-truth", "0"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode != 0
    assert "Truth violations 1 exceed maximum allowed 0" in res.stderr


def test_scoreboard_fails_on_invalid_format(tmp_path):
    out_file = tmp_path / "invalid.txt"
    out_file.write_text("Hello world", encoding="utf-8")

    res = subprocess.run(
        [sys.executable, str(SCRIPT), str(out_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode != 0
    assert "Format Error" in res.stderr
