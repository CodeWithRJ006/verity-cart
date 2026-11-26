# experiments/stats.py — owned by Dev2. Python 3.9, stdlib only.
"""Paired bootstrap and comparison of local_runner result files.

    python experiments/stats.py --a A.json --b B.json [--n-resamples 10000] [--seed 0]

`per_negotiation` lists are compared only when they come from identical
scenarios: same seed set, same length, same scenario_hash and same buyer set
(checked per seed).  The pooled difference concatenates the seeds in seed
order, so pairing is preserved; public and family result files are never
merged.

Positive mean_diff always means A scores higher than B.

This module does not import arena; the percentile convention matches
arena/stats.py:19-20 (nearest rank over the sorted bootstrap means).
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
from pathlib import Path
from typing import Dict, List, Sequence, Tuple


def _mean(values: Sequence[float]) -> float:
    return statistics.mean(values) if values else 0.0


def paired_bootstrap(
    a: Sequence[float],
    b: Sequence[float],
    n_resamples: int = 10000,
    seed: int = 0,
) -> Tuple[float, float, float]:
    """Paired bootstrap over two equal-length score lists from the same scenarios.

    Returns ``(mean(a) - mean(b), ci_low, ci_high)``; the CI is the 2.5/97.5
    percentile of the resampled mean differences.  Deterministic for a fixed
    ``seed``.  A positive ``ci_low`` means A improves on B.
    """
    a = [float(x) for x in a]
    b = [float(x) for x in b]
    if len(a) != len(b):
        raise ValueError(
            "paired bootstrap needs equal lengths, got %d and %d" % (len(a), len(b))
        )
    if not a:
        raise ValueError("paired bootstrap needs at least one pair")
    if n_resamples < 1:
        raise ValueError("n_resamples must be >= 1, got %d" % n_resamples)

    diffs = [x - y for x, y in zip(a, b)]
    rng = random.Random(seed)
    n = len(diffs)
    means = sorted(
        sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_resamples)
    )
    low = means[int(0.025 * n_resamples)]
    high = means[int(0.975 * n_resamples) - 1]
    return statistics.mean(diffs), low, high


# ---------------------------------------------------------------------------
# local_runner result files
# ---------------------------------------------------------------------------

def _seed_rows(payload: dict) -> Dict[str, dict]:
    rows = payload.get("per_seed")
    if not isinstance(rows, dict) or not rows:
        raise ValueError("result file has no per_seed rows")
    for seed, row in rows.items():
        if not isinstance(row, dict):
            raise ValueError("per_seed[%r] is not an object" % seed)
        if not isinstance(row.get("per_negotiation"), list):
            raise ValueError("per_seed[%r] has no per_negotiation list" % seed)
        if not isinstance(row.get("scenario_hash"), str):
            raise ValueError("per_seed[%r] has no scenario_hash" % seed)
    return rows


def check_pairable(a: dict, b: dict) -> List[str]:
    """Validate two local_runner payloads and return their common seeds in order.

    Raises ValueError when the runs did not see identical scenarios, so a
    comparison can never silently pair different negotiations.
    """
    ra, rb = _seed_rows(a), _seed_rows(b)
    if set(ra) != set(rb):
        raise ValueError(
            "refusing to compare: seed sets differ (%s vs %s)"
            % (sorted(ra, key=int), sorted(rb, key=int))
        )

    ba, bb = a.get("buyers") or {}, b.get("buyers") or {}
    for key in ("spec", "split"):
        if key in ba and key in bb and ba[key] != bb[key]:
            raise ValueError(
                "refusing to compare: buyers.%s differs (%r vs %r)"
                % (key, ba[key], bb[key])
            )
    if ba.get("names") and bb.get("names") and list(ba["names"]) != list(bb["names"]):
        raise ValueError("refusing to compare: buyers.names differ")

    seeds = sorted(ra, key=int)
    for seed in seeds:
        x = ra[seed]["per_negotiation"]
        y = rb[seed]["per_negotiation"]
        if len(x) != len(y):
            raise ValueError(
                "refusing to compare seed %s: lengths %d vs %d" % (seed, len(x), len(y))
            )
        if ra[seed]["scenario_hash"] != rb[seed]["scenario_hash"]:
            raise ValueError(
                "refusing to compare seed %s: scenario_hash mismatch (%s vs %s)"
                % (seed, ra[seed]["scenario_hash"], rb[seed]["scenario_hash"])
            )
    return seeds


def compare(a: dict, b: dict, n_resamples: int = 10000, seed: int = 0) -> dict:
    """Per-seed means plus the pooled paired difference (A minus B) and its CI."""
    seeds = check_pairable(a, b)
    ra = a["per_seed"]
    rb = b["per_seed"]
    pooled_a: List[float] = []
    pooled_b: List[float] = []
    per_seed = []
    for s in seeds:
        x = [float(v) for v in ra[s]["per_negotiation"]]
        y = [float(v) for v in rb[s]["per_negotiation"]]
        per_seed.append(
            {
                "seed": int(s),
                "n": len(x),
                "mean_a": _mean(x),
                "mean_b": _mean(y),
                "mean_diff": _mean(x) - _mean(y),
            }
        )
        pooled_a.extend(x)
        pooled_b.extend(y)

    diff, low, high = paired_bootstrap(pooled_a, pooled_b, n_resamples, seed)
    if low > 0:
        improves = "a"
    elif high < 0:
        improves = "b"
    else:
        improves = None
    return {
        "per_seed": per_seed,
        "pooled": {
            "n": len(pooled_a),
            "mean_a": _mean(pooled_a),
            "mean_b": _mean(pooled_b),
            "mean_diff": diff,
            "ci_low": low,
            "ci_high": high,
            "n_resamples": n_resamples,
            "seed": seed,
            "improves": improves,
        },
    }


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Paired bootstrap comparison of two local_runner JSON files.")
    ap.add_argument("--a", required=True, help="result JSON for run A")
    ap.add_argument("--b", required=True, help="result JSON for run B")
    ap.add_argument("--n-resamples", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    try:
        a, b = _load(args.a), _load(args.b)
        report = compare(a, b, args.n_resamples, args.seed)
    except (OSError, ValueError) as exc:
        raise SystemExit("cannot compare: %s" % exc)

    print("A: %s" % args.a)
    print("B: %s" % args.b)
    print("\nseed        n   mean A   mean B   diff(A-B)")
    for row in report["per_seed"]:
        print(
            "  %-6s %5d  %7.3f  %7.3f  %+8.3f"
            % (row["seed"], row["n"], row["mean_a"], row["mean_b"], row["mean_diff"])
        )
    p = report["pooled"]
    print(
        "\npooled paired diff (A-B)  %+.3f  95%% CI [%+.3f, %+.3f]  "
        "(%d pairs, %d resamples)"
        % (p["mean_diff"], p["ci_low"], p["ci_high"], p["n"], p["n_resamples"])
    )
    if p["improves"] == "a":
        print("CI excludes 0: A improves on B")
    elif p["improves"] == "b":
        print("CI excludes 0: B improves on A")
    else:
        print("CI includes 0: no significant difference")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
