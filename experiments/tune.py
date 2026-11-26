# experiments/tune.py — owned by Dev2. Python 3.9, stdlib only.
"""Random search + local refinement over the five spike parameters.

    python experiments/tune.py [--budget 300] [--refine 100] [--rng-seed 0]
        [--n 210] [--k 8] [--label default] [--out experiments/tuning]

Protocol (hard-coded, there is no flag to change it):
  * seeds are exactly TUNE {1,2,3}: DEV-EVAL {0,7,8,9} and SEALED {20..29} are refused;
  * the family source is the TRAIN split only.

Objective, per point:
    J = 0.5 * mean(score on public buyers, seeds 1,2,3)
      + 0.5 * mean(score on family TRAIN,  seeds 1,2,3)
and J = -inf when the point has any policy or truth violation.

Every evaluation goes through experiments.local_runner.run_seed and
seed_payload in memory; nothing is written except the CSV and JSON pair for
this tuning run (exclusive create, never overwrite).
"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import random
import statistics
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from experiments import local_runner, stats
from verity.config import Config

ROOT = Path(__file__).resolve().parents[1]

TUNE_SEEDS = (1, 2, 3)
FAMILY_SPLIT = "TRAIN"
DEFAULT_N = 210
PARAMS = ("T", "e", "slack", "g", "walk_slack")
BOUNDS: Dict[str, Tuple[float, float]] = {
    "T": (3.0, 9.0),
    "e": (0.3, 2.0),
    "slack": (0.0, 0.03),
    "g": (0.0, 1.0),
    "walk_slack": (0.90, 1.0),
}
SPIKE_DEFAULT: Dict[str, float] = {
    "T": 6.0,
    "e": 0.5,
    "slack": 0.0,
    "g": 0.5,
    "walk_slack": 0.97,
}
FIXED: Dict[str, object] = {
    "m": 0,
    "max_round": 10,
    "partial_bid_policy": "matched",
    "accept_require_complete": False,
    "echo_buyer_total": True,
    "allocator": "proportional",
}
OBJECTIVE = (
    "J = 0.5*mean score(public, seeds 1,2,3) + 0.5*mean score(family TRAIN, "
    "seeds 1,2,3); J = -inf if policy+truth violations > 0"
)
BANNER = (
    "TUNE seeds only: gains here are optimistic (selection of the best of N); "
    "the evidence is the DEV-EVAL comparison with these switches frozen"
)
CSV_COLUMNS = (
    "index", "phase", "T", "e", "slack", "g", "walk_slack",
    "J", "public_mean", "family_mean", "violations", "deadlocks",
)


# ---------------------------------------------------------------------------
# Protocol and switches
# ---------------------------------------------------------------------------

def check_protocol(seeds: Sequence[int], split: str) -> None:
    """Refuse anything outside TUNE {1,2,3} / family TRAIN.  Hard guards."""
    bad = [s for s in seeds if int(s) not in TUNE_SEEDS]
    if bad:
        raise SystemExit(
            "tuning protocol: seed(s) %s are not TUNE seeds {1,2,3}; "
            "DEV-EVAL {0,7,8,9}, SEALED {20..29} and any other seed are refused"
            % bad
        )
    if split != FAMILY_SPLIT:
        raise SystemExit(
            "tuning protocol: the family split must be TRAIN, got %r "
            "(TEST and ALL are refused)" % (split,)
        )


def _fmt_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return repr(value)
    return str(value)


def switches_for(params: Dict[str, float]) -> str:
    """Serialise one point as a local_runner --switches string.

    The five tuned values come first; the fixed spike defaults follow.  The
    string is validated through Config.from_switches (verity/config.py:35-66),
    which raises ValueError for anything malformed or unknown.
    """
    pairs = ["%s=%s" % (name, _fmt_value(float(params[name]))) for name in PARAMS]
    pairs += ["%s=%s" % (key, _fmt_value(value)) for key, value in FIXED.items()]
    spec = ",".join(pairs)
    Config.from_switches(spec)  # validation only; run_seed parses it again
    return spec


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate_point(
    params: Dict[str, float],
    n: int = DEFAULT_N,
    seeds: Sequence[int] = TUNE_SEEDS,
    split: str = FAMILY_SPLIT,
) -> dict:
    """Evaluate one parameter point in memory; returns its results and per-negotiation lists."""
    check_protocol(seeds, split)
    if n < 1:
        raise SystemExit("--n must be >= 1, got %d" % n)
    spec = switches_for(params)

    runs: Dict[str, List[dict]] = {"public": [], "family": []}
    scores: Dict[str, List[float]] = {"public": [], "family": []}
    violations = 0
    deadlocks = 0
    sources = (("public", "public", "ALL"), ("family", "family", split))
    for key, buyers, buyer_split in sources:
        for seed in seeds:
            summary, results, buyer_classes = local_runner.run_seed(
                int(seed), spec, n, buyers, buyer_split
            )
            payload = local_runner.seed_payload(summary, results, buyer_classes, int(seed))
            violations += summary["policy"] + summary["truth"]
            deadlocks += summary["deadlocks"]
            scores[key].append(summary["score"])
            runs[key].append(
                {
                    "seed": int(seed),
                    "n": payload["n"],
                    "scenario_hash": payload["scenario_hash"],
                    "per_negotiation": payload["per_negotiation"],
                    "score": summary["score"],
                }
            )

    public_mean = statistics.mean(scores["public"])
    family_mean = statistics.mean(scores["family"])
    J = 0.5 * public_mean + 0.5 * family_mean
    if violations > 0:
        J = -math.inf
    return {
        "params": {name: float(params[name]) for name in PARAMS},
        "switches": spec,
        "J": J,
        "public_mean": public_mean,
        "family_mean": family_mean,
        "violations": violations,
        "deadlocks": deadlocks,
        "runs": runs,
    }


def _pooled(point: dict, source: str) -> List[float]:
    out: List[float] = []
    for run in point["runs"][source]:
        out.extend(run["per_negotiation"])
    return out


# ---------------------------------------------------------------------------
# Sampling and the plateau pick
# ---------------------------------------------------------------------------

def sample_uniform(rng: random.Random) -> Dict[str, float]:
    return {name: rng.uniform(*BOUNDS[name]) for name in PARAMS}


def sample_refined(
    rng: random.Random, parent: Dict[str, float], scale: float
) -> Dict[str, float]:
    """Gaussian step around ``parent``, clipped to bounds; ``scale`` shrinks sigma."""
    out: Dict[str, float] = {}
    for name in PARAMS:
        low, high = BOUNDS[name]
        sigma = (high - low) * 0.15 * scale
        value = parent[name] + rng.gauss(0.0, sigma)
        out[name] = min(high, max(low, value))
    return out


def _normalise(params: Dict[str, float]) -> Tuple[float, ...]:
    coords = []
    for name in PARAMS:
        low, high = BOUNDS[name]
        span = high - low
        coords.append(0.0 if span == 0 else (params[name] - low) / span)
    return tuple(coords)


def _distance(a: Tuple[float, ...], b: Tuple[float, ...]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def smooth_scores(points: Sequence[dict], k: int = 8) -> List[float]:
    """J_smooth = mean of the point's own J and its k nearest neighbours' J."""
    coords = [_normalise(p["params"]) for p in points]
    out: List[float] = []
    for i, coord in enumerate(coords):
        order = sorted(
            (_distance(coord, other), j)
            for j, other in enumerate(coords)
            if j != i
        )[:k]
        values = [points[i]["J"]] + [points[j]["J"] for _d, j in order]
        out.append(sum(values) / len(values))
    return out


def plateau_pick(
    points: Sequence[dict],
    k: int = 8,
    defaults: Optional[Dict[str, float]] = None,
) -> dict:
    """Return the maximum-J_smooth point; annotates every point with J_smooth.

    Deterministic tie-break: smaller normalised distance to the spike defaults,
    then earlier index.
    """
    defaults = SPIKE_DEFAULT if defaults is None else defaults
    smooth = smooth_scores(points, k)
    default_coord = _normalise(defaults)
    for point, value in zip(points, smooth):
        point["J_smooth"] = value

    def key(pair):
        i, point = pair
        return (smooth[i], -_distance(_normalise(point["params"]), default_coord), -i)

    best_i = max(range(len(points)), key=lambda i: key((i, points[i])))
    return points[best_i]


def top_by_smooth(points: Sequence[dict], limit: int = 10) -> List[dict]:
    indexed = list(enumerate(points))
    indexed.sort(key=lambda pair: (-pair[1]["J_smooth"], pair[0]))
    return [point for _i, point in indexed[:limit]]


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _csv_value(value: float) -> str:
    return repr(float(value))  # number or '-inf'


def _json_j(value: float) -> Optional[float]:
    return float(value) if math.isfinite(value) else None


def point_summary(point: dict) -> dict:
    return {
        "index": point["index"],
        "phase": point["phase"],
        "params": point["params"],
        "switches": point["switches"],
        "J": _json_j(point["J"]),
        "J_smooth": _json_j(point["J_smooth"]),
        "public_mean": point["public_mean"],
        "family_mean": point["family_mean"],
        "violations": point["violations"],
        "deadlocks": point["deadlocks"],
    }


def write_outputs(out_dir: Path, label: str, points: Sequence[dict], meta: dict) -> Tuple[Path, Path, dict]:
    """Write the CSV/JSON pair with exclusive create; returns (csv, json, payload)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    stem = "%s_%s_tune_%s" % (stamp, local_runner.git_short_sha(), label)
    suffix = 0
    while True:
        name = stem if suffix == 0 else "%s_%d" % (stem, suffix + 1)
        csv_path = out_dir / (name + ".csv")
        json_path = out_dir / (name + ".json")
        if not csv_path.exists() and not json_path.exists():
            break
        suffix += 1

    lines = [",".join(CSV_COLUMNS)]
    for point in points:
        fields = [
            str(point["index"]),
            point["phase"],
        ]
        fields += [_csv_value(point["params"][name]) for name in PARAMS]
        fields += [
            _csv_value(point["J"]),
            _csv_value(point["public_mean"]),
            _csv_value(point["family_mean"]),
            str(point["violations"]),
            str(point["deadlocks"]),
        ]
        lines.append(",".join(fields))

    with open(csv_path, "x", encoding="utf-8") as fh:  # 'x': exclusive create
        fh.write("\n".join(lines) + "\n")

    payload = dict(meta)
    payload["csv_path"] = str(csv_path)
    payload["json_path"] = str(json_path)
    with open(json_path, "x", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return csv_path, json_path, payload


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def _protocol_meta(n: int) -> dict:
    return {
        "protocol": {
            "seeds": list(TUNE_SEEDS),
            "split": FAMILY_SPLIT,
            "n": n,
            "banner": BANNER,
        },
        "objective": OBJECTIVE,
        "bounds": {name: list(BOUNDS[name]) for name in PARAMS},
        "fixed": FIXED,
        "spike_default_params": SPIKE_DEFAULT,
        "python_version": "%d.%d.%d" % sys.version_info[:3],
        "git_sha": local_runner.git_short_sha(),
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def run_tuning(
    rng_seed: int = 0,
    budget: int = 300,
    refine: int = 100,
    n: int = DEFAULT_N,
    k: int = 8,
    n_resamples: int = 10000,
    label: str = "default",
    out_dir: Optional[Path] = None,
    verbose: bool = True,
) -> Tuple[Path, Path, dict]:
    """Run point 0, ``budget`` random points and ``refine`` local points; write CSV+JSON."""
    check_protocol(TUNE_SEEDS, FAMILY_SPLIT)
    if budget < 0 or refine < 0:
        raise SystemExit("--budget and --refine must be >= 0")
    if n < 1:
        raise SystemExit("--n must be >= 1, got %d" % n)
    if k < 1:
        raise SystemExit("--k must be >= 1, got %d" % k)

    out_dir = Path(out_dir) if out_dir is not None else ROOT / "experiments" / "tuning"
    rng = random.Random(rng_seed)
    invalid: List[dict] = []
    points: List[dict] = []
    started = time.perf_counter()

    if verbose:
        print(BANNER)
        print(
            "\nprotocol: seeds %s, family split %s, n=%d  (budget=%d, refine=%d, rng_seed=%d)"
            % (",".join(str(s) for s in TUNE_SEEDS), FAMILY_SPLIT, n, budget, refine, rng_seed)
        )

    def run(params: dict, phase: str, index: int) -> None:
        try:
            point = evaluate_point(params, n)
        except ValueError as exc:  # Config.from_switches rejected the point
            invalid.append({"index": index, "phase": phase, "params": params, "error": str(exc)})
            if verbose:
                print("  point %3d %-6s invalid, skipped: %s" % (index, phase, exc))
            return
        point["index"] = index
        point["phase"] = phase
        points.append(point)
        if verbose:
            print(
                "  point %3d %-6s J=%8.3f  public=%6.2f  family=%6.2f  viol=%d dead=%d"
                % (index, phase, point["J"], point["public_mean"],
                   point["family_mean"], point["violations"], point["deadlocks"])
            )

    run(dict(SPIKE_DEFAULT), "spike", 0)

    for i in range(1, budget + 1):
        run(sample_uniform(rng), "random", i)

    top5 = sorted(points, key=lambda p: (-_sortable(p["J"]), p["index"]))[:5]
    for i in range(refine):
        stage = min(3, (4 * i) // max(1, refine))
        parent = top5[rng.randrange(len(top5))]
        run(sample_refined(rng, parent["params"], 0.5 ** stage), "refine", budget + 1 + i)

    if not points:
        raise SystemExit("tuning produced no valid points")

    plateau = plateau_pick(points, k)
    top5 = sorted(points, key=lambda p: (-_sortable(p["J"]), p["index"]))[:5]
    best = top5[0]
    spike = points[0]
    assert spike["phase"] == "spike"

    comparisons = {}
    for source in ("public", "family"):
        a = _pooled(plateau, source)
        b = _pooled(spike, source)
        diff, low, high = stats.paired_bootstrap(a, b, n_resamples, rng_seed)
        if low > 0:
            direction = "better"
        elif high < 0:
            direction = "worse"
        else:
            direction = "none"
        comparisons[source] = {
            "n": len(a),
            "mean_diff": diff,
            "ci_low": low,
            "ci_high": high,
            "n_resamples": n_resamples,
            "improves": low > 0,
            "direction": direction,
        }

    wall_seconds = time.perf_counter() - started
    meta = _protocol_meta(n)
    meta.update(
        {
            "rng_seed": rng_seed,
            "budget": budget,
            "refine": refine,
            "k": k,
            "n_resamples": n_resamples,
            "label": label,
            "wall_clock_seconds": wall_seconds,
            "evaluated_points": len(points),
            "invalid_points": invalid,
            "spike_default": point_summary(spike),
            "best_raw": point_summary(best),
            "plateau_pick": point_summary(plateau),
            "sharpness": _json_j(best["J"] - best["J_smooth"]),
            "top_smooth": [
                {
                    "rank": rank,
                    "index": p["index"],
                    "phase": p["phase"],
                    "params": p["params"],
                    "J": _json_j(p["J"]),
                    "J_smooth": _json_j(p["J_smooth"]),
                }
                for rank, p in enumerate(top_by_smooth(points, 10), start=1)
            ],
            "plateau_vs_default": comparisons,
        }
    )
    csv_path, json_path, payload = write_outputs(out_dir, label, points, meta)

    if verbose:
        _print_report(payload, points, plateau)
        print("\nwrote %s" % csv_path)
        print("wrote %s" % json_path)

    return csv_path, json_path, payload


def _sortable(value: float) -> float:
    """-inf safe sort key: violations rank last."""
    return float(value)


def _print_report(payload: dict, points: Sequence[dict], plateau: dict) -> None:
    print("\n%s" % BANNER)
    print("\ntop 10 points by J_smooth")
    print("rank  idx  phase   T      e      slack   g      walk   J        J_smooth")
    for row in payload["top_smooth"]:
        p = row["params"]
        print(
            "  %2d  %3d  %-6s %5.2f  %5.2f  %5.3f  %5.2f  %5.2f  %8.3f %8.3f"
            % (row["rank"], row["index"], row["phase"], p["T"], p["e"],
               p["slack"], p["g"], p["walk_slack"],
               row["J"] if row["J"] is not None else float("-inf"),
               row["J_smooth"] if row["J_smooth"] is not None else float("-inf"))
        )

    for key, label in (
        ("spike_default", "spike default"),
        ("best_raw", "best raw"),
        ("plateau_pick", "plateau pick"),
    ):
        point = payload[key]
        print("\n%s (index %d, phase %s): J=%s  J_smooth=%s"
              % (label, point["index"], point["phase"],
                 _show_j(point["J"]), _show_j(point["J_smooth"])))
        print("  --switches %s" % point["switches"])

    print("\nsharpness warning: best raw J - J_smooth = %s" % _show_j(payload["sharpness"]))

    print("\nplateau pick vs spike defaults (paired bootstrap, per source)")
    verdicts = {"better": "improves", "worse": "worse", "none": "no significant difference"}
    for source in ("public", "family"):
        c = payload["plateau_vs_default"][source]
        print(
            "  %-6s n=%d  diff %+.3f  95%% CI [%+.3f, %+.3f]  %s"
            % (source, c["n"], c["mean_diff"], c["ci_low"], c["ci_high"],
               verdicts[c["direction"]])
        )
    print("\nwall clock          %.1f s  (%d points x 6 runs, n=%d)"
          % (payload["wall_clock_seconds"], len(points), payload["protocol"]["n"]))


def _show_j(value: Optional[float]) -> str:
    return "-inf" if value is None else "%.3f" % value


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Random search + refinement over the spike parameters.")
    ap.add_argument("--budget", type=int, default=300, help="random points (phase 1)")
    ap.add_argument("--refine", type=int, default=100, help="refinement points (phase 2)")
    ap.add_argument("--rng-seed", type=int, default=0, help="seed for random.Random")
    ap.add_argument("--n", type=int, default=DEFAULT_N, help="negotiations per seed (default 210)")
    ap.add_argument("--k", type=int, default=8, help="neighbours for the plateau smoothing")
    ap.add_argument("--label", default="default", help="label in the output filenames")
    ap.add_argument("--out", default=str(ROOT / "experiments" / "tuning"),
                    help="output directory (created if missing)")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    run_tuning(
        rng_seed=args.rng_seed,
        budget=args.budget,
        refine=args.refine,
        n=args.n,
        k=args.k,
        label=args.label,
        out_dir=Path(args.out),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
