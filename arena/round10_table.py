"""Round-10 evidence table (guide section 5). Reads the `round10` records in results/*.json.
For each bin of dist_to_floor (how far the buyer's bid is below our floor, share of list) x bid rising:
n, accept rate p_hat, break-even p*. Bins with p_hat < p* are flagged: the final offer is worse than walking.
  p* = D*q / (V + D*q)   V = mean normalised value of a deal at the floor (computed from the kit scenarios),
  D = 0.25 deadlock penalty, q = share of rejected final offers that end in deadlock (--q, default 1 = worst case).
  python arena/round10_table.py [--files results/a.json,results/b.json] [--min-n 5]"""
import argparse, glob, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import run_arena as R  # noqa: E402
import buyers as B  # noqa: E402  (kit)
from harness import floor_price  # noqa: E402

BINS = [(-9, 0.0, "bid >= floor"), (0.0, 0.02, "0-2% below"), (0.02, 0.05, "2-5% below"), (0.05, 0.10, "5-10% below"), (0.10, 9, ">10% below")]
D = 0.25


def mean_value_at_floor(seed=0, n=210):
    store, policy = R.load_store(), R.load_policy()
    vals = []
    for s in B.make_scenarios(store, policy, n, seed):
        sell = [(store[i["sku"]], min(i["qty"], store[i["sku"]]["stock"])) for i in s["items"]]
        pot = sum(q * (r["price"] - r["cost"]) for r, q in sell)
        top = sum(q * r["price"] for r, q in sell)
        fl = sum(q * floor_price(r, policy) for r, q in sell)
        if pot > 0 and top > 0 and s["reservation"] * top >= fl:   # a compliant deal at the floor exists
            vals.append(sum(q * (floor_price(r, policy) - r["cost"]) for r, q in sell) / pot)
    return sum(vals) / len(vals)


def load(files):
    recs = []
    for f in files:
        d = json.load(open(f, encoding="utf-8"))
        runs = list(d["rows"].values()) if "rows" in d else [d]
        for r in runs:
            for x in r.get("round10", []):
                recs.append(dict(x, source=Path(f).name, label=r.get("label", "")))
    return recs


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--files", help="comma list; default: every results/*.json except dry-run and persona runs")
    ap.add_argument("--q", type=float, default=1.0)
    ap.add_argument("--min-n", type=int, default=5)
    ap.add_argument("--out", default=str(ROOT / "results" / "round10_table.md"))
    a = ap.parse_args()
    files = a.files.split(",") if a.files else sorted(f for f in glob.glob(str(ROOT / "results" / "*.json"))
                                                      if not any(k in f for k in ("_dry", "personas", "lopo")))
    recs = load(files)
    if not recs:
        sys.exit("no round10 records found")
    V = mean_value_at_floor()
    ps = D * a.q / (V + D * a.q)
    md = ["# Round-10 evidence", "",
          "Situation: the seller makes an offer in round 10 (its last turn). `dist_to_floor` = floor ratio minus the buyer's last bid ratio "
          "(share of list; positive = buyer still below our floor). `rising` = last bid higher than the one before.", "",
          "Break-even: V (mean value of a deal at the floor) = **%.3f**, D = %.2f, q = %.2f \u21d2 **p\\* = %.3f**. "
          "A bin with p\u0302 < p\\* means the final offer loses to walking away. Bins with n < %d are not judged." % (V, D, a.q, ps, a.min_n), "",
          "Records: %d from %d file(s). Seller behaviour differs across files, so read this together with the file list below." % (len(recs), len(files)), "",
          "| dist_to_floor | rising | n | accepted | p\u0302 | verdict |", "|---|---|---|---|---|---|"]
    for lo, hi, name in BINS:
        for rising in (True, False):
            b = [r for r in recs if lo < r["dist_to_floor"] <= hi and r["rising"] == rising]
            if not b:
                md.append("| %s | %s | 0 | \u2014 | \u2014 | no data |" % (name, "yes" if rising else "no")); continue
            acc = sum(r["accepted"] for r in b); p = acc / len(b)
            v = "n too small" if len(b) < a.min_n else ("\u26a0 p\u0302 < p* (walk instead)" if p < ps else "offer is right")
            md.append("| %s | %s | %d | %d | %.2f | %s |" % (name, "yes" if rising else "no", len(b), acc, p, v))
    md += ["", "Files: " + ", ".join(sorted({Path(f).name for f in files}))]
    Path(a.out).write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md)); print("wrote", a.out)


if __name__ == "__main__":
    main()
