"""S3: metamorphic, twin, session-reuse and attack-matrix tests on the GOOD reference sellers.
Sellers are black boxes (file paths). Never imports verity."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from arena import attack_matrix, checks  # noqa: E402
from arena import driver as d  # noqa: E402

GOOD = [pytest.param(d.BASELINE, id="kit_baseline"),
        pytest.param(d.SPIKE, id="spike", marks=pytest.mark.skipif(not d.SPIKE.exists(), reason="no seller_spike.py"))]


@pytest.fixture(scope="module")
def scripts():
    return d.family_scripts()


def test_inputs_are_what_we_claim(scripts):
    assert len(scripts) == 20 and all(len(s) >= 5 for s in scripts)
    assert len(d.text_variants(100)) == 100 and len(set(d.text_variants(100))) >= 90


@pytest.mark.parametrize("seller", GOOD)
def test_metamorphic_text_never_moves_the_seller(seller, scripts):
    runs, bad = checks.metamorphic(seller, scripts)
    print("metamorphic: %d negotiations, %d mismatches" % (runs, bad))
    assert runs == 2000 and bad == 0


@pytest.mark.parametrize("seller", GOOD)
def test_twin(seller, scripts):
    runs, bad = checks.twin(seller, scripts)
    assert runs == 20 and bad == 0


@pytest.mark.parametrize("seller", GOOD)
def test_session_reuse(seller, scripts):
    runs, bad = checks.session_reuse(seller, scripts)
    print("session reuse: %d negotiations, %d mismatches" % (runs, bad))
    assert runs == 200 and bad == 0


@pytest.mark.parametrize("seller", GOOD)
def test_attack_matrix(seller):
    rep = attack_matrix.evaluate(seller)
    assert len(rep["rows"]) == 14
    assert attack_matrix.ok(rep), rep
