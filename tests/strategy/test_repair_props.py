"""Property tests for verity/repair.py (Hypothesis belongs in tests only).

Coverage:
  1. both allocators always price inside [floor, list] for every line;
  2. allocate_exact is EXACT exactly when an independent brute force (plain
     Python sets, no bit shifts) finds an integer split, exhaustively over
     every total in [F, L] for small baskets; totals outside [F, L] are
     AGGREGATE_INFEASIBLE;
  3. allocate_at_most never exceeds its target, returns EXACT/AT_MOST inside
     [F, L], AGGREGATE below F, and list prices at/above L;
  4. determinism (same call twice -> equal RepairResult);
  5. inputs are never mutated;
  6. explicit INTEGER_INFEASIBLE cases (qty 3/4 with R not divisible by it, and
     a 2x4 line pair) with brute-force agreement.

Maximality of allocate_at_most (cannot add one unit of price to any line) is a
MEASUREMENT, not an assertion: the spike's leftover loop need not be maximal and
allocate_at_most may not change, so the count is printed instead.

Also prints the exact DP's timing over 1000 random baskets.
"""
from __future__ import annotations

import random
import sys
import time
from pathlib import Path

KIT = Path(__file__).resolve().parents[2] / "kit"
if str(KIT) not in sys.path:
    sys.path.insert(0, str(KIT))

import harness  # noqa: E402
from hypothesis import HealthCheck, given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from tests.strategy.env_double import EnvDouble  # noqa: E402
from verity.contracts import RepairResult, RepairStatus  # noqa: E402
from verity.repair import allocate_at_most, allocate_exact  # noqa: E402

STORE = harness.load_store()
POLICY = harness.load_policy()
ENV = EnvDouble(STORE, POLICY)

IN_STOCK = sorted(sku for sku, row in STORE.items() if row["stock"] > 0)
BY_WIDTH = sorted(IN_STOCK, key=lambda s: (ENV.list_price(s) - ENV.floor(s), s))
# Smallest price windows, used only where every total in [F, L] is enumerated.
SMALL_SKUS = BY_WIDTH[:5]

SETTINGS = settings(
    derandomize=True,
    deadline=None,
    max_examples=300,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


def _totals(basket, env=ENV):
    F = sum(q * env.floor(sku) for sku, q in basket.items())
    L = sum(q * env.list_price(sku) for sku, q in basket.items())
    return F, L


def _sum(basket, prices):
    return sum(q * prices[sku] for sku, q in basket.items())


def _brute_reachable(basket, env, cap):
    """Independent oracle: plain set of reachable sums of q_i * d_i, 0 <= d_i <= W_i.

    Deliberately NOT bitset/shift based, so it cannot share a bug with the DP.
    Only sums <= cap are kept.
    """
    reach = {0}
    for sku, qty in basket.items():
        width = env.list_price(sku) - env.floor(sku)
        nxt = set()
        for base in reach:
            for d in range(width + 1):
                total = base + qty * d
                if total > cap:
                    break  # d only grows, so every later multiple is larger
                nxt.add(total)
        reach = nxt
    return reach


@st.composite
def full_baskets(draw):
    """1-6 distinct in-stock SKUs, qty 1-5 (the shape MiniSeller can pass)."""
    n = draw(st.integers(min_value=1, max_value=6))
    skus = draw(st.lists(st.sampled_from(IN_STOCK), min_size=n, max_size=n, unique=True))
    return {sku: draw(st.integers(min_value=1, max_value=5)) for sku in skus}


@st.composite
def small_baskets(draw):
    """1-2 lines, qty 1, from the 5 narrowest price windows: [F, L] is enumerable."""
    n = draw(st.integers(min_value=1, max_value=2))
    skus = draw(st.lists(st.sampled_from(SMALL_SKUS), min_size=n, max_size=n, unique=True))
    return {sku: 1 for sku in skus}


# ---------------------------------------------------------------------------
# 1. bounds for both allocators
# ---------------------------------------------------------------------------

@SETTINGS
@given(full_baskets(), st.integers(min_value=-5000, max_value=300000))
def test_prices_always_within_floor_list(basket, target):
    for allocator in (allocate_at_most, allocate_exact):
        result = allocator(basket, ENV, target)
        assert isinstance(result, RepairResult)
        if result.prices is None:
            continue
        assert set(result.prices) == set(basket), (basket, result)
        for sku, price in result.prices.items():
            assert isinstance(price, int) and not isinstance(price, bool)
            assert ENV.floor(sku) <= price <= ENV.list_price(sku), (
                f"{sku}: price={price} floor={ENV.floor(sku)} list={ENV.list_price(sku)}"
            )
        assert result.total == _sum(basket, result.prices)


# ---------------------------------------------------------------------------
# 2. exactness vs the independent brute force, every total in [F, L]
# ---------------------------------------------------------------------------

@SETTINGS
@given(small_baskets())
def test_exact_matches_brute_force_for_every_total(basket):
    F, L = _totals(basket)
    reach = _brute_reachable(basket, ENV, L - F)

    for total in range(F, L + 1):
        result = allocate_exact(basket, ENV, total)
        r = total - F
        if r in reach:
            assert result.status == RepairStatus.EXACT, (basket, total, result)
            assert result.prices is not None and result.total == total
            assert _sum(basket, result.prices) == total, (basket, total, result.prices)
        else:
            assert result.status == RepairStatus.INTEGER_INFEASIBLE, (basket, total, result)
            assert result.prices is None and result.total is None


@SETTINGS
@given(full_baskets())
def test_exact_aggregate_outside_floor_and_list(basket):
    F, L = _totals(basket)
    for total in (F - 1, F - 500, L + 1, L + 5000):
        result = allocate_exact(basket, ENV, total)
        assert result.status == RepairStatus.AGGREGATE_INFEASIBLE, (basket, total, result)
        assert result.prices is None and result.total is None


# ---------------------------------------------------------------------------
# 3. at_most contract
# ---------------------------------------------------------------------------

@SETTINGS
@given(full_baskets(), st.integers(min_value=-5000, max_value=300000))
def test_at_most_contract(basket, target):
    F, L = _totals(basket)
    result = allocate_at_most(basket, ENV, target)

    if target < F:
        assert result.status == RepairStatus.AGGREGATE_INFEASIBLE
        assert result.prices is None and result.total is None
        return

    assert result.status in (RepairStatus.EXACT, RepairStatus.AT_MOST), result
    assert result.prices is not None and result.total is not None
    assert result.total == _sum(basket, result.prices)
    assert result.total <= target, (basket, target, result.total)
    assert result.status == (
        RepairStatus.EXACT if result.total == target else RepairStatus.AT_MOST
    )


@SETTINGS
@given(full_baskets())
def test_at_most_reaches_list_prices_at_or_above_L(basket):
    _, L = _totals(basket)
    for target in (L, L + 1, L + 10000):
        result = allocate_at_most(basket, ENV, target)
        assert result.prices == {sku: ENV.list_price(sku) for sku in basket}, (
            basket,
            target,
            result.prices,
        )
        assert result.total == L
        assert result.total <= target


# ---------------------------------------------------------------------------
# 4./5. determinism and no input mutation
# ---------------------------------------------------------------------------

@SETTINGS
@given(full_baskets(), st.integers(min_value=-100, max_value=300000))
def test_deterministic_and_inputs_unchanged(basket, target):
    basket_before = dict(basket)
    for allocator in (allocate_at_most, allocate_exact):
        first = allocator(basket, ENV, target)
        second = allocator(basket, ENV, target)
        assert first == second, (allocator.__name__, basket, target, first, second)
    assert basket == basket_before


# ---------------------------------------------------------------------------
# 6. explicit INTEGER_INFEASIBLE cases + brute-force agreement
# ---------------------------------------------------------------------------

class _FixedEnv:
    """Minimal env double with hand-picked floors/lists for explicit cases."""

    def __init__(self, floors, lists):
        self._floors = floors
        self._lists = lists

    def floor(self, sku):
        return self._floors[sku]

    def list_price(self, sku):
        return self._lists[sku]


EXPLICIT_ENV = _FixedEnv(
    {"A": 10, "B": 10, "C": 10},
    {"A": 20, "B": 20, "C": 40},
)


def test_explicit_integer_infeasible_cases():
    # (basket, total, expected_status): R = total - F.
    cases = [
        ({"A": 3}, 31, RepairStatus.INTEGER_INFEASIBLE),  # R=1, not a multiple of 3
        ({"A": 3}, 32, RepairStatus.INTEGER_INFEASIBLE),  # R=2
        ({"A": 3}, 30, RepairStatus.EXACT),               # R=0
        ({"A": 3}, 33, RepairStatus.EXACT),               # R=3
        ({"A": 4}, 42, RepairStatus.INTEGER_INFEASIBLE),  # R=2, not a multiple of 4
        ({"A": 4}, 46, RepairStatus.INTEGER_INFEASIBLE),  # R=6
        ({"A": 4}, 44, RepairStatus.EXACT),               # R=4
        ({"A": 2, "B": 4}, 61, RepairStatus.INTEGER_INFEASIBLE),  # R=1 (all sums even)
        ({"A": 2, "B": 4}, 63, RepairStatus.INTEGER_INFEASIBLE),  # R=3
        ({"A": 2, "B": 4}, 62, RepairStatus.EXACT),               # R=2 = 2*1
        ({"A": 2, "B": 4}, 66, RepairStatus.EXACT),               # R=6 = 2*3
        ({"A": 2, "B": 2}, 43, RepairStatus.INTEGER_INFEASIBLE),  # R=3 (all sums even)
        ({"A": 2, "B": 2}, 44, RepairStatus.EXACT),               # R=4 = 2*2
    ]
    for basket, total, expected in cases:
        F, L = _totals(basket, EXPLICIT_ENV)
        assert F <= total <= L, (basket, total, F, L)
        result = allocate_exact(basket, EXPLICIT_ENV, total)
        assert result.status == expected, (basket, total, result)

        # Independent oracle must agree that an integer split does/does not exist.
        exists = (total - F) in _brute_reachable(basket, EXPLICIT_ENV, L - F)
        assert exists == (expected == RepairStatus.EXACT)

        if expected == RepairStatus.EXACT:
            assert result.prices is not None
            assert _sum(basket, result.prices) == total
            for sku, price in result.prices.items():
                assert EXPLICIT_ENV.floor(sku) <= price <= EXPLICIT_ENV.list_price(sku)
        else:
            assert result.prices is None and result.total is None

    print(f"\nexplicit exact cases (incl. INTEGER_INFEASIBLE): {len(cases)} checked")


def test_invalid_input_statuses():
    bad_calls = [
        ([], 10),
        ({}, 10),
        ({"A": 0}, 10),
        ({"A": -1}, 10),
        ({"A": True}, 10),
        ({"A": "3"}, 10),
        ({"A": 1.0}, 10),
        ({"A": 1}, True),
        ({"A": 1}, 10.0),
        ({"A": 1}, "10"),
        ({"ZZ": 1}, 10),
    ]
    for basket, total in bad_calls:
        result = allocate_exact(basket, EXPLICIT_ENV, total)
        assert result.status == RepairStatus.INVALID_INPUT, (basket, total, result)
        assert result.prices is None and result.total is None
    print(f"invalid-input cases: {len(bad_calls)} checked")


# ---------------------------------------------------------------------------
# Maximality MEASUREMENT for allocate_at_most (printed, never asserted)
# ---------------------------------------------------------------------------

def test_at_most_maximality_measurement():
    """Count targets where no line can take one more unit of price.

    This is a measurement: the spike's leftover loop (legacy_spike.py:31-61) is
    copied verbatim and may stop below the true maximum, and we may not change it.
    """
    rng = random.Random(2024)
    checked = 0
    stubborn = 0
    counterexample = None
    for _ in range(400):
        n = rng.randint(1, 6)
        skus = rng.sample(IN_STOCK, n)
        basket = {s: rng.randint(1, min(STORE[s]["stock"], 5)) for s in skus}
        F, L = _totals(basket)
        target = rng.randint(F, L)
        result = allocate_at_most(basket, ENV, target)
        if result.prices is None or result.status == RepairStatus.AGGREGATE_INFEASIBLE:
            continue
        checked += 1
        prices = result.prices
        # Raising the unit price of a line by 1 raises the offer total by qty.
        maximal = all(
            prices[sku] >= ENV.list_price(sku) or result.total + qty > target
            for sku, qty in basket.items()
        )
        if not maximal:
            stubborn += 1
            if counterexample is None:
                counterexample = (basket, target, dict(prices), result.total)

    print(
        f"\nat_most maximality: {stubborn}/{checked} targets were NOT maximal "
        f"(no line could take +1 unit and stay <= target)"
    )
    if counterexample is not None:
        basket, target, prices, total = counterexample
        gaps = {
            sku: target - total
            for sku in basket
            if prices[sku] < ENV.list_price(sku)
        }
        print(
            f"  counterexample: basket={basket} target={target} prices={prices} "
            f"total={total} remaining_gap={gaps}"
        )
    assert checked > 0


# ---------------------------------------------------------------------------
# Timing of the exact DP over 1000 random baskets
# ---------------------------------------------------------------------------

def test_exact_dp_timing_over_1000_baskets():
    rng = random.Random(7)
    timings = []
    statuses = {}
    for _ in range(1000):
        n = rng.randint(1, 6)
        skus = rng.sample(IN_STOCK, n)
        basket = {s: rng.randint(1, min(STORE[s]["stock"], 5)) for s in skus}
        F, L = _totals(basket)
        total = rng.randint(F, L)
        start = time.perf_counter()
        result = allocate_exact(basket, ENV, total)
        timings.append((time.perf_counter() - start) * 1000.0)
        statuses[result.status.value] = statuses.get(result.status.value, 0) + 1

    worst = max(timings)
    mean = sum(timings) / len(timings)
    print(
        f"\nexact DP timing over {len(timings)} random baskets: "
        f"worst={worst:.3f} ms mean={mean:.3f} ms statuses={statuses}"
    )
    assert worst < 100.0, f"exact DP worst case {worst:.1f} ms is not milliseconds"
