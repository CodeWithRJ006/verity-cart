# tests/strategy/test_local_runner.py — owned by Dev2.
"""Local runner: golden spike reproduction, JSON output, switch validation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments import local_runner

REQUIRED_PER_SEED = {
    "score",
    "deal_rate",
    "value_per_negotiation",
    "value_among_deals",
    "margin_kept",
    "violations",
    "deadlocks",
    "per_buyer",
}
BUYERS = ["cooperative", "hard_bargainer", "manipulator"]


def test_seed_0_defaults_reproduce_the_spike():
    """Default switches + seed 0 must match the spike's SCORE and per-buyer scores."""
    summary, results, buyer_classes = local_runner.run_seed(0, "", 210)

    assert round(summary["score"], 1) == 51.9
    payload = local_runner.seed_payload(summary, results, buyer_classes)
    scores = {
        name: round(row["score"], 1) for name, row in payload["per_buyer"].items()
    }
    assert scores == {"cooperative": 74.8, "hard_bargainer": 42.9, "manipulator": 38.0}


def test_json_is_written_with_documented_keys_and_never_overwritten(tmp_path: Path):
    args = ["--seeds", "0", "--n", "3", "--out", str(tmp_path), "--label", "t"]

    assert local_runner.main(args) == 0
    files = sorted(tmp_path.glob("*.json"))
    assert len(files) == 1, files
    first = files[0]
    before = first.read_bytes()

    payload = json.loads(before)
    assert {"switches", "seeds", "per_seed", "mean_score"} <= set(payload)
    assert payload["seeds"] == [0]
    row = payload["per_seed"]["0"]
    assert REQUIRED_PER_SEED <= set(row)
    assert set(row["per_buyer"]) == set(BUYERS)
    assert {"score", "deadlocks", "violations"} <= set(row["per_buyer"]["cooperative"])

    assert local_runner.main(args) == 0
    files = sorted(tmp_path.glob("*.json"))
    assert len(files) == 2, files
    assert first.read_bytes() == before, "second run overwrote the first JSON file"


def test_unknown_switch_raises():
    with pytest.raises(ValueError, match="Unknown config switch"):
        local_runner.parse_switches("bogus=1")
    with pytest.raises(ValueError, match="Unknown config switch"):
        local_runner.run_seed(0, "bogus=1", 1)
