"""Run kit/evaluate.py for a seller + seeds as a subprocess, parse the printout, write results JSON.
Black box: never imports verity. Python 3.9, stdlib only.
  python arena/scoreboard.py --seller seller_spike.py --seeds 0 --label spike
"""
import argparse, datetime, json, os, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KIT = ROOT / "kit"
NUM = r"(-?\d+(?:\.\d+)?)"
LINES = {  # evaluate.py prints these (evaluate.py:~148-165)
    "score": r"^SCORE\s+" + NUM, "deal_rate": r"^deal rate\s+" + NUM,
    "margin_kept": r"^margin kept\s+" + NUM, "value_per_negotiation": r"^value\s+" + NUM,
    "policy": r"^policy violations\s+(\d+)", "truth": r"^truth violations\s+(\d+)",
    "deadlocks": r"^deadlocks\s+(\d+)", "n_negotiations": r"^negotiations\s+(\d+)",
}
BUYER = re.compile(r"^\s+(\w+)\s+\d+\s+" + NUM + r"\s+" + NUM + r"\s+" + NUM + r"\s+\d+\s+\d+\s+\d+\s+" + NUM + r"\s*$")


def git_sha():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT),
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "nogit"


def parse(out):
    d = {}
    for key, pat in LINES.items():
        m = re.search(pat, out, re.M)
        if not m:
            raise ValueError("could not parse '%s' from evaluate.py output:\n%s" % (key, out))
        d[key] = float(m.group(1)) if "." in m.group(1) else int(m.group(1))
    d["by_buyer"] = {m.group(1): float(m.group(5)) for m in map(BUYER.match, out.splitlines()) if m}
    return d


# kit/harness.py load_class() splits the path on ":" so absolute Windows paths (C:\...) break;
# pass paths relative to kit/ (same drive) instead.
def run_seed(seller, seed, n, buyers, impl, switches):
    env = dict(os.environ)
    if impl: env["VERITY_IMPL"] = impl
    if switches: env["VERITY_SWITCHES"] = switches
    cmd = [sys.executable, "evaluate.py", "--seller", os.path.relpath(str(Path(seller).resolve()), str(KIT)), "--seed", str(seed),
           "--n", str(n), "--no-baseline"]
    if buyers: cmd += ["--buyers", os.path.relpath(str(Path(buyers).resolve()), str(KIT))]
    p = subprocess.run(cmd, cwd=str(KIT), env=env, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr or p.stdout)
    return parse(p.stdout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seller", required=True)
    ap.add_argument("--seeds", default="0")
    ap.add_argument("--n", type=int, default=210)
    ap.add_argument("--buyers", help="module defining BUYERS (default: kit buyers.py)")
    ap.add_argument("--impl"); ap.add_argument("--switches")
    ap.add_argument("--label", default="run")
    ap.add_argument("--out", default=str(ROOT / "results"))
    a = ap.parse_args()
    seeds = [int(s) for s in a.seeds.split(",")]
    per = {str(s): run_seed(a.seller, s, a.n, a.buyers, a.impl, a.switches) for s in seeds}
    sw = dict(kv.split("=", 1) for kv in a.switches.split(",")) if a.switches else {}
    res = {"git_sha": git_sha(), "label": a.label, "seller": a.seller, "impl": a.impl, "switches": sw,
           "seeds": seeds, "per_seed": per, "round10": [], "n_negotiations": a.n}
    Path(a.out).mkdir(parents=True, exist_ok=True)
    f = Path(a.out) / ("%s_%s_%s.json" % (datetime.date.today().strftime("%Y%m%d"), res["git_sha"], a.label))
    if f.exists():
        sys.exit("refusing to overwrite " + str(f))  # results/ is append-only
    f.write_text(json.dumps(res, indent=1))
    for s, d in per.items():
        print("seed %s: score %.1f  deals %.3f  policy %d  truth %d  deadlocks %d  %s" % (
            s, d["score"], d["deal_rate"], d["policy"], d["truth"], d["deadlocks"], d["by_buyer"]))
    print("wrote", f)


if __name__ == "__main__":
    main()
