# verity/renderer.py — TEMPORARY I0 placeholder. Replaced by Dev1 in S4.
from typing import Dict, List


def render(kind: str, items: List[dict], total: int, dropped: List[str] = None, store: dict = None) -> str:
    if kind == "accept":
        return "Deal, thank you!"
    if kind == "walkaway_nostock":
        return "Sorry, those items are out of stock."
    if kind == "walkaway":
        return "Thanks for your time. We can't agree on price, so I will pass."
    # kind == "counter" / "offer"
    if items and store:
        names = " and ".join(f"{i['qty']} x {store[i['sku']]['name']}" for i in items if i.get("sku") in store)
        return f"I can do {names} for ₹{total:,}."
    return f"I can do this bundle for ₹{total:,}."
