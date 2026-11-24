# verity/renderer.py — Fixed truthful templates for outgoing seller messages.
# Python 3.9 stdlib only.
from __future__ import annotations
from typing import Any, Dict, List, Optional


def render(
    kind: str,
    items: Optional[List[Dict[str, Any]]] = None,
    total: Optional[int] = None,
    dropped: Optional[List[str]] = None,
    store: Optional[Dict[str, Any]] = None,
) -> str:
    """Render seller messages using strict, truthful templates.

    Template set:
    - open: 'I can offer {names} for ₹{total:,}.'
    - counter: 'I can do {names} for ₹{total:,}.'
    - accept: 'Deal, thank you!'
    - walkaway_nostock: 'Sorry, those items are out of stock.'
    - walkaway_final: "Thanks for your time. We can't agree on price, so I will pass."
    - plain_fallback: 'I can offer this bundle for ₹{total:,}.'

    Invariants:
    - Never generates percentages, stock counts, scarcity/urgency words, fee words, or competitor names.
    - Numbers formatted strictly as integer rupees with thousands separators (₹{total:,}).
    - Returns plain strings with 0 truth violations.
    """
    if kind == "accept":
        return "Deal, thank you!"

    if kind == "walkaway_nostock":
        return "Sorry, those items are out of stock."

    if kind in ("walkaway", "walkaway_final"):
        return "Thanks for your time. We can't agree on price, so I will pass."

    # Format line names if items and store available
    names = ""
    if items and store:
        valid_segments = []
        for it in items:
            sku = it.get("sku")
            qty = it.get("qty", 1)
            if sku in store and "name" in store[sku]:
                valid_segments.append(f"{qty} x {store[sku]['name']}")
        if valid_segments:
            names = " and ".join(valid_segments)

    # Formatted total
    total_str = f"₹{total:,}" if total is not None else ""

    if kind == "open":
        if names and total_str:
            return f"I can offer {names} for {total_str}."
        if total_str:
            return f"I can offer this bundle for {total_str}."
        return "I can offer this bundle."

    if kind == "counter":
        if names and total_str:
            return f"I can do {names} for {total_str}."
        if total_str:
            return f"I can do this bundle for {total_str}."
        return "I can do this bundle."

    # kind == "plain_fallback" or fallback
    if total_str:
        return f"I can offer this bundle for {total_str}."
    return "I can offer this bundle."
