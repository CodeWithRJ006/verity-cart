"""Tests for verity/repair.py.

Key requirement: allocate_at_most must produce IDENTICAL results to
legacy_spike.Seller.reslice for the same basket and target.

We build the legacy Seller (legacy_spike.py:8-9) with the real kit store and policy,
seed a random basket, then compare output prices dict exactly.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[2] / "kit"
if str(KIT) not in sys.path:
    sys.path.insert(0, str(KIT))

import harness  # noqa: E402

from tests.strategy.env_double import EnvDouble  # noqa: E402
from verity.contracts import RepairStatus  # noqa: E402
from verity.repair import allocate_at_most, allocate_exact  # noqa: E402

# We also import legacy_spike via the verity package path
VERITY = Path(__file__).resolve().parents[2] / "verity"
if str(VERITY.parent) not in sys.path:
    sys.path.insert(0, str(VERITY.parent))

import verity.legacy_spike as _spike  # noqa: E402


def _load():
    store = harness.load_store()
    policy = harness.load_policy()
    return store, policy


def _make_legacy_seller(store, policy):
    """Build legacy_spike.Seller (legacy_spike.py:8-11) with default params."""
    return _spike.Seller(store, policy)


def _random_basket(store, rng, min_skus=1, max_skus=4):
    """Pick 1-4 distinct in-stock SKUs with random qty in [1, min(stock, 5)]."""
    in_stock = [s for s, row in store.items() if row["stock"] > 0]
    n = rng.randint(min_skus, min(max_skus, len(in_stock)))
    skus = rng.sample(in_stock, n)
    return {s: rng.randint(1, min(store[s]["stock"], 5)) for s in skus}


def _spike_reslice(legacy_seller, basket, total):
    """Call legacy_spike.Seller.reslice (legacy_spike.py:31) after setting basket."""
    # start() initialises per-negotiation state (legacy_spike.py:19-23)
    legacy_seller.start("test")
    legacy_seller.basket = dict(basket)
    return legacy_seller.reslice(total)


def test_allocate_at_most_matches_spike():
    """allocate_at_most must produce prices identical to legacy_spike.reslice."""
    store, policy = _load()
    env = EnvDouble(store, policy)
    legacy = _make_legacy_seller(store, policy)
    rng = random.Random(42)

    n_cases = 0
    for _ in range(200):
        basket = _random_basket(store, rng)
        F = sum(q * env.floor(sku) for sku, q in basket.items())
        L = sum(q * env.list_price(sku) for sku, q in basket.items())
        if F > L:   # degenerate basket, skip
            continue

        # Test three target values: at F, midpoint, at L
        for target in [F, (F + L) // 2, L]:
            result = allocate_at_most(basket, env, target)
            spike_pr = _spike_reslice(legacy, basket, target)

            # Both must agree on every per-sku price
            assert result.prices == spike_pr, (
                f"basket={basket} target={target}\n"
                f"  repair: {result.prices}\n"
                f"  spike:  {spike_pr}"
            )
            n_cases += 1

    print(f"\nallocate_at_most matched legacy_spike in {n_cases} cases")


def test_prices_within_floor_list():
    """Every allocated price must satisfy floor <= price <= list."""
    store, policy = _load()
    env = EnvDouble(store, policy)
    rng = random.Random(99)

    for _ in range(100):
        basket = _random_basket(store, rng)
        F = sum(q * env.floor(sku) for sku, q in basket.items())
        L = sum(q * env.list_price(sku) for sku, q in basket.items())
        if F > L:
            continue
        target = rng.randint(F, L)
        result = allocate_at_most(basket, env, target)
        assert result.status in (RepairStatus.AT_MOST, RepairStatus.EXACT)
        assert result.prices is not None
        for sku, p in result.prices.items():
            assert env.floor(sku) <= p <= env.list_price(sku), (
                f"{sku}: price={p}, floor={env.floor(sku)}, list={env.list_price(sku)}"
            )


def test_sum_lte_target():
    """Allocated total must not exceed the requested target."""
    store, policy = _load()
    env = EnvDouble(store, policy)
    rng = random.Random(7)

    for _ in range(100):
        basket = _random_basket(store, rng)
        F = sum(q * env.floor(sku) for sku, q in basket.items())
        L = sum(q * env.list_price(sku) for sku, q in basket.items())
        if F > L:
            continue
        target = rng.randint(F, L)
        result = allocate_at_most(basket, env, target)
        assert result.total is not None
        assert result.total <= target, f"total {result.total} > target {target}"


def test_aggregate_infeasible_below_floor():
    """target < F => AGGREGATE_INFEASIBLE with prices=None."""
    store, policy = _load()
    env = EnvDouble(store, policy)
    # pick any single-sku basket
    sku = next(iter(store))
    basket = {sku: 1}
    F = env.floor(sku)
    if F > 0:
        result = allocate_at_most(basket, env, F - 1)
        assert result.status == RepairStatus.AGGREGATE_INFEASIBLE
        assert result.prices is None


def test_allocate_exact_returns_exact_or_infeasible():
    """allocate_exact either returns EXACT (sum==total) or INTEGER_INFEASIBLE."""
    store, policy = _load()
    env = EnvDouble(store, policy)
    rng = random.Random(13)

    for _ in range(100):
        basket = _random_basket(store, rng)
        F = sum(q * env.floor(sku) for sku, q in basket.items())
        L = sum(q * env.list_price(sku) for sku, q in basket.items())
        if F > L:
            continue
        total = rng.randint(F, L)
        result = allocate_exact(basket, env, total)
        assert result.status in (
            RepairStatus.EXACT,
            RepairStatus.INTEGER_INFEASIBLE,
            RepairStatus.AGGREGATE_INFEASIBLE,
        )
        if result.status == RepairStatus.EXACT:
            assert result.total == total
            assert result.prices is not None
