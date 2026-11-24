# verity/repair.py — owned by Dev2. Python 3.9, stdlib only.
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Dict

from verity.contracts import Basket, RepairResult, RepairStatus

if TYPE_CHECKING:
    pass


def allocate_at_most(basket: Basket, env: object, target: int) -> RepairResult:
    """Prices per line, each within [floor, list], summing to <= target (as close as possible).

    Verbatim port of legacy_spike.Seller.reslice (legacy_spike.py:31-61).
    Same bisection (40 iterations), same leftover loop and sort order.

    Status rules:
      target < F  -> AGGREGATE_INFEASIBLE, prices=None
      target >= L -> list prices, status=AT_MOST (or EXACT if sum == target)
      otherwise   -> AT_MOST (or EXACT if sum == target)
    """
    lines = list(basket.items())  # [(sku, qty), ...]

    # Aggregate floor total; list total is implicit via env.list_price in at()/tot()
    F = sum(q * env.floor(sku) for sku, q in lines)

    if target < F:
        return RepairResult(status=RepairStatus.AGGREGATE_INFEASIBLE)

    # --- verbatim bisection from legacy_spike.py:35-60 ---
    def at(s: float) -> Dict[str, int]:
        return {
            k: min(
                env.list_price(k),
                max(env.floor(k), math.ceil(env.list_price(k) * s)),
            )
            for k, _ in lines
        }

    def tot(pr: Dict[str, int]) -> int:
        return sum(q * pr[k] for k, q in lines)

    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if tot(at(mid)) <= target:
            lo = mid
        else:
            hi = mid
    pr = at(lo)
    left = target - tot(pr)
    for k, q in sorted(lines, key=lambda x: x[1]):
        if pr[k] < env.list_price(k) and q <= left:
            step = min(left // q, env.list_price(k) - pr[k])
            pr[k] += step
            left -= step * q
    # --- end verbatim port ---

    actual_total = tot(pr)
    # Clamp prices dict values to int (they should already be from math.ceil + int ops)
    prices: Dict[str, int] = {k: int(v) for k, v in pr.items()}
    status = RepairStatus.EXACT if actual_total == target else RepairStatus.AT_MOST
    return RepairResult(status=status, prices=prices, total=int(actual_total))


def allocate_exact(basket: Basket, env: object, total: int) -> RepairResult:
    """Allocate line prices summing exactly to total.

    For now delegates to allocate_at_most and returns EXACT only if the sum matches.
    If the sum does not match, returns INTEGER_INFEASIBLE.

    TODO: implement exact DP for guaranteed integer splits.
    """
    result = allocate_at_most(basket, env, total)
    if result.status == RepairStatus.AGGREGATE_INFEASIBLE:
        return result
    if result.total == total:
        return RepairResult(
            status=RepairStatus.EXACT,
            prices=result.prices,
            total=result.total,
        )
    return RepairResult(status=RepairStatus.INTEGER_INFEASIBLE)


def _check_allocator(allocator: str) -> None:
    """Raise NotImplementedError for unsupported allocators."""
    if allocator == "greedy":
        raise NotImplementedError("allocator='greedy' is not yet implemented")
