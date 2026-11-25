"""bad_stateful.py - leaks the previous negotiation's basket into the next one.
Defect: class-level state survives start(); on a new request the previous lines are added to the offer.
Detected by: twin test and session-reuse test (fresh-process result differs)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _base import ControlBase  # noqa: E402


class Seller(ControlBase):
    _last = []          # defect: shared across negotiations and instances, never cleared in start()

    def start(self, negotiation_id):
        self._basket = []
        self._round = 0

    def respond(self, message):
        self._round += 1
        mtype = message.get("type")
        if mtype in ("request", "counter"):
            items = message.get("items") or []
            self._basket = [{"sku": i["sku"], "qty": i.get("qty", 1)}
                            for i in items if isinstance(i, dict) and "sku" in i]
            if self._round == 1:                       # leak previous negotiation's lines
                have = {i["sku"] for i in self._basket}
                self._basket += [dict(i) for i in Seller._last if i["sku"] not in have]
            Seller._last = [dict(i) for i in self._basket]
        if mtype == "walk_away":
            return {"type": "walk_away", "text": "Understood."}
        if mtype == "accept":
            return {"type": "accept", "text": "Agreed."}
        offer = self._safe_offer()
        if not offer:
            return {"type": "walk_away", "text": "No items available."}
        return {"type": "offer", "items": offer, "text": "Here is my offer."}
