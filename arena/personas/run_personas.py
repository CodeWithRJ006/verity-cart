"""Run a seller against the 5 LLM personas (30 negotiations each by default). Resumable: every LLM call is cached.
  python arena/personas/run_personas.py --seller seller_spike.py --dry-run          # fake provider, no network
  set ARENA_PROVIDER=gemini & set GEMINI_API_KEY=... & python arena/personas/run_personas.py --seller seller_spike.py
Reported separately from the official run. Real-run notes: arena/personas/README.md"""
import argparse, json, os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "arena"))
import run_arena as R  # noqa: E402

PERSONAS = ("anchorer", "competitor", "injector", "pressurer", "terse")


def raw_stats(path, offset):
    """Unique LLM calls since `offset` bytes: {persona: {calls, malformed, leaks}} (cached repeats not double counted)."""
    out, seen = {p: {"calls": 0, "malformed": 0, "leaks": 0} for p in PERSONAS}, set()
    if not Path(path).exists():
        return out
    with open(path, "rb") as fh:
        fh.seek(offset)
        for line in fh.read().decode("utf-8").splitlines():
            d = json.loads(line)
            k = (d["persona"], d["seed"], d["round"], d["raw"])
            if k in seen: continue
            seen.add(k)
            o = out[d["persona"]]; o["calls"] += 1; o["malformed"] += d["malformed"]; o["leaks"] += d["leak"]
    return out


def setup(dry):
    if dry:
        os.environ.update(ARENA_PROVIDER="fake", ARENA_CACHE=str(ROOT / "results" / "personas_cache_dry"),
                          ARENA_RAW=str(ROOT / "results" / "personas_raw_dry.jsonl"))
    elif os.environ.get("ARENA_PROVIDER", "fake") == "fake":
        raise SystemExit("set ARENA_PROVIDER=gemini|openrouter|ollama for a real run, or pass --dry-run")
    return Path(os.environ.get("ARENA_RAW", str(ROOT / "results" / "personas_raw.jsonl")))


def run_one(seller, impl, switches, per, seed, label, raw):
    off = raw.stat().st_size if raw.exists() else 0
    res = R.execute(seller, [seed], "personas", per * len(PERSONAS), impl, switches, label)
    return res, raw_stats(raw, off)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seller", required=True)
    ap.add_argument("--impl", choices=["stub", "real", "baseline"])
    ap.add_argument("--switches")
    ap.add_argument("--per-persona", type=int, default=30)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--label", default=None)
    ap.add_argument("--dry-run", action="store_true", help="fake provider, 5 negotiations per persona, no network")
    ap.add_argument("--out", default=str(ROOT / "results"))
    a = ap.parse_args()
    raw = setup(a.dry_run)
    per = 5 if a.dry_run else a.per_persona
    R.check_seeds([a.seed])
    label = a.label or ("personas_%s%s" % (Path(a.seller).stem, "_dry" if a.dry_run else ""))
    try:
        res, st = run_one(a.seller, a.impl, a.switches, per, a.seed, label, raw)
    except RuntimeError as e:
        if "QuotaExceeded" in str(e):
            raise SystemExit("quota reached: %s\nRe-run the same command later; cached calls are free." % e)
        raise
    res["llm"] = {"provider": os.environ.get("ARENA_PROVIDER", "fake"), "model": os.environ.get("ARENA_MODEL", ""), "calls": st}
    f = R.write_json(res, label, a.out)
    d = res["per_seed"][str(a.seed)]
    print("persona        score  malformed/calls  leaks")
    for p in PERSONAS:
        print("%-12s %7.1f  %6d/%-6d %5d" % (p, d["by_buyer"].get(p, float("nan")), st[p]["malformed"], st[p]["calls"], st[p]["leaks"]))
    print("overall score %.1f  policy %d  truth %d  deadlocks %d\nwrote %s" % (d["score"], d["policy"], d["truth"], d["deadlocks"], f))


if __name__ == "__main__":
    main()
