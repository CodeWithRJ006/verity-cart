"""bad_below_floor.py — offers exactly 1 rupee below floor on the first line.
Detected by: policy-violation check / scoreboard (policy > 0).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _base import ControlBase, floor_price


class Seller(ControlBase):
    def respond(self, message):
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

        # Defect: subtract 1 rupee below floor on the first line
        row = self._store[offer[0]["sku"]]
        fp = floor_price(row, self._policy)
        offer[0]["unit_price"] = fp - 1   # <- violates policy

        return {"type": "offer", "items": offer, "text": "Special price for you."}
