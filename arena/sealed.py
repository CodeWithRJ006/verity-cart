"""SEALED run: the frozen config on seeds 20-29, ONCE, on the v1.0-freeze tag. Writes results/sealed_<sha>.json.
  python arena/sealed.py --seller seller_verity.py --i-mean-it
Refuses unless: tag v1.0-freeze is on HEAD, --i-mean-it is given, and no sealed result or marker exists.
Runs the kit baseline on the same seeds in the same invocation, so one run gives both rows. Nothing is printed until
both rows finished (a crash leaves no marker and nothing observed)."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_arena as R  # noqa: E402
import stats  # noqa: E402

SEEDS = list(range(20, 30))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seller", default="seller_verity.py")
    ap.add_argument("--impl", choices=["stub", "real", "baseline"], help="default: the seller's own default (frozen config)")
    ap.add_argument("--switches")
    ap.add_argument("--buyers", default="public")
    ap.add_argument("--n", type=int, default=210)
    ap.add_argument("--out", default=str(R.ROOT / "results"))
    ap.add_argument("--i-mean-it", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    if list(out.glob("sealed_*.json")):
        sys.exit("a sealed result already exists in %s; the sealed run happens once" % out)
    R.check_seeds(SEEDS, a.i_mean_it)  # tag, marker and flag checks
    final = R.execute(a.seller, SEEDS, a.buyers, a.n, a.impl, a.switches, "sealed_final")
    base = R.execute("kit/example_seller.py", SEEDS, a.buyers, a.n, None, None, "sealed_baseline")
    cfg = R.ROOT / "verity" / "config.py"
    d, lo, hi = stats.paired_bootstrap(base["per_negotiation"], final["per_negotiation"])
    res = {"git_sha": R.git_sha(), "tag": R.FREEZE_TAG, "seeds": SEEDS, "buyers": a.buyers, "final": final, "baseline": base,
           "config_sha256": hashlib.sha256(cfg.read_bytes()).hexdigest() if cfg.exists() else None,
           "delta_vs_baseline": {"mean": d, "ci95": [lo, hi]}}
    f = out / ("sealed_%s.json" % res["git_sha"])
    out.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(res, indent=1, sort_keys=True))
    R.SEALED_MARK.write_text(json.dumps({"git_sha": res["git_sha"], "file": f.name}))
    print(stats.seed_table(final))
    print("\nbaseline per seed:", {s: round(p["score"], 1) for s, p in base["per_seed"].items()})
    print("final mean %.1f, baseline mean %.1f, paired diff %+.2f [%+.2f, %+.2f]" % (
        stats.pooled(final)["score"], stats.pooled(base)["score"], d, lo, hi))
    print("wrote", f, "\nSEALED run recorded; it cannot be repeated.")


if __name__ == "__main__":
    main()
