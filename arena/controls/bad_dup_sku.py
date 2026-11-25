"""bad_dup_sku.py — duplicates the first SKU line in every offer.
Defect: offer contains the same SKU twice.
Detected by: attack matrix (dup-SKU column) — gate / check_items flags malformed offer.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _base import ControlBase


class Seller(ControlBase):
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

        # Defect: append a duplicate of the first line
        dup = dict(offer[0])
        offer.append(dup)

        return {"type": "offer", "items": offer, "text": "Here is my offer."}
