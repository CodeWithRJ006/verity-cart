# verity/state.py — TEMPORARY I0 placeholder. Replaced by Dev1 in S6.
from typing import Dict, List, Optional
from .contracts import Basket, View
from . import gate


class NegotiationState:
    def __init__(self, store, policy, env):
        self.store = store
        self.policy = policy
        self.env = env
        self.basket: Optional[Basket] = None
        self.dropped: List[str] = []
        self.bids: List[float] = []
        self.last_offer_ratio: Optional[float] = None
        self.turn = 0

    def begin(self, msg) -> None:
        self.turn = 1
        wanted: Dict[str, int] = {}
        items = msg.items if hasattr(msg, "items") else msg.get("items")
        for it in items or []:
            if isinstance(it, dict):
                sku = it.get("sku")
                qty = it.get("qty")
                if sku in self.store and isinstance(qty, int) and not isinstance(qty, bool) and qty > 0:
                    wanted[sku] = wanted.get(sku, 0) + qty
        self.basket = {
            s: min(q, self.env.stock(s))
            for s, q in wanted.items()
            if self.env.stock(s) > 0
        }
        self.dropped = [s for s, q in wanted.items() if self.env.stock(s) == 0]

    def view(self, parsed) -> View:
        self.turn = parsed.round if parsed.round is not None else self.turn + 1
        if self.basket is None:
            self.begin(parsed)
        L = sum(q * self.env.list_price(k) for k, q in self.basket.items()) if self.basket else 0
        F = sum(q * self.env.floor(k) for k, q in self.basket.items()) if self.basket else 0

        # Check buyer items
        items = parsed.items
        bid_complete = False
        bid_valid = False
        if isinstance(items, list) and self.basket:
            seen_skus = {}
            for it in items:
                if isinstance(it, dict):
                    s, q, pr = it.get("sku"), it.get("qty"), it.get("unit_price")
                    if s in self.basket and isinstance(q, int) and not isinstance(q, bool) and q == self.basket[s]:
                        if isinstance(pr, (int, float)) and not isinstance(pr, bool):
                            seen_skus[s] = (q, pr)
            if len(seen_skus) == len(self.basket) and len(items) == len(self.basket):
                bid_complete = True
                bid_total = sum(q * p for q, p in seen_skus.values())
                if L > 0:
                    ratio = bid_total / L
                    self.bids.append(ratio)
            bid_valid = gate.bid_valid_as_made(items, self.basket, self.env)

        return View(
            round=self.turn,
            msg_type=parsed.type,
            L=L,
            F=F,
            bids=list(self.bids),
            bid_complete=bid_complete,
            bid_valid_as_made=bid_valid,
            last_offer_ratio=self.last_offer_ratio,
        )

    def remember(self, offer: dict) -> None:
        items = offer.get("items")
        if isinstance(items, list) and self.basket:
            total = sum(i["qty"] * i["unit_price"] for i in items if isinstance(i, dict) and "qty" in i and "unit_price" in i)
            L = sum(q * self.env.list_price(k) for k, q in self.basket.items())
            if L > 0:
                self.last_offer_ratio = total / L
