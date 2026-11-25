"""Tune-free persona evaluation: each seller vs each persona separately, plus mean when one persona is left out,
plus how many LLM outputs were malformed. No parameter is fitted on these runs.
  python arena/personas/leave_one_persona_out.py --dry-run
  python arena/personas/leave_one_persona_out.py --sellers seller_spike.py,kit/example_seller.py"""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_personas as P  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sellers", default="kit/example_seller.py,seller_spike.py")
    ap.add_argument("--per-persona", type=int, default=30)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default=str(P.ROOT / "results"))
    a = ap.parse_args()
    raw = P.setup(a.dry_run)
    per = 5 if a.dry_run else a.per_persona
    P.R.check_seeds([a.seed])
    names = P.PERSONAS
    md = ["# Persona evaluation (tune-free)%s" % (" \u2014 DRY RUN, fake provider" if a.dry_run else ""), "",
          "| seller | " + " | ".join(names) + " | all | " + " | ".join("w/o " + n for n in names) + " | malformed/calls |",
          "|---|" + "---|" * (2 * len(names) + 2)]
    for s in a.sellers.split(","):
        label = "lopo_%s%s" % (Path(s).stem, "_dry" if a.dry_run else "")
        res, st = P.run_one(str(P.ROOT / s), None, None, per, a.seed, label, raw)
        P.R.write_json(res, label, a.out)
        d = res["per_seed"][str(a.seed)]["by_buyer"]
        allm = sum(d.values()) / len(d)
        loo = [(sum(d.values()) - d[n]) / (len(d) - 1) for n in names]
        bad, calls = sum(v["malformed"] for v in st.values()), sum(v["calls"] for v in st.values())
        md.append("| %s | %s | %.1f | %s | %d/%d |" % (s, " | ".join("%.1f" % d[n] for n in names), allm,
                                                       " | ".join("%.1f" % x for x in loo), bad, calls))
    text = "\n".join(md) + "\n"
    f = Path(a.out) / ("lopo%s.md" % ("_dry" if a.dry_run else ""))
    f.write_text(text, encoding="utf-8")
    print(text); print("wrote", f)


if __name__ == "__main__":
    main()
