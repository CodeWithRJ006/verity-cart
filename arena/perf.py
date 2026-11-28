"""Latency and memory of a seller: p50/p95/max ms per Seller.respond over 210 negotiations x 3 public buyers.
Pass 1 times respond() with time.perf_counter; pass 2 re-runs under tracemalloc for peak memory.
  python arena/perf.py --seller seller_spike.py --label spike
  python arena/perf.py --seller seller_verity.py --impl real --label verity
Runs in-process (needs the timing hook); never imports verity itself. Writes results/<date>_<sha>_perf_<label>_<HHMMSS>.json."""
import argparse
import datetime
import json
import os
import random
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
KIT = ROOT / "kit"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(KIT))
import buyers as B  # noqa: E402
import run_arena as R  # noqa: E402
from harness import load_class, load_policy, load_store, run_negotiation  # noqa: E402


class Timed:
    def __init__(self, seller):
        self.seller, self.times, self.tag = seller, [], None

    def start(self, negotiation_id):
        self.seller.start(negotiation_id)

    def respond(self, message):
        t0 = time.perf_counter()
        try:
            return self.seller.respond(message)
        finally:
            self.times.append((self.tag, time.perf_counter() - t0))


def play(seller_cls, store, policy, seed, n):
    scenarios = B.make_scenarios(store, policy, n, seed, B.BUYERS)
    t0 = time.perf_counter()
    seller = Timed(seller_cls(store, policy))
    construct_ms = 1000 * (time.perf_counter() - t0)
    for sc in scenarios:
        seller.tag = sc["buyer"]
        buyer = B.BUYERS[sc["buyer"]](sc, store, random.Random(sc["seed"]))
        run_negotiation(seller, buyer, store, policy, sc["id"])
    return seller.times, construct_ms


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * (len(xs) - 1) + 0.5))]


def summary(ms):
    return {"calls": len(ms), "p50_ms": round(pct(ms, 0.5), 4), "p95_ms": round(pct(ms, 0.95), 4),
            "max_ms": round(max(ms), 4), "mean_ms": round(statistics.mean(ms), 4)}


def peak_rss_mb():
    try:
        import resource
    except ImportError:  # Windows has no resource module
        return None
    v = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(v / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seller", required=True)
    ap.add_argument("--impl", choices=["stub", "real", "baseline"])
    ap.add_argument("--switches")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--n", type=int, default=210)
    ap.add_argument("--label", default="perf")
    ap.add_argument("--out", default=str(ROOT / "results"))
    a = ap.parse_args()
    for k in [k for k in os.environ if k.startswith("VERITY_")]:
        del os.environ[k]
    if a.impl:
        os.environ["VERITY_IMPL"] = a.impl
    if a.switches:
        os.environ["VERITY_SWITCHES"] = a.switches
    store, policy = load_store(), load_policy()
    rel = R.rel(a.seller)  # kit's load_class breaks on absolute Windows paths; resolve relative to kit/
    os.chdir(KIT)
    seller_cls = load_class(rel, "Seller")
    times, construct_ms = play(seller_cls, store, policy, a.seed, a.n)
    ms = [1000 * t for _, t in times]
    by = {b: summary([1000 * t for tag, t in times if tag == b]) for b in sorted({tag for tag, _ in times})}
    tracemalloc.start()
    play(seller_cls, store, policy, a.seed, a.n)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    res = {"git_sha": R.git_sha(), "label": a.label, "seller": a.seller, "impl": a.impl, "seed": a.seed,
           "n_negotiations": a.n, "overall": summary(ms), "by_buyer": by, "construct_ms": round(construct_ms, 3),
           "peak_python_mb": round(peak / 1e6, 2), "peak_rss_mb": peak_rss_mb(), "python": sys.version.split()[0],
           "platform": sys.platform}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    f = out / ("%s_%s_perf_%s.json" % (stamp, res["git_sha"], a.label))
    f.write_text(json.dumps(res, indent=1, sort_keys=True))
    o = res["overall"]
    print("%d respond() calls: p50 %.3f ms  p95 %.3f ms  max %.3f ms  mean %.3f ms" % (o["calls"], o["p50_ms"], o["p95_ms"], o["max_ms"], o["mean_ms"]))
    print("peak python memory %.2f MB, peak RSS %s MB, construct %.2f ms" % (res["peak_python_mb"], res["peak_rss_mb"], construct_ms))
    print("wrote", f)


if __name__ == "__main__":
    main()
