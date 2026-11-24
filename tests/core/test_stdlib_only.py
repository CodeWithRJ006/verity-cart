"""Tests that verity/ contains only stdlib imports."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_verity_stdlib_only():
    script = REPO_ROOT / "tools" / "check_stdlib_only.py"
    target = REPO_ROOT / "verity"

    res = subprocess.run(
        [sys.executable, str(script), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert res.returncode == 0, f"Non-stdlib imports detected in verity:\n{res.stderr}\n{res.stdout}"
    assert "OK: All imports in" in res.stdout
