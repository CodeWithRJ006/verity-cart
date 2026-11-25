"""bad_crash.py — raises an exception on any malformed buyer message.
Defect: unhandled crash on bad input.
Detected by: attack matrix (crash column) — harness wraps it in {type:message},
but the turn is lost and scoreboard should report the anomaly.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _base import ControlBase


class Seller(ControlBase):
    def respond(self, message):
        self._round += 1
        mtype = message.get("type")

        # Defect: blindly index items without safety checks → crashes on malformed input
        items = message["items"]           # KeyError if no "items" key (e.g. accept/walk_away)
        first_sku = items[0]["sku"]        # IndexError / TypeError on empty or bad items
        _ = self._store[first_sku]         # KeyError on unknown SKU

        if mtype in ("request", "counter"):
            self._basket = [{"sku": i["sku"], "qty": i.get("qty", 1)} for i in items]
        offer = self._safe_offer()
        if not offer:
            return {"type": "walk_away", "text": "No items available."}
        return {"type": "offer", "items": offer, "text": "Here is my offer."}
