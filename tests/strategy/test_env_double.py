import copy
import math
import sys
from fractions import Fraction
from pathlib import Path

KIT = Path(__file__).resolve().parents[2] / "kit"
if str(KIT) not in sys.path:
    sys.path.insert(0, str(KIT))

import harness  # noqa: E402

from tests.strategy.env_double import EnvDouble  # noqa: E402


def _exact_floor(row, policy):
    m = Fraction(str(policy["min_margin"][row["category"]]))
    d = Fraction(str(policy["max_discount"]))
    margin_floor = Fraction(row["cost"]) / (1 - m)
    discount_floor = Fraction(row["price"]) * (1 - d)
    return math.ceil(max(margin_floor, discount_floor))


def test_floor_equals_harness():
    store, policy = harness.load_store(), harness.load_policy()
    env = EnvDouble(store, policy)
    for sku, row in store.items():
        assert env.floor(sku) == harness.floor_price(row, policy), sku
    print("checked: %d SKUs" % len(store))


def test_exact_crosscheck_reports_only():
    store, policy = harness.load_store(), harness.load_policy()
    env = EnvDouble(store, policy)
    diffs = []
    for sku, row in store.items():
        f, e = env.floor(sku), _exact_floor(row, policy)
        if f != e:
            diffs.append((sku, f, e, f - e))
    if diffs:
        print("sku | float floor | exact floor | diff")
        for d in diffs:
            print(" | ".join(str(x) for x in d))
    print("disagreements: %d of %d SKUs" % (len(diffs), len(store)))


def test_no_mutation():
    store, policy = harness.load_store(), harness.load_policy()
    before_s, before_p = copy.deepcopy(store), copy.deepcopy(policy)
    env = EnvDouble(store, policy)
    for sku in store:
        env.floor(sku)
        env.list_price(sku)
        env.stock(sku)
    assert store == before_s and policy == before_p
