"""Ablation ladder A, B0, B, C, D (+ spike reference S) with identical seeds and buyers.
  python arena/ablate.py --seeds 1,2,3 --buyers public
Rows that cannot run yet (impl not merged, unknown switch) are reported as unavailable, not fatal."""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_arena as R  # noqa: E402
import stats  # noqa: E402

V = "seller_verity.py"
# name, description, seller, impl, switches
ROWS = [
    ("A", "Kit example seller (baseline)", "kit/example_seller.py", None, None),
    ("S", "Feasibility spike (reference)", "seller_spike.py", None, None),
    ("B0", "Gate+templates, baseline acceptance rule", V, "baseline", None),
    ("B", "P0 tuned, echo_buyer_total=false", V, "real", "echo_buyer_total=false"),
    ("C", "P0 with re-slice (echo_buyer_total=true)", V, "real", "echo_buyer_total=true"),
    ("D1", "C + allocator=proportional", V, "real", "echo_buyer_total=true,allocator=proportional"),
    ("D2", "C + allocator=greedy", V, "real", "echo_buyer_total=true,allocator=greedy"),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seeds", default="1,2,3")
    ap.add_argument("--buyers", default="public")
    ap.add_argument("--n", type=int, default=210)
    ap.add_argument("--rows", help="comma list, e.g. A,S,B0 (default all)")
    ap.add_argument("--out", default=str(R.ROOT / "results"))
    ap.add_argument("--i-mean-it", action="store_true")
    a = ap.parse_args()
    seeds = [int(x) for x in a.seeds.split(",")]
    kind = R.check_seeds(seeds, a.i_mean_it)
    want = a.rows.split(",") if a.rows else [r[0] for r in ROWS]
    done, table = {}, []
    for name, desc, seller, impl, sw in ROWS:
        if name not in want:
            continue
        try:
            res = R.execute(str(R.ROOT / seller), seeds, a.buyers, a.n, impl, sw, "abl_" + name)
            done[name] = res; table.append((name, desc, res, None))
        except (RuntimeError, SystemExit) as e:
            table.append((name, desc, None, str(e)))
        print("row %-2s %s" % (name, "ok" if name in done else "UNAVAILABLE: " + table[-1][3][:100]))
    md = stats.ladder_markdown(table, "A", "Ablation ladder (%s seeds %s, buyers %s)" % (kind, a.seeds, a.buyers))
    stem = "ablation_%s_%s" % (a.buyers.replace("/", "_").replace("\\", "_"), a.seeds.replace(",", "-"))
    first = next(iter(done.values()), None)
    f = R.write_json({"git_sha": R.git_sha(), "label": stem, "seeds": seeds, "buyers": a.buyers, "rows": done}, stem, a.out)
    m = f.with_suffix(".md")
    if m.exists() and m.read_text(encoding="utf-8") != md:
        raise SystemExit("ablation markdown differs from existing %s (non-determinism?)" % m)
    m.write_text(md, encoding="utf-8")
    print(md)
    print("wrote", f, "and", m.name)
    if kind == "sealed":
        R.SEALED_MARK.write_text('{"git_sha": "%s", "label": "%s"}' % (R.git_sha(), stem))


if __name__ == "__main__":
    main()
