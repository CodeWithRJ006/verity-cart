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

    # Additive fields for paired-bootstrap and budget work.
    assert payload["buyers"] == {"spec": "public", "split": "ALL", "names": BUYERS}
    assert isinstance(payload["wall_clock_seconds"], float)
    assert payload["wall_clock_seconds"] >= 0
    assert len(row["per_negotiation"]) == 3
    assert len(row["scenario_hash"]) == 64
    assert sum(row["per_negotiation"]) / 3 == pytest.approx(row["score"])

    assert local_runner.main(args) == 0
    files = sorted(tmp_path.glob("*.json"))
    assert len(files) == 2, files
    assert first.read_bytes() == before, "second run overwrote the first JSON file"


def test_unknown_switch_raises():
    with pytest.raises(ValueError, match="Unknown config switch"):
        local_runner.parse_switches("bogus=1")
    with pytest.raises(ValueError, match="Unknown config switch"):
        local_runner.run_seed(0, "bogus=1", 1)


def test_public_buyers_meta_is_the_kit_default():
    classes, meta = local_runner.load_buyers("public", "ALL")
    assert meta == {"spec": "public", "split": "ALL", "names": BUYERS}
    assert set(classes) == set(BUYERS)


def test_non_public_buyers_are_loaded_like_the_kit(tmp_path: Path):
    """A --buyers path is executed by evaluate.load_buyers, not imported as a package."""
    mod = tmp_path / "my_buyers.py"
    mod.write_text(
        "from buyers import Cooperative\n\nBUYERS = {'solo': Cooperative}\n",
        encoding="utf-8",
    )
    classes, meta = local_runner.load_buyers(str(mod), "ALL")
    assert list(classes) == ["solo"]
    assert meta["spec"] == str(mod)


def test_split_requires_the_family_module():
    with pytest.raises(SystemExit, match="only applies to the family"):
        local_runner.load_buyers("public", "TRAIN")
    with pytest.raises(SystemExit, match="no such module file"):
        local_runner.load_buyers("does/not/exist.py", "ALL")


def test_sealed_seeds_are_refused_everywhere(tmp_path: Path):
    with pytest.raises(SystemExit, match="SEALED"):
        local_runner.run_seed(20, "", 1)
    with pytest.raises(SystemExit, match="SEALED"):
        local_runner.run_seed(29, "", 1)
    with pytest.raises(SystemExit, match="SEALED"):
        local_runner.main(["--seeds", "25", "--n", "1", "--out", str(tmp_path)])
    with pytest.raises(SystemExit, match="SEALED"):
        local_runner.main(["--seeds", "0,21", "--n", "1", "--out", str(tmp_path)])
    assert list(tmp_path.glob("*.json")) == []


def test_per_negotiation_list_is_deterministic():
    first = local_runner.seed_payload(*local_runner.run_seed(0, "", 6), 0)
    second = local_runner.seed_payload(*local_runner.run_seed(0, "", 6), 0)
    assert first["per_negotiation"] == second["per_negotiation"]
    assert first["scenario_hash"] == second["scenario_hash"]
    assert len(first["per_negotiation"]) == 6
