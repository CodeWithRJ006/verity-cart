"""bad_walks_early.py — walks away unconditionally at round 3.
Defect: premature walk_away collapses score (many deals possible but never closed).
Detected by: scoreboard (score collapse, very low deal rate).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _base import ControlBase

_WALK_ROUND = 3


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

        # Defect: walk away at or after round 3, closing almost nothing
        if self._round >= _WALK_ROUND:
            return {"type": "walk_away", "text": "Sorry, cannot proceed further."}

        offer = self._safe_offer()
        if not offer:
            return {"type": "walk_away", "text": "No items available."}
        return {"type": "offer", "items": offer, "text": "Here is my offer."}
