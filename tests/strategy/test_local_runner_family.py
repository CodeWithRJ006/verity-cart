# tests/strategy/test_local_runner_family.py — owned by Dev2.
"""Family-buyer path of the local runner: --buyers family and --split TRAIN|TEST.

The split is read from arena/family_split.json by local_runner (never
re-implemented); these tests only compare against that same file.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments import local_runner

ROOT = Path(__file__).resolve().parents[2]
SPLIT_FILE = ROOT / "arena" / "family_split.json"


def _split(name: str):
    data = json.loads(SPLIT_FILE.read_text(encoding="utf-8"))
    return data["split"][name]


def test_split_preserves_module_order_and_matches_the_file():
    all_classes, meta_all = local_runner.load_buyers("family", "ALL")
    assert meta_all["spec"] == "family"
    assert meta_all["split"] == "ALL"
    assert len(all_classes) == 20

    for name, expected_n in (("TRAIN", 12), ("TEST", 8)):
        classes, meta = local_runner.load_buyers("family", name)
        assert meta["split"] == name
        assert len(classes) == expected_n
        assert set(classes) == set(_split(name))
        # Module order, filtered by name (scenario order depends on it).
        assert meta["names"] == [n for n in meta_all["names"] if n in set(_split(name))]


def test_train_end_to_end_stores_per_negotiation_scores(tmp_path: Path):
    n = 12  # one negotiation per TRAIN config
    args = [
        "--buyers", "family",
        "--split", "TRAIN",
        "--seeds", "0",
        "--n", str(n),
        "--out", str(tmp_path),
        "--label", "family_train",
    ]
    assert local_runner.main(args) == 0

    files = sorted(tmp_path.glob("*.json"))
    assert len(files) == 1, files
    payload = json.loads(files[0].read_text(encoding="utf-8"))

    assert payload["buyers"]["spec"] == "family"
    assert payload["buyers"]["split"] == "TRAIN"
    assert len(payload["buyers"]["names"]) == 12
    assert set(payload["buyers"]["names"]) == set(_split("TRAIN"))

    row = payload["per_seed"]["0"]
    assert row["n"] == n
    assert len(row["per_negotiation"]) == n
    assert len(row["scenario_hash"]) == 64
    assert sum(row["per_negotiation"]) / n == pytest.approx(row["score"])
    assert payload["wall_clock_seconds"] >= 0

    # n == len(TRAIN): every selected buyer was played exactly once.
    assert list(row["per_buyer"]) == payload["buyers"]["names"]
    assert all(pb["n"] == 1 for pb in row["per_buyer"].values())


def test_split_all_is_the_unfiltered_family():
    classes, meta = local_runner.load_buyers("family", "ALL")
    assert len(classes) == 20
    assert len(meta["names"]) == 20


def test_family_runs_are_deterministic():
    first = local_runner.seed_payload(
        *local_runner.run_seed(0, "", 6, "family", "TRAIN"), seed=0
    )
    second = local_runner.seed_payload(
        *local_runner.run_seed(0, "", 6, "family", "TRAIN"), seed=0
    )
    assert first["per_negotiation"] == second["per_negotiation"]
    assert first["scenario_hash"] == second["scenario_hash"]
    assert first["per_buyer"] == second["per_buyer"]
