"""Dev1 stand-in repair double. Invariant: prices in [floor, list]; sum <= target (at-most) or == total (exact)."""
from .contracts import Prices, RepairResult, RepairStatus


def allocate_at_most(basket, env, target: int) -> RepairResult:
    if not basket:
        return RepairResult(RepairStatus.INVALID_INPUT)
    F = sum(q * env.floor(k) for k, q in basket.items())
    L = sum(q * env.list_price(k) for k, q in basket.items())
    if target < F or target > L:
        return RepairResult(RepairStatus.AGGREGATE_INFEASIBLE)
    pr = {k: env.floor(k) for k in basket}
    H = L - F
    left = target - F
    if H > 0:
        for k in basket:
            add = min(env.list_price(k) - pr[k], int(left * (env.list_price(k) - env.floor(k)) / H))
            pr[k] += add
    rem = target - sum(q * pr[k] for k, q in basket.items())
    for k, q in sorted(basket.items(), key=lambda x: x[1]):
        step = min(rem // q, env.list_price(k) - pr[k])
        if step > 0:
            pr[k] += step
            rem -= step * q
    return RepairResult(RepairStatus.AT_MOST, pr, sum(q * pr[k] for k, q in basket.items()))


def allocate_exact(basket, env, total: int) -> RepairResult:
    res = allocate_at_most(basket, env, total)
    if res.status != RepairStatus.AT_MOST:
        return res
    if res.total == total:
        return RepairResult(RepairStatus.EXACT, res.prices, res.total)
    return RepairResult(RepairStatus.INTEGER_INFEASIBLE)
