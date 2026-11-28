# tests/strategy/test_stats.py — owned by Dev2.
"""Paired bootstrap: known shifts, determinism, pairing refusal, CLI."""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from experiments import stats


def _shifted(n=400, shift=6.0, noise=4.0, seed=1):
    rng = random.Random(seed)
    base = [50.0 + rng.uniform(-noise, noise) for _ in range(n)]
    return [x + shift for x in base], base


def test_positive_shift_gives_ci_above_zero():
    a, b = _shifted()
    diff, low, high = stats.paired_bootstrap(a, b, n_resamples=2000, seed=0)
    assert diff == pytest.approx(6.0)
    assert low > 0.0
    assert low <= diff <= high


def test_identical_lists_give_zero_and_ci_containing_zero():
    a = [3.0, 1.0, 4.0, 1.0, 5.0, 9.0]
    diff, low, high = stats.paired_bootstrap(a, list(a), n_resamples=500, seed=3)
    assert diff == 0.0
    assert low == 0.0 and high == 0.0


def test_deterministic_for_a_fixed_seed():
    a, b = _shifted()
    first = stats.paired_bootstrap(a, b, n_resamples=300, seed=11)
    second = stats.paired_bootstrap(a, b, n_resamples=300, seed=11)
    assert first == second


def test_unequal_lengths_are_refused():
    with pytest.raises(ValueError, match="equal lengths"):
        stats.paired_bootstrap([1.0, 2.0], [1.0], n_resamples=10)
    with pytest.raises(ValueError, match="at least one pair"):
        stats.paired_bootstrap([], [], n_resamples=10)


def _payload(scores, hash_value, seed="1", buyers=None):
    row = {
        "score": sum(scores) / len(scores),
        "n": len(scores),
        "per_negotiation": list(scores),
        "scenario_hash": hash_value,
        "per_buyer": {},
        "violations": {"policy": 0, "truth": 0, "kinds": {}},
        "deadlocks": 0,
    }
    out = {"per_seed": {seed: row}}
    if buyers is not None:
        out["buyers"] = buyers
    return out


def test_scenario_hash_mismatch_is_refused():
    a = _payload([1.0, 2.0], "aaa")
    b = _payload([1.0, 2.0], "bbb")
    with pytest.raises(ValueError, match="scenario_hash mismatch"):
        stats.check_pairable(a, b)
    with pytest.raises(ValueError, match="scenario_hash mismatch"):
        stats.compare(a, b, n_resamples=10)


def test_different_lengths_between_files_are_refused():
    a = _payload([1.0, 2.0], "same")
    b = _payload([1.0, 2.0, 3.0], "same")
    with pytest.raises(ValueError, match="lengths 2 vs 3"):
        stats.check_pairable(a, b)


def test_matching_files_compare_per_seed_and_pooled():
    a = _payload([10.0, 20.0], "same")
    b = _payload([8.0, 18.0], "same")
    report = stats.compare(a, b, n_resamples=100, seed=0)
    assert report["per_seed"][0]["mean_diff"] == pytest.approx(2.0)
    p = report["pooled"]
    assert p["n"] == 2
    assert p["mean_diff"] == pytest.approx(2.0)
    assert p["improves"] == "a"


def test_buyer_set_mismatch_is_refused():
    a = _payload([1.0], "same", buyers={"spec": "public", "split": "ALL", "names": ["x"]})
    b = _payload([1.0], "same", buyers={"spec": "family", "split": "TRAIN", "names": ["x"]})
    with pytest.raises(ValueError, match="buyers.spec differs"):
        stats.check_pairable(a, b)


def test_cli_prints_per_seed_and_pooled_ci(tmp_path: Path, capsys):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps(_payload([60.0, 61.0, 62.0], "h")), encoding="utf-8")
    b.write_text(json.dumps(_payload([55.0, 56.0, 57.0], "h")), encoding="utf-8")

    assert stats.main(["--a", str(a), "--b", str(b), "--n-resamples", "200"]) == 0
    out = capsys.readouterr().out
    assert "pooled paired diff" in out
    assert "95% CI" in out
    assert "A improves on B" in out


def test_cli_exits_on_mismatch(tmp_path: Path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps(_payload([60.0], "h1")), encoding="utf-8")
    b.write_text(json.dumps(_payload([60.0], "h2")), encoding="utf-8")
    with pytest.raises(SystemExit, match="cannot compare"):
        stats.main(["--a", str(a), "--b", str(b)])
