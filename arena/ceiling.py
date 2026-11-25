import collections
import os
import re
import statistics
import sys

KIT = (
    sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "kit")
)  # starter-kit folder
sys.path.insert(0, KIT)
import buyers as B  # noqa: E402
from harness import floor_price, load_policy, load_store  # noqa: E402

store, policy = load_store(), load_policy()
sc = B.make_scenarios(store, policy, 210, 0)
by = collections.defaultdict(list)
for s in sc:
    sell = [(store[i["sku"]], min(i["qty"], store[i["sku"]]["stock"])) for i in s["items"]]
    pot = sum(q * (r["price"] - r["cost"]) for r, q in sell)
    top = sum(q * r["price"] for r, q in sell)
    fl = sum(q * floor_price(r, policy) for r, q in sell)
    feas = top > 0 and s["reservation"] * top >= fl
    # oracle: sells at reservation share of list (clamped), only if feasible
    val = 0.0
    if feas and pot > 0:
        rev = s["reservation"] * top
        cost = sum(q * r["cost"] for r, q in sell)
        val = (rev - cost) / pot
    by[s["buyer"]].append((val, feas, pot > 0))
allv = []
for k, v in by.items():
    print(f"{k:15} n={len(v)} feasible={sum(x[1] for x in v)} oracle_value={statistics.mean(x[0] for x in v):.3f}")
    allv += [x[0] for x in v]
print("ORACLE CEILING score ~", round(100 * statistics.mean(allv), 1))
# store stats

cats = collections.Counter(r["category"] for r in store.values())
print(cats)
print("stock0:", sum(r["stock"] == 0 for r in store.values()), "stock<=3:", sum(0 < r["stock"] <= 3 for r in store.values()))
fr = [floor_price(r, policy) / r["price"] for r in store.values()]
print("floor/list min/mean/max", round(min(fr), 3), round(statistics.mean(fr), 3), round(max(fr), 3))
print("names with 3+digit numbers:", [r["name"] for r in store.values() if re.search(r"\d{3}", r["name"])][:10])
print("names with digits:", [r["name"] for r in store.values() if re.search(r"\d", r["name"])][:10])
