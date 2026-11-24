# verity/gate.py — TEMPORARY I0 placeholder. Replaced by Dev1 in S5.
from typing import Dict, List, Tuple


def check_outgoing(msg: dict, basket: Dict[str, int], env) -> Tuple[bool, List[str]]:
    reasons = []
    if not isinstance(msg, dict):
        return False, ["not_a_dict"]
    t = msg.get("type")
    if t not in ("offer", "accept", "walk_away", "message"):
        return False, ["bad_type"]
    if t == "offer":
        items = msg.get("items")
        if not isinstance(items, list) or not items:
            return False, ["empty_items"]
        seen_skus = set()
        for it in items:
            if not isinstance(it, dict):
                return False, ["item_not_dict"]
            sku = it.get("sku")
            qty = it.get("qty")
            price = it.get("unit_price")
            if sku not in basket:
                reasons.append(f"extra_sku:{sku}")
                continue
            if sku in seen_skus:
                reasons.append(f"dup_sku:{sku}")
            seen_skus.add(sku)
            if not isinstance(qty, int) or isinstance(qty, bool) or qty != basket[sku]:
                reasons.append(f"bad_qty:{sku}")
            if not isinstance(price, int) or isinstance(price, bool):
                reasons.append(f"price_not_int:{sku}")
            elif not (env.floor(sku) <= price <= env.list_price(sku)):
                reasons.append(f"price_out_of_bounds:{sku}")
        if seen_skus != set(basket.keys()):
            reasons.append("sku_set_mismatch")
    return (len(reasons) == 0, reasons)


def bid_valid_as_made(items, basket: Dict[str, int], env) -> bool:
    if not isinstance(items, list) or not items:
        return False
    if not basket:
        return False
    seen = {}
    for it in items:
        if not isinstance(it, dict):
            return False
        sku = it.get("sku")
        qty = it.get("qty")
        price = it.get("unit_price")
        if sku not in basket or sku in seen:
            return False
        if not isinstance(qty, int) or isinstance(qty, bool) or qty != basket[sku]:
            return False
        if not isinstance(price, (int, float)) or isinstance(price, bool):
            return False
        if not (env.floor(sku) <= price <= env.list_price(sku)):
            return False
        seen[sku] = price
    return len(seen) == len(basket)
