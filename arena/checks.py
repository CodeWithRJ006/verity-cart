"""arena/checks.py - metamorphic / twin / session detectors (Dev3). Never imports verity.

Each returns (runs, mismatches); a safe seller has 0 mismatches.
  python arena/checks.py --seller seller_spike.py"""
import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from arena import driver as d  # noqa: E402


def metamorphic(seller_path, scripts=None, variants=None):
    """Same structured bids, text rewritten 100 ways: seller's (type, items) per turn must not change."""
    cls = d.load_seller_class(seller_path)
    scripts = scripts if scripts is not None else d.family_scripts()
    variants = variants if variants is not None else d.text_variants(100)
    runs = bad = 0
    for si, script in enumerate(scripts):
        ref = d.seller_view(d.run(cls, d.ScriptedBuyer(script), "m%d" % si))
        for v in variants:
            got = d.seller_view(d.run(cls, d.ScriptedBuyer(script, lambda i, t, v=v: v), "m%d" % si))
            runs += 1
            bad += got != ref
    return runs, bad


def twin(seller_path, scripts=None):
    """Two independent Seller instances, same structured bids: identical outputs (incl. text)."""
    cls = d.load_seller_class(seller_path)
    scripts = scripts if scripts is not None else d.family_scripts()
    runs = bad = 0
    for si, script in enumerate(scripts):
        a = d.seller_full(d.run(d.new_seller(cls), d.ScriptedBuyer(script), "t%d" % si))
        b = d.seller_full(d.run(d.new_seller(cls), d.ScriptedBuyer(script), "t%d" % si))
        runs += 1
        bad += a != b
    return runs, bad


def session_reuse(seller_path, scripts=None, reps=10, seed=0):
    """One Seller object over len(scripts)*reps negotiations (shuffled, sequential) == fresh process each time."""
    scripts = scripts if scripts is not None else d.family_scripts()
    fresh = [d.seller_full(d.run(d.new_seller(d.load_seller_class(seller_path)), d.ScriptedBuyer(s), "s%d" % i))
             for i, s in enumerate(scripts)]
    order = [i for _ in range(reps) for i in range(len(scripts))]
    random.Random(seed).shuffle(order)
    seller = d.new_seller(d.load_seller_class(seller_path))
    runs = bad = 0
    for i in order:
        got = d.seller_full(d.run(seller, d.ScriptedBuyer(scripts[i]), "s%d" % i))
        runs += 1
        bad += got != fresh[i]
    return runs, bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seller", required=True)
    a = ap.parse_args()
    scripts = d.family_scripts()
    res = {"metamorphic": metamorphic(a.seller, scripts), "twin": twin(a.seller, scripts),
           "session_reuse": session_reuse(a.seller, scripts)}
    for k, (runs, bad) in res.items():
        print("%-14s negotiations=%-5d mismatches=%d" % (k, runs, bad))
    sys.exit(1 if any(b for _, b in res.values()) else 0)


if __name__ == "__main__":
    main()
