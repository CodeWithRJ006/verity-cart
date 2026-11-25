"""Contract conformance suite for the repair implementations.

Parametrized over BOTH implementations that verity/registry.py can load
(verity/registry.py:6-12): ``verity.repair_stub`` (Dev1's double) and
``verity.repair`` (Dev2's real allocator).  Only invariants both must satisfy are
asserted here; nothing in this file may depend on which implementation ran.

Contract asserted (verity/contracts.py:7-27):
  * the call returns a RepairResult;
  * present prices are integers inside [floor, list] for every basket line;
  * EXACT => sum(q_i * p_i) == requested total (and total field agrees);
  * AT_MOST => sum(q_i * p_i) <= target, never above it;
  * AGGREGATE_INFEASIBLE / INTEGER_INFEASIBLE carry prices=None;
  * the same call twice returns equal results (deterministic).
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[2] / "kit"
if str(KIT) not in sys.path:
    sys.path.insert(0, str(KIT))

import harness  # noqa: E402
import pytest  # noqa: E402

from tests.strategy.env_double import EnvDouble  # noqa: E402
from verity import repair as real_repair  # noqa: E402
from verity import repair_stub as stub_repair  # noqa: E402
from verity.contracts import RepairResult, RepairStatus  # noqa: E402

STORE = harness.load_store()
POLICY = harness.load_policy()
ENV = EnvDouble(STORE, POLICY)
IN_STOCK = sorted(sku for sku, row in STORE.items() if row["stock"] > 0)

IMPLS = [
    pytest.param(stub_repair, id="repair_stub"),
    pytest.param(real_repair, id="repair"),
]


def _cases():
    """40 deterministic baskets of 1-4 in-stock SKUs, qty 1-4."""
    rng = random.Random(1234)
    baskets = []
    for _ in range(40):
        n = rng.randint(1, 4)
        skus = rng.sample(IN_STOCK, n)
        baskets.append({s: rng.randint(1, min(STORE[s]["stock"], 4)) for s in skus})
    return baskets


CASES = _cases()


def _totals(basket):
    F = sum(q * ENV.floor(sku) for sku, q in basket.items())
    L = sum(q * ENV.list_price(sku) for sku, q in basket.items())
    return F, L


def _targets(basket):
    F, L = _totals(basket)
    return [F - 1, F, (F + L) // 2, L, L + 1]


def _sum(basket, prices):
    return sum(q * prices[sku] for sku, q in basket.items())


@pytest.mark.parametrize("impl", IMPLS)
def test_at_most_returns_result_within_target(impl):
    for basket in CASES:
        for target in _targets(basket):
            result = impl.allocate_at_most(basket, ENV, target)
            assert isinstance(result, RepairResult), (basket, target, result)
            assert result.status in (
                RepairStatus.EXACT,
                RepairStatus.AT_MOST,
                RepairStatus.AGGREGATE_INFEASIBLE,
            ), (basket, target, result)

            if result.status == RepairStatus.AGGREGATE_INFEASIBLE:
                assert result.prices is None, (basket, target, result)
                continue

            assert result.prices is not None and result.total is not None
            assert set(result.prices) == set(basket)
            assert _sum(basket, result.prices) == result.total
            assert result.total <= target, (basket, target, result.total)
            for sku, price in result.prices.items():
                assert isinstance(price, int) and not isinstance(price, bool)
                assert ENV.floor(sku) <= price <= ENV.list_price(sku), (
                    f"{sku}: price={price} floor={ENV.floor(sku)} "
                    f"list={ENV.list_price(sku)}"
                )


@pytest.mark.parametrize("impl", IMPLS)
def test_exact_status_implies_exact_sum(impl):
    for basket in CASES:
        for target in _targets(basket):
            result = impl.allocate_exact(basket, ENV, target)
            assert isinstance(result, RepairResult), (basket, target, result)

            if result.status in (
                RepairStatus.AGGREGATE_INFEASIBLE,
                RepairStatus.INTEGER_INFEASIBLE,
                RepairStatus.INVALID_INPUT,
            ):
                assert result.prices is None, (basket, target, result)

            if result.prices is None:
                continue

            assert result.total is not None
            assert set(result.prices) == set(basket)
            assert _sum(basket, result.prices) == result.total
            for sku, price in result.prices.items():
                assert isinstance(price, int) and not isinstance(price, bool)
                assert ENV.floor(sku) <= price <= ENV.list_price(sku)

            if result.status == RepairStatus.EXACT:
                assert result.total == target, (basket, target, result)
                assert _sum(basket, result.prices) == target


@pytest.mark.parametrize("impl", IMPLS)
def test_both_entry_points_are_deterministic(impl):
    for basket in CASES:
        for target in _targets(basket):
            assert impl.allocate_at_most(basket, ENV, target) == impl.allocate_at_most(
                basket, ENV, target
            ), (basket, target)
            assert impl.allocate_exact(basket, ENV, target) == impl.allocate_exact(
                basket, ENV, target
            ), (basket, target)


@pytest.mark.parametrize("impl", IMPLS)
def test_inputs_are_not_mutated(impl):
    for basket in CASES:
        before = dict(basket)
        target = _totals(basket)[0]
        impl.allocate_at_most(basket, ENV, target)
        impl.allocate_exact(basket, ENV, target)
        assert basket == before, basket
