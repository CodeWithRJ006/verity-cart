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
    """Allocate integer per-line prices summing to exactly ``total``.

    Spec 02_DEV2 section 3.2.  With d_i = p_i - floor_i in [0, W_i],
    W_i = list_i - floor_i, and R = total - F, the question is whether some
    integer d_i satisfies sum(q_i * d_i) == R.  Feasibility is a bitset DP over
    Python big-int shifts (bit s of the prefix set means a prefix can reach s);
    reconstruction walks the stored prefix sets, last line to first, choosing on
    each line the admissible d closest to the proportional share
    R * W_i / sum(q_j * W_j), ties to the smaller d.

    Status rules:
      bad basket / total  -> INVALID_INPUT, prices=None
      total < F or > L    -> AGGREGATE_INFEASIBLE, prices=None
      no integer split    -> INTEGER_INFEASIBLE, prices=None
      otherwise           -> EXACT with sum(q_i * p_i) == total

    Integer arithmetic only (no float anywhere in feasibility or reconstruction);
    the basket and env are never mutated.
    """
    # --- input validation -------------------------------------------------
    if not isinstance(basket, dict) or not basket:
        return RepairResult(status=RepairStatus.INVALID_INPUT)
    if not isinstance(total, int) or isinstance(total, bool):
        return RepairResult(status=RepairStatus.INVALID_INPUT)
    lines = []
    for sku, qty in basket.items():
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
            return RepairResult(status=RepairStatus.INVALID_INPUT)
        lines.append((sku, qty))

    # Env lookups come last so an unknown SKU (KeyError from EnvDouble, or any
    # error from Dev1's Envelope) is reported as bad input rather than raised.
    try:
        floors = {sku: int(env.floor(sku)) for sku, _ in lines}
        lists = {sku: int(env.list_price(sku)) for sku, _ in lines}
    except Exception:
        return RepairResult(status=RepairStatus.INVALID_INPUT)

    F = sum(qty * floors[sku] for sku, qty in lines)
    L = sum(qty * lists[sku] for sku, qty in lines)
    if total < F or total > L:
        return RepairResult(status=RepairStatus.AGGREGATE_INFEASIBLE)

    R = total - F
    widths = [lists[sku] - floors[sku] for sku, _ in lines]
    if R == 0:
        return RepairResult(
            status=RepairStatus.EXACT,
            prices={sku: floors[sku] for sku, _ in lines},
            total=total,
        )

    n = len(lines)
    mask = (1 << (R + 1)) - 1  # keep only sums 0..R reachable

    # prefixes[i] = bitset of sums reachable with the first i lines.
    prefixes = [1]
    for i in range(n):
        prev = prefixes[-1]
        if prev == 0:
            prefixes.append(0)
            continue
        qty = lines[i][1]
        reach = 0
        v = prev
        for _ in range(widths[i] + 1):
            reach |= v
            v <<= qty
            if v & mask == 0:  # every later multiple is above R too
                break
        prefixes.append(reach & mask)

    if not (prefixes[n] >> R) & 1:
        return RepairResult(status=RepairStatus.INTEGER_INFEASIBLE)

    # --- deterministic reconstruction, last line back to first -------------
    span = sum(qty * w for (_, qty), w in zip(lines, widths))
    ds = [0] * n
    residual = R
    for i in range(n - 1, -1, -1):
        qty = lines[i][1]
        chosen = -1
        best_key = None
        for cand in range(widths[i] + 1):
            rem = residual - qty * cand
            if rem < 0:
                break  # cand only grows from here
            if not (prefixes[i] >> rem) & 1:
                continue
            key = abs(cand * span - R * widths[i])
            if best_key is None or key < best_key:  # ties keep the smaller d
                chosen, best_key = cand, key
        if chosen < 0:  # unreachable when prefixes[n] has bit R set
            return RepairResult(status=RepairStatus.INTEGER_INFEASIBLE)
        ds[i] = chosen
        residual -= qty * chosen
    if residual != 0:  # defensive; unreachable for the same reason
        return RepairResult(status=RepairStatus.INTEGER_INFEASIBLE)

    prices = {sku: floors[sku] + ds[i] for i, (sku, _) in enumerate(lines)}
    return RepairResult(status=RepairStatus.EXACT, prices=prices, total=total)


def _check_allocator(allocator: str) -> None:
    """Raise NotImplementedError for unsupported allocators."""
    if allocator == "greedy":
        raise NotImplementedError("allocator='greedy' is not yet implemented")
