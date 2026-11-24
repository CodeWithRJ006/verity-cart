# verity/gate.py — Independent outgoing message verification gate (Dev1).
# Python 3.9 stdlib only. No imports from strategy, repair, or renderer.
from __future__ import annotations

import math
from typing import Any, Optional


def bid_valid_as_made(items: Any, basket: Optional[dict[str, int]], env: Any) -> bool:  # noqa: UP045
    """True iff every buyer line is valid AS MADE.

    Conditions:
    - items is a non-empty list of dicts.
    - basket is a non-empty dict.
    - Every line has a known SKU in basket.
    - No duplicate SKUs, and the SKU set equals the basket exactly.
    - Line qty is an int (not bool) equal to basket[sku] and <= current stock.
    - Line unit_price is an int or float (not bool, finite) with floor <= price <= list.
    - Never raises: any exception returns False.
    """
    try:
        if not isinstance(items, list) or not items:
            return False
        if not isinstance(basket, dict) or not basket:
            return False

        seen_skus = set()
        for it in items:
            if not isinstance(it, dict):
                return False
            sku = it.get("sku")
            qty = it.get("qty")
            price = it.get("unit_price")

            if not isinstance(sku, str) or sku not in basket or sku in seen_skus:
                return False
            seen_skus.add(sku)

            if type(qty) is not int or qty != basket[sku] or qty <= 0:
                return False

            if type(price) not in (int, float) or isinstance(price, bool) or not math.isfinite(price):
                return False

            try:
                floor = env.floor(sku)
                list_p = env.list_price(sku)
                if hasattr(env, "stock") and qty > env.stock(sku):
                    return False
            except Exception:  # noqa: BLE001
                return False

            if not (floor <= price <= list_p):
                return False

        return seen_skus == set(basket.keys())
    except Exception:  # noqa: BLE001
        return False


def check_outgoing(msg: Any, basket: Optional[dict[str, int]], env: Any) -> tuple[bool, list[str]]:  # noqa: UP045
    """Verifies that an outgoing seller message satisfies all policy, protocol, and inventory constraints.

    Allowed types per kit/harness.py:201: ("offer", "accept", "walk_away", "message").
    Never raises: any unhandled exception returns (False, ["gate_error"]).
    """
    try:
        if not isinstance(msg, dict):
            return False, ["bad_type"]

        reasons: list[str] = []

        # kit/harness.py:201 - seller's allowed type set: ("offer", "accept", "walk_away", "message")
        msg_type = msg.get("type")
        if msg_type not in ("offer", "accept", "walk_away", "message"):
            reasons.append("bad_type")

        # "text" must be a str
        text = msg.get("text")
        if not isinstance(text, str):
            reasons.append("bad_text")

        # If bad_type, abort further checks
        if "bad_type" in reasons:
            return False, reasons

        # "walk_away" and "message": no items required
        if msg_type in ("walk_away", "message"):
            return len(reasons) == 0, reasons

        # "accept": additionally the buyer's items must satisfy bid_valid_as_made
        if msg_type == "accept":
            items = msg.get("items") if "items" in msg else msg.get("buyer_items")
            if items is None or not bid_valid_as_made(items, basket, env):
                reasons.append("bad_items")
            return len(reasons) == 0, reasons

        # "offer": items must be a non-empty list of dicts
        items = msg.get("items")
        if not isinstance(items, list) or not items:
            reasons.append("bad_items")
            return False, reasons

        if any(not isinstance(it, dict) for it in items):
            reasons.append("bad_items")
            return False, reasons

        seen_skus = set()
        for it in items:
            sku = it.get("sku")
            qty = it.get("qty")
            price = it.get("unit_price")

            # Validate SKU format and existence in store via env
            if not isinstance(sku, str):
                reasons.append("unknown_sku")
                continue

            try:
                floor = env.floor(sku)
                list_p = env.list_price(sku)
                stock = env.stock(sku)
            except KeyError:
                reasons.append("unknown_sku")
                continue
            except Exception:  # noqa: BLE001
                reasons.append("unknown_sku")
                continue

            # Duplicate SKU check
            if sku in seen_skus:
                reasons.append("dup_sku")
            seen_skus.add(sku)

            # Extra SKU check (not in basket)
            if not isinstance(basket, dict) or sku not in basket:
                reasons.append("extra_sku")
                continue

            # Qty check
            expected_qty = basket[sku]
            if type(qty) is not int or qty != expected_qty or qty <= 0:
                reasons.append(f"qty_mismatch:{sku}")
            if type(qty) is int and qty > stock:
                reasons.append(f"over_stock:{sku}")

            # Price check (must be int, not bool, not float)
            if type(price) is not int or isinstance(price, bool):
                reasons.append(f"price_not_int:{sku}")
            else:
                if price < floor:
                    reasons.append(f"below_floor:{sku}")
                elif price > list_p:
                    reasons.append(f"above_list:{sku}")

        # Missing SKU check: all basket SKUs must be present in items
        if isinstance(basket, dict):
            missing = set(basket.keys()) - seen_skus
            if missing:
                reasons.append("missing_sku")

        return len(reasons) == 0, reasons
    except Exception:  # noqa: BLE001
        return False, ["gate_error"]
