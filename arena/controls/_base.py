"""Shared base for control sellers.  Python 3.9, stdlib only.
Each control subclasses ControlBase and overrides respond() to introduce exactly one defect.
Never import verity: sellers are black boxes in this lane.
"""
import csv
import math
import sys
from pathlib import Path

# resolve kit/ from any cwd
_KIT = Path(__file__).resolve().parent.parent.parent / "kit"
sys.path.insert(0, str(_KIT))


def _load_store():
    with open(_KIT / "store.csv", newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return {r["sku"]: dict(r, price=int(r["price"]), cost=int(r["cost"]), stock=int(r["stock"]))
            for r in rows}


def _load_policy():
    import json as _json
    with open(_KIT / "policy.json", encoding="utf-8") as fh:
        return _json.load(fh)


def floor_price(row, policy):
    margin_floor = row["cost"] / (1 - policy["min_margin"][row["category"]])
    discount_floor = row["price"] * (1 - policy["max_discount"])
    return math.ceil(max(margin_floor, discount_floor))


class ControlBase:
    """Minimal honest seller that controls can override."""

    def __init__(self, store, policy):
        self._store = store
        self._policy = policy
        self._basket = []          # list of {sku, qty} from buyer request
        self._round = 0

    def start(self, negotiation_id):
        self._basket = []
        self._round = 0

    def _safe_offer(self, ratio=0.90):
        """Return a legal offer at `ratio` of list price (clamped to floor)."""
        items = []
        for it in self._basket:
            row = self._store.get(it["sku"])
            if row is None or row["stock"] == 0:
                continue
            qty = min(it["qty"], row["stock"])
            fp = floor_price(row, self._policy)
            price = max(fp, int(row["price"] * ratio))
            items.append({"sku": it["sku"], "qty": qty, "unit_price": price})
        return items

    def respond(self, message):
        self._round += 1
        mtype = message.get("type")
        if mtype in ("request", "counter"):
            items = message.get("items") or []
            self._basket = [{"sku": i["sku"], "qty": i.get("qty", 1)}
                            for i in items if isinstance(i, dict) and "sku" in i]
        if mtype == "walk_away":
            return {"type": "walk_away", "text": "Understood."}
        if mtype == "accept":
            return {"type": "accept", "text": "Agreed."}
        offer = self._safe_offer()
        if not offer:
            return {"type": "walk_away", "text": "No items available."}
        return {"type": "offer", "items": offer, "text": "Here is my offer."}
