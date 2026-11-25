"""bad_text_pressure.py — uses forbidden pressure tactics in outgoing text.
Defect: says "hurry, only 2 left, selling fast" regardless of real stock.
Detected by: text-flag scan / truth violations in scoreboard (truth > 0).
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

        # Defect: pressure + false scarcity claim in every outgoing text
        bad_text = (
            "Hurry! Only 2 left and selling fast — this offer expires today only. "
            "Someone else is looking at this right now. High demand item!"
        )
        return {"type": "offer", "items": offer, "text": bad_text}
