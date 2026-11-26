# tests/strategy/test_tune.py — owned by Dev2.
"""Tuner: spike point, protocol guards, bounds, plateau pick, determinism, output."""
from __future__ import annotations

import math
import random
from pathlib import Path

import pytest

from experiments import tune
from verity.config import Config

# ---------------------------------------------------------------------------
# Point 0 and switches
# ---------------------------------------------------------------------------

def test_point_zero_reproduces_the_spike_means():
    """Spike defaults at n=210: public 48.7, family TRAIN 30.7, no violations."""
    point = tune.evaluate_point(dict(tune.SPIKE_DEFAULT))
    assert round(point["public_mean"], 1) == 48.7
    assert round(point["family_mean"], 1) == 30.7
    assert point["violations"] == 0
    assert point["J"] == pytest.approx(0.5 * point["public_mean"] + 0.5 * point["family_mean"])
    for source in ("public", "family"):
        assert len(point["runs"][source]) == 3
        assert all(len(r["per_negotiation"]) == 210 for r in point["runs"][source])


def test_switches_string_round_trips_through_config():
    spec = tune.switches_for(dict(tune.SPIKE_DEFAULT))
    cfg = Config.from_switches(spec)
    assert cfg.T == 6.0 and cfg.e == 0.5 and cfg.g == 0.5
    assert cfg.slack == 0.0 and cfg.walk_slack == 0.97
    assert cfg.m == 0 and cfg.max_round == 10
    assert cfg.partial_bid_policy == "matched"
    assert cfg.echo_buyer_total is True
    assert cfg.allocator == "proportional"
    assert cfg.accept_require_complete is False
    assert spec.startswith("T=6.0,e=0.5,slack=0.0,g=0.5,walk_slack=0.97,")


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------

def test_sampled_points_stay_inside_the_bounds():
    rng = random.Random(7)
    parents = []
    for _ in range(200):
        point = tune.sample_uniform(rng)
        parents.append(point)
        for name, (low, high) in tune.BOUNDS.items():
            assert low <= point[name] <= high, (name, point)
    for scale in (1.0, 0.5, 0.125):
        for _ in range(200):
            point = tune.sample_refined(rng, parents[0], scale)
            for name, (low, high) in tune.BOUNDS.items():
                assert low <= point[name] <= high, (name, point, scale)


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("seeds", [(0,), (7,), (8,), (9,), (20,), (29,), (1, 2, 3, 4)])
def test_non_tune_seeds_are_refused(seeds):
    with pytest.raises(SystemExit, match="tuning protocol"):
        tune.check_protocol(seeds, "TRAIN")
    with pytest.raises(SystemExit, match="tuning protocol"):
        tune.evaluate_point(dict(tune.SPIKE_DEFAULT), n=1, seeds=seeds)


@pytest.mark.parametrize("split", ["TEST", "ALL", "test"])
def test_non_train_splits_are_refused(split):
    with pytest.raises(SystemExit, match="must be TRAIN"):
        tune.check_protocol((1, 2, 3), split)
    with pytest.raises(SystemExit, match="must be TRAIN"):
        tune.evaluate_point(dict(tune.SPIKE_DEFAULT), n=1, split=split)


def test_cli_exposes_no_seed_or_split_switch(tmp_path: Path):
    with pytest.raises(SystemExit):
        tune.main(["--seeds", "0", "--out", str(tmp_path)])
    with pytest.raises(SystemExit):
        tune.main(["--split", "TEST", "--out", str(tmp_path)])
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# Plateau pick
# ---------------------------------------------------------------------------

def _synthetic_surface():
    """One tall narrow spike (T=6.0) beside a broad, lower plateau (T>=8.0)."""
    points = []

    def add(T, J):
        params = dict(tune.SPIKE_DEFAULT)
        params["T"] = T
        points.append({"index": len(points), "phase": "random", "params": params, "J": J})

    add(6.0, 100.0)
    for T in (5.2, 5.4, 5.6, 5.8, 6.2, 6.4, 6.6, 6.8):
        add(T, 0.0)
    for i in range(20):
        add(8.0 + 0.05 * i, 50.0)
    return points


def test_plateau_pick_prefers_the_broad_plateau_over_a_narrow_spike():
    points = _synthetic_surface()
    spike = max(points, key=lambda p: p["J"])
    assert spike["J"] == 100.0

    pick = tune.plateau_pick(points, k=8)
    assert pick["J"] == 50.0
    assert pick["J_smooth"] == pytest.approx(50.0)
    assert pick["params"]["T"] >= 8.0
    assert pick is not spike

    # Deterministic tie-break: the plateau point nearest the spike defaults.
    assert pick["params"]["T"] == pytest.approx(8.0)
    assert tune.plateau_pick(points, k=8) is pick


def test_plateau_handles_a_single_point():
    points = [
        {"index": 0, "phase": "spike", "params": dict(tune.SPIKE_DEFAULT), "J": 12.0}
    ]
    pick = tune.plateau_pick(points, k=8)
    assert pick["J_smooth"] == 12.0
    assert pick is points[0]


# ---------------------------------------------------------------------------
# End-to-end (tiny)
# ---------------------------------------------------------------------------

def _run(tmp_path: Path, label: str, rng_seed: int = 5):
    return tune.run_tuning(
        rng_seed=rng_seed,
        budget=2,
        refine=1,
        n=30,
        k=2,
        n_resamples=100,
        label=label,
        out_dir=tmp_path,
        verbose=False,
    )


def test_same_rng_seed_produces_identical_csv_rows(tmp_path: Path):
    csv_a, _json_a, payload_a = _run(tmp_path / "a", "det")
    csv_b, _json_b, _payload_b = _run(tmp_path / "b", "det")
    assert csv_a.read_bytes() == csv_b.read_bytes()

    lines = csv_a.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0].split(",") == list(tune.CSV_COLUMNS)
    assert len(lines) == 1 + 4  # spike + 2 random + 1 refine
    assert payload_a["evaluated_points"] == 4
    assert payload_a["protocol"]["n"] == 30
    # -inf parses back from the CSV when a violating point exists.
    for line in lines[1:]:
        assert line.split(",")[7] not in ("nan", "")


def test_csv_writes_negative_inf_as_parseable_text(tmp_path: Path):
    point = {
        "index": 0,
        "phase": "random",
        "params": dict(tune.SPIKE_DEFAULT),
        "J": -math.inf,
        "J_smooth": -math.inf,
        "public_mean": 10.0,
        "family_mean": 20.0,
        "violations": 3,
        "deadlocks": 0,
    }
    meta = {"protocol": {"seeds": [1, 2, 3], "split": "TRAIN", "n": 1}}
    csv_path, _json_path, _payload = tune.write_outputs(tmp_path, "inf", [point], meta)
    fields = csv_path.read_text(encoding="utf-8").splitlines()[1].split(",")
    assert fields[7] == "-inf"
    assert math.isinf(float(fields[7])) and float(fields[7]) < 0


def test_outputs_are_never_overwritten(tmp_path: Path):
    first_csv, first_json, _ = _run(tmp_path, "same")
    first_bytes = first_csv.read_bytes()
    first_json_bytes = first_json.read_bytes()

    second_csv, second_json, _ = _run(tmp_path, "same")
    assert second_csv != first_csv
    assert second_json != first_json
    assert first_csv.read_bytes() == first_bytes
    assert first_json.read_bytes() == first_json_bytes
    assert len(list(tmp_path.glob("*.csv"))) == 2
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_json_records_the_protocol_and_all_three_points(tmp_path: Path):
    import json

    _csv, json_path, payload = _run(tmp_path, "meta", rng_seed=9)
    on_disk = json.loads(json_path.read_text(encoding="utf-8"))
    assert on_disk["rng_seed"] == 9
    assert on_disk["budget"] == 2 and on_disk["refine"] == 1
    assert on_disk["protocol"] == {
        "seeds": [1, 2, 3],
        "split": "TRAIN",
        "n": 30,
        "banner": tune.BANNER,
    }
    for key in ("spike_default", "best_raw", "plateau_pick"):
        spec = on_disk[key]["switches"]
        assert spec.startswith("T=")
        assert "walk_slack=" in spec and "allocator=proportional" in spec
    assert "plateau_vs_default" in on_disk
    for source in ("public", "family"):
        assert on_disk["plateau_vs_default"][source]["n"] == 3 * 30
    assert len(on_disk["top_smooth"]) == 4
    assert on_disk["wall_clock_seconds"] > 0
    assert math.isfinite(payload["wall_clock_seconds"])
