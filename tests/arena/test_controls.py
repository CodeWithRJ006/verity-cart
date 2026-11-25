"""Every bad control must be caught by its DESIGNATED detector; the good references must pass the same detectors.
Note: seller_spike.py has no text check; it is scored, and any expected finding is asserted explicitly below."""
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from arena import attack_matrix, checks  # noqa: E402
from arena import driver as d  # noqa: E402

C = d.CONTROLS


@pytest.fixture(scope="module")
def scripts():
    return d.family_scripts()


def matrix(name):
    return attack_matrix.evaluate(C / name)


def test_below_floor_caught_by_policy_violations():
    rep = matrix("bad_below_floor.py")
    assert rep["clean"]["violations"] > 0


def test_text_pressure_caught_by_text_flags():
    rep = matrix("bad_text_pressure.py")
    assert rep["clean"]["violations"] > 0


def test_crash_caught_by_attack_matrix_crash_column():
    rep = matrix("bad_crash.py")
    assert any(r["crash"] for r in rep["rows"].values())


def test_dup_sku_caught_by_attack_matrix_dup_column():
    rep = matrix("bad_dup_sku.py")
    assert rep["clean"]["dup"] > 0 and not attack_matrix.ok(rep)


def test_follows_text_caught_by_metamorphic_and_matrix():
    runs, bad = checks.metamorphic(C / "bad_follows_text.py", d.family_scripts()[:5], d.text_variants(30))
    assert bad > 0
    rep = matrix("bad_follows_text.py")
    assert rep["rows"]["injection"]["moved"] > 0 and rep["rows"]["fake_budget"]["moved"] == 0


def test_stateful_caught_by_twin_and_session(scripts):
    assert checks.twin(C / "bad_stateful.py", scripts)[1] > 0
    assert checks.session_reuse(C / "bad_stateful.py", scripts, reps=2)[1] > 0


def _score(seller):
    kit = d.KIT
    rel = os.path.relpath(str(Path(seller).resolve()), str(kit))
    p = subprocess.run([sys.executable, "evaluate.py", "--seller", rel, "--seed", "0", "--n", "60", "--no-baseline"],
                       cwd=str(kit), capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-400:]
    return float(re.search(r"^SCORE\s+(-?[\d.]+)", p.stdout, re.M).group(1))


def test_walks_early_caught_by_score_collapse():
    assert _score(C / "bad_walks_early.py") < 0.5 * _score(d.BASELINE)


GOOD = [d.BASELINE] + ([d.SPIKE] if d.SPIKE.exists() else [])


@pytest.mark.parametrize("seller", GOOD, ids=lambda p: Path(p).stem)
def test_good_references_pass_every_detector(seller, scripts):
    assert attack_matrix.ok(attack_matrix.evaluate(seller))
    assert checks.metamorphic(seller, scripts[:5], d.text_variants(20))[1] == 0
    assert checks.twin(seller, scripts)[1] == 0
    assert checks.session_reuse(seller, scripts, reps=2)[1] == 0
