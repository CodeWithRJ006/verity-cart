# experiments/local_runner.py — owned by Dev2. Python 3.9, stdlib only.
"""Run MiniSeller through the kit harness on evaluate.py's own scenarios.

    python experiments/local_runner.py --switches k=v,k=v --seeds 1,2,3 [--n 210] [--out DIR] [--label NAME]

Scenarios, buyer construction and scoring are imported from kit, not
re-implemented: the scenario list comes from
``evaluate.public_buyers.make_scenarios(store, policy, n, seed, buyers)``
(kit/evaluate.py:134), each buyer is built as
``buyer_classes[sc["buyer"]](sc, store, random.Random(sc["seed"]))``
(kit/evaluate.py:73) inside ``evaluate.run`` (kit/evaluate.py:67), and the
metrics come from ``evaluate.score_one`` / ``evaluate.summarise``
(kit/evaluate.py:44, 87).

Switches:
    accept_semantics=gate|spike   -> MiniSeller -> ViewRef   (default: spike)
    echo_alloc=at_most|exact      -> MiniSeller              (default: at_most)
    every other key               -> Config.from_switches    (raises if unknown)

Spike-equivalent defaults: partial_bid_policy=matched, accept_semantics=spike,
echo_alloc=at_most.

No network. This module must not import verity.seller/state/parser/gate/arena.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime
import functools
import json
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "kit"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(KIT) not in sys.path:
    sys.path.insert(0, str(KIT))

import evaluate  # noqa: E402  (kit/evaluate.py; exposes kit/buyers.py as evaluate.public_buyers)

from experiments.mini_seller import MiniSeller  # noqa: E402
from verity.config import Config  # noqa: E402

RUNNER_KEYS = ("accept_semantics", "echo_alloc")
DEFAULT_SWITCHES: Dict[str, str] = {"accept_semantics": "spike", "echo_alloc": "at_most"}
ACCEPT_SEMANTICS = ("gate", "spike")
ECHO_ALLOC = ("at_most", "exact")


# ---------------------------------------------------------------------------
# Switches
# ---------------------------------------------------------------------------

def parse_switches(spec: str) -> Tuple[Config, str, str]:
    """Split a switch list into (Config, accept_semantics, echo_alloc).

    ``accept_semantics`` and ``echo_alloc`` belong to MiniSeller; everything
    else is re-serialised for ``Config.from_switches``, which raises on
    unknown keys (verity/config.py:44-46).
    """
    runner = dict(DEFAULT_SWITCHES)
    config_pairs: List[str] = []
    for pair in (spec or "").split(","):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            raise ValueError(f"Malformed switch (expected key=val): {pair!r}")
        key, _, value = pair.partition("=")
        key, value = key.strip(), value.strip()
        if key in RUNNER_KEYS:
            runner[key] = value
        else:
            config_pairs.append(f"{key}={value}")

    if runner["accept_semantics"] not in ACCEPT_SEMANTICS:
        raise ValueError(
            f"accept_semantics must be 'gate' or 'spike', got {runner['accept_semantics']!r}"
        )
    if runner["echo_alloc"] not in ECHO_ALLOC:
        raise ValueError(
            f"echo_alloc must be 'at_most' or 'exact', got {runner['echo_alloc']!r}"
        )
    cfg = Config.from_switches(",".join(config_pairs))
    return cfg, runner["accept_semantics"], runner["echo_alloc"]


# ---------------------------------------------------------------------------
# One seed
# ---------------------------------------------------------------------------

def run_seed(seed: int, switches: str, n: int = 210):
    """Play one seed exactly as evaluate.py would; return (summary, results, buyers)."""
    cfg, accept_semantics, echo_alloc = parse_switches(switches)
    store, policy = evaluate.load_store(), evaluate.load_policy()
    buyer_classes = evaluate.public_buyers.BUYERS
    scenarios = evaluate.public_buyers.make_scenarios(store, policy, n, seed, buyer_classes)
    # evaluate.run calls seller_cls(store, policy) (kit/evaluate.py:70), so the
    # per-run switches travel through functools.partial.
    seller_cls = functools.partial(
        MiniSeller,
        cfg=cfg,
        accept_semantics=accept_semantics,
        echo_alloc=echo_alloc,
    )
    results, _transcripts, _times = evaluate.run(
        seller_cls, scenarios, buyer_classes, store, policy, 1
    )
    return evaluate.summarise(results), results, buyer_classes


def _per_buyer(results, buyer_classes) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for name in buyer_classes:
        rows = [r for r in results if r["buyer"] == name]
        if not rows:
            continue
        t = evaluate.summarise(rows)
        out[name] = {
            "n": t["n"],
            "deal_rate": t["deal_rate"],
            "margin_kept": t["margin_kept"],
            "value": t["value"],
            "policy_violations": t["policy"],
            "truth_violations": t["truth"],
            "violations": t["policy"] + t["truth"],
            "deadlocks": t["deadlocks"],
            "score": t["score"],
        }
    return out


def seed_payload(summary, results, buyer_classes) -> dict:
    """The per-seed JSON body (Dev3 owns the final schema; this is a first version)."""
    deals = [r for r in results if r["deal"]]
    return {
        "score": summary["score"],
        "n": summary["n"],
        "deal_rate": summary["deal_rate"],
        "value_per_negotiation": summary["value"],
        "value_among_deals": statistics.mean(r["value"] for r in deals) if deals else 0.0,
        "margin_kept": summary["margin_kept"],
        "violations": {
            "policy": summary["policy"],
            "truth": summary["truth"],
            "kinds": summary["kinds"],
        },
        "deadlocks": summary["deadlocks"],
        "per_buyer": _per_buyer(results, buyer_classes),
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_seed(seed: int, summary, results, buyer_classes) -> None:
    """Print the headline metrics and per-buyer table, like evaluate.py's main()."""
    print(f"\n=== seed {seed} ===")
    print(f"negotiations        {summary['n']}   "
          f"({summary['feasible']} where a compliant deal existed)")
    print(f"deal rate           {summary['deal_rate']:.3f}   "
          f"where possible {summary['feasible_deal_rate']:.3f}")
    print(f"margin kept         {summary['margin_kept']:.3f}   "
          f"(share of list-price profit, on deals)")
    print(f"value               {summary['value']:.3f}   "
          f"(deal rate and margin together)")
    print(f"policy violations   {summary['policy']}")
    print(f"truth violations    {summary['truth']}")
    for kind, count in sorted(summary["kinds"].items()):
        print(f"    {kind:28} {count}")
    print(f"deadlocks           {summary['deadlocks']}")
    print(f"SCORE               {summary['score']:.1f}")

    print("\nby buyer                n   deals  margin  value  policy  truth  deadlocks  score")
    for name in buyer_classes:
        rows = [r for r in results if r["buyer"] == name]
        if rows:
            t = evaluate.summarise(rows)
            print(f"  {name:20} {t['n']:4}   {t['deal_rate']:.2f}   "
                  f"{t['margin_kept']:.2f}   {t['value']:.2f}  "
                  f"{t['policy']:6} {t['truth']:6} {t['deadlocks']:9}  {t['score']:6.1f}")


def git_short_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return "nogit"
    sha = out.stdout.decode("utf-8", "replace").strip()
    return sha if out.returncode == 0 and sha else "nogit"


def output_path(out_dir: Path, label: str) -> Path:
    """A new path under out_dir; never overwrites an existing file."""
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    stem = f"{stamp}_{git_short_sha()}_local_{label}"
    k = 1
    while True:
        path = out_dir / (f"{stem}.json" if k == 1 else f"{stem}_{k}.json")
        if not path.exists():
            return path
        k += 1


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    base, suffix, k = path.stem, path.suffix, 0
    while True:
        candidate = path if k == 0 else path.with_name(f"{base}_{k + 1}{suffix}")
        try:
            with open(candidate, "x", encoding="utf-8") as fh:  # 'x': exclusive create
                json.dump(payload, fh, indent=2, sort_keys=True)
                fh.write("\n")
            return
        except FileExistsError:
            # Someone created it between the check and the open: take the next name.
            k += 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Run MiniSeller on evaluate.py's scenarios.")
    ap.add_argument("--switches", default="",
                    help="k=v,k=v; accept_semantics/echo_alloc go to MiniSeller, the rest to Config")
    ap.add_argument("--seeds", default="0", help="comma-separated seeds, e.g. 1,2,3")
    ap.add_argument("--n", type=int, default=210, help="negotiations per seed")
    ap.add_argument("--out", default=str(ROOT / "results"), help="JSON output directory")
    ap.add_argument("--label", default="default", help="label in the JSON filename")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    if not seeds:
        raise SystemExit("--seeds needs at least one integer")

    cfg, accept_semantics, echo_alloc = parse_switches(args.switches)  # fail fast

    per_seed: Dict[str, dict] = {}
    for seed in seeds:
        summary, results, buyer_classes = run_seed(seed, args.switches, args.n)
        per_seed[str(seed)] = seed_payload(summary, results, buyer_classes)
        print_seed(seed, summary, results, buyer_classes)

    mean_score = statistics.mean(p["score"] for p in per_seed.values())
    print(f"\nmean SCORE over seeds {','.join(str(s) for s in seeds)}   {mean_score:.1f}")

    payload = {
        "switches": {
            "spec": args.switches,
            "accept_semantics": accept_semantics,
            "echo_alloc": echo_alloc,
            "config": dataclasses.asdict(cfg),
        },
        "seeds": seeds,
        "n": args.n,
        "per_seed": per_seed,
        "mean_score": mean_score,
    }
    path = output_path(Path(args.out), args.label)
    write_json(path, payload)
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
