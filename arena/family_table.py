"""Per-config table: baseline vs spike (score, deadlocks) over the 20 family configs.
Run from repo root:  python arena/family_table.py [--seed 0] [--n 30] [--attack none|on]
Paths passed to evaluate.py are RELATIVE to kit/ (Windows-safe). Never imports verity."""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KIT = ROOT / "kit"
sys.path.insert(0, str(ROOT))
from arena.family import build_family  # noqa: E402


def _f(v):
    return "ERR" if v is None else v


def run(seller_rel, name, seed, n, attack):
    env = dict(os.environ, FAMILY_ONLY=name)
    if attack == "on":
        env["FAMILY_ATTACK"] = "on"
    cmd = [sys.executable, "evaluate.py", "--seller", seller_rel, "--buyers", "../arena/family.py",
           "--seed", str(seed), "--n", str(n), "--no-baseline"]
    p = subprocess.run(cmd, cwd=str(KIT), env=env, capture_output=True, text=True)
    if p.returncode:
        return None, None, None
    sc = re.search(r"^SCORE\s+(-?[\d.]+)", p.stdout, re.M)
    dl = re.search(r"^deadlocks\s+(\d+)", p.stdout, re.M)
    pv = re.search(r"^policy violations\s+(\d+)", p.stdout, re.M)
    return float(sc.group(1)), int(dl.group(1)), int(pv.group(1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--attack", choices=["none", "on"], default="none")
    a = ap.parse_args()
    spike = "../seller_spike.py"
    print("%-22s %9s %7s %6s %6s %6s" % ("config", "baseline", "spike", "dl_b", "dl_s", "viol"))
    for cfg in build_family():
        name = cfg["name"] + ("+atk" if a.attack == "on" and not cfg["attack_style"] else "")
        base = run("example_seller.py", cfg["name"], a.seed, a.n, a.attack)
        spk = run(spike, cfg["name"], a.seed, a.n, a.attack)
        print("%-22s %9s %7s %6s %6s %6s" % (name, _f(base[0]), _f(spk[0]), _f(base[1]), _f(spk[1]),
                                            (base[2] or 0) + (spk[2] or 0) if base[2] is not None and spk[2] is not None else "ERR"))


if __name__ == "__main__":
    main()
