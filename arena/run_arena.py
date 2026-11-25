"""Official arena runner. Drives kit/evaluate.py as a subprocess (never imports verity).
  python arena/run_arena.py --seller seller_spike.py --seeds 1,2,3 --buyers public --label spike
  python arena/run_arena.py --seller seller_verity.py --impl real --switches echo_buyer_total=false --seeds 0,7,8,9
--impl / --switches become VERITY_IMPL / VERITY_SWITCHES for the subprocess. Python 3.9, stdlib only."""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
KIT = ROOT / "kit"
sys.path.insert(0, str(KIT))
from harness import floor_price, load_policy, load_store  # kit helper, not verity  # noqa: E402

TUNE, DEV, SEALED = {1, 2, 3}, {0, 7, 8, 9}, set(range(20, 30))
SEALED_MARK = ROOT / "results" / "SEALED_RUN.json"
FREEZE_TAG = "v1.0-freeze"


def git(*a):
    try:
        return subprocess.check_output(["git"] + list(a), cwd=str(ROOT), stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return ""


def git_sha():
    return git("rev-parse", "--short", "HEAD") or "nogit"


def check_seeds(seeds, i_mean_it=False):
    """Seed protocol (Handbook 1.1 E). TUNE {1,2,3}, DEV-EVAL {0,7,8,9}, SEALED {20..29}; sets never mixed with SEALED."""
    s = set(seeds)
    if not s <= (TUNE | DEV | SEALED):
        raise SystemExit(
            "seeds outside the protocol (TUNE %s, DEV-EVAL %s, SEALED 20-29): %s"
            % (sorted(TUNE), sorted(DEV), sorted(s - (TUNE | DEV | SEALED)))
        )
    if s & SEALED:
        if s - SEALED:
            raise SystemExit("SEALED seeds cannot be mixed with other seeds")
        if SEALED_MARK.exists():
            raise SystemExit("SEALED run already happened: %s" % SEALED_MARK)
        if FREEZE_TAG not in git("tag", "--points-at", "HEAD").split():
            raise SystemExit("SEALED needs git tag %s checked out" % FREEZE_TAG)
        if not i_mean_it:
            raise SystemExit("SEALED needs --i-mean-it")
        return "sealed"
    return "tune" if s <= TUNE else "dev"


def rel(p):
    try:  # kit's load_class splits on ':' so absolute Windows paths break; stay relative to kit/
        return os.path.relpath(str(Path(p).resolve()), str(KIT))
    except ValueError:
        return str(Path(p).resolve())


def buyers_arg(spec):
    if spec == "public":
        return None
    if spec == "family":
        f = HERE / "family.py"
        if not f.exists() or "BUYERS" not in f.read_text(encoding="utf-8"):
            raise SystemExit("arena/family.py must exist and define a BUYERS dict (evaluate.py --buyers contract)")
        return rel(f)
    if spec == "personas":
        if "ARENA_PROVIDER" not in os.environ:
            raise SystemExit("set ARENA_PROVIDER explicitly (fake|gemini|openrouter|ollama); or use personas/run_personas.py")
        return rel(HERE / "personas" / "persona_buyers.py")
    return rel(spec)


def _ratio(items, basket):
    num = den = 0
    for it in items or []:
        try:
            if it["sku"] in basket and isinstance(it["unit_price"], (int, float)) and not isinstance(it["unit_price"], bool):
                num += it["qty"] * it["unit_price"]
                den += it["qty"] * basket[it["sku"]][0]
        except (KeyError, TypeError):
            pass
    return num / den if den else None


def round10_record(row, store, policy):
    """Seller's round-10 situation: how far the buyer's bid is below our floor (share of list), is it rising,
    was our round-10 offer accepted. None unless the seller made an offer in round 10."""
    tr = row["transcript"]
    s10 = next((m for m in tr if m["from"] == "seller" and m.get("round") == 10), None)
    first = next((m for m in tr if m["from"] == "seller" and m.get("type") == "offer"), None)
    if not s10 or s10.get("type") != "offer" or not first:
        return None
    basket = {
        i["sku"]: (store[i["sku"]]["price"], floor_price(store[i["sku"]], policy)) for i in first["items"] if i["sku"] in store
    }
    bids = [
        _ratio(m.get("items"), basket)
        for m in tr
        if m["from"] == "buyer" and m.get("round", 99) <= 10 and m.get("type") in ("request", "counter")
    ]
    bids = [b for b in bids if b is not None]
    if not bids:
        return None
    L = sum(i["qty"] * basket[i["sku"]][0] for i in first["items"] if i["sku"] in basket)
    F = sum(i["qty"] * basket[i["sku"]][1] for i in first["items"] if i["sku"] in basket)
    accepted = any(m["from"] == "buyer" and m.get("round") == 11 and m.get("type") == "accept" for m in tr)
    return {
        "dist_to_floor": round(F / L - bids[-1], 4),
        "rising": len(bids) > 1 and bids[-1] > bids[-2],
        "accepted": accepted,
        "buyer": row["buyer"],
    }


def metrics(rows):
    deals = [r for r in rows if r["deal"]]

    def mean(xs):
        return sum(xs) / len(xs) if xs else 0.0

    by = {}
    for r in rows:
        by.setdefault(r["buyer"], []).append(r["score"])
    return {
        "score": 100 * mean([r["score"] for r in rows]),
        "deal_rate": len(deals) / len(rows),
        "value_per_negotiation": mean([r["value"] for r in rows]),
        "value_among_deals": mean([r["value"] for r in deals]),
        "margin_kept": mean([r["margin_kept"] for r in deals]),
        "policy": sum(r["policy_violations"] for r in rows),
        "truth": sum(r["truth_violations"] for r in rows),
        "deadlocks": sum(r["deadlock"] for r in rows),
        "by_buyer": {k: 100 * mean(v) for k, v in sorted(by.items())},
        "n": len(rows),
    }


def run_seed(seller, seed, n, buyers, impl, switches, store, policy, keep=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("VERITY_")}
    if impl:
        env["VERITY_IMPL"] = impl
    if switches:
        env["VERITY_SWITCHES"] = switches
    with tempfile.TemporaryDirectory() as td:
        log = Path(keep) if keep else Path(td) / "log.jsonl"
        cmd = [
            sys.executable,
            "evaluate.py",
            "--seller",
            rel(seller),
            "--seed",
            str(seed),
            "--n",
            str(n),
            "--no-baseline",
            "--log",
            str(log),
        ]
        if buyers:
            cmd += ["--buyers", buyers]
        p = subprocess.run(cmd, cwd=str(KIT), env=env, capture_output=True, text=True)
        if p.returncode:
            raise RuntimeError((p.stderr or p.stdout).strip().splitlines()[-1][:300])
        rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]
    m = metrics(rows)
    printed = re.search(r"^SCORE\s+(-?\d+(?:\.\d+)?)", p.stdout, re.M)
    if not printed or abs(float(printed.group(1)) - m["score"]) > 0.06:  # cross-check log-derived vs printed score
        raise RuntimeError("score mismatch: log %.2f vs printed %s" % (m["score"], printed and printed.group(1)))
    per_neg = {"%d:%s" % (seed, r["id"]): 100 * r["score"] for r in rows}
    r10 = [x for x in (round10_record(r, store, policy) for r in rows) if x]
    for x in r10:
        x["seed"] = seed
    return m, per_neg, r10


def execute(seller, seeds, buyers="public", n=210, impl=None, switches=None, label="run", keep_logs=None):
    store, policy = load_store(), load_policy()
    barg = buyers_arg(buyers)
    per, pn, r10 = {}, {}, []
    for s in seeds:
        keep = None
        if keep_logs:
            Path(keep_logs).mkdir(parents=True, exist_ok=True)
            keep = str(Path(keep_logs) / ("%s_seed%d.jsonl" % (label, s)))
        m, d, r = run_seed(seller, s, n, barg, impl, switches, store, policy, keep)
        per[str(s)] = m
        pn.update(d)
        r10 += r
    sw = dict(kv.split("=", 1) for kv in switches.split(",")) if switches else {}
    return {
        "git_sha": git_sha(),
        "label": label,
        "seller": str(seller),
        "impl": impl,
        "switches": sw,
        "buyers": buyers,
        "seeds": list(seeds),
        "per_seed": per,
        "per_negotiation": pn,
        "round10": r10,
        "n_negotiations": n,
    }


def write_json(obj, stem, out):
    """Append-only: same name + identical content is fine (proves determinism); different content is an error."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    f = out / ("%s_%s_%s.json" % (datetime.date.today().strftime("%Y%m%d"), obj["git_sha"], stem))
    text = json.dumps(obj, indent=1, sort_keys=True)
    if f.exists():
        if f.read_text() != text:
            raise SystemExit("results are append-only and %s exists with DIFFERENT numbers (non-determinism?)" % f)
        print("identical to existing", f)
    else:
        f.write_text(text)
    return f


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seller", required=True)
    ap.add_argument("--impl", choices=["stub", "real", "baseline"])
    ap.add_argument("--switches")
    ap.add_argument("--seeds", default="1,2,3")
    ap.add_argument("--buyers", default="public", help="public | family | personas | path/to/module.py")
    ap.add_argument("--n", type=int, default=210)
    ap.add_argument("--label", default="run")
    ap.add_argument("--out", default=str(ROOT / "results"))
    ap.add_argument("--keep-logs", help="folder to keep full transcripts (one JSONL per seed)")
    ap.add_argument("--i-mean-it", action="store_true")
    a = ap.parse_args()
    seeds = [int(x) for x in a.seeds.split(",")]
    kind = check_seeds(seeds, a.i_mean_it)
    res = execute(a.seller, seeds, a.buyers, a.n, a.impl, a.switches, a.label, a.keep_logs)
    res["seed_set"] = kind
    f = write_json(res, a.label, a.out)
    for s, d in res["per_seed"].items():
        print(
            "seed %s: score %.1f deals %.3f v/neg %.3f v/deal %.3f policy %d truth %d deadlocks %d %s"
            % (
                s,
                d["score"],
                d["deal_rate"],
                d["value_per_negotiation"],
                d["value_among_deals"],
                d["policy"],
                d["truth"],
                d["deadlocks"],
                {k: round(v, 1) for k, v in d["by_buyer"].items()},
            )
        )
    print("wrote", f)
    if kind == "sealed":
        SEALED_MARK.write_text(json.dumps({"git_sha": res["git_sha"], "label": a.label, "file": f.name}))
        print("SEALED run recorded; it cannot be repeated.")


if __name__ == "__main__":
    main()
