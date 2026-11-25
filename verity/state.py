# verity/state.py — State tracker and View builder (Dev1).
# Python 3.9 stdlib only. No imports from strategy, repair, or renderer.
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from . import gate
from .contracts import Basket, View
from .envelope import Envelope
from .parser import ParsedMsg, parse


class NegotiationState:
    """Tracks negotiation history and constructs View dataclasses for strategy.

    Invariants:
    - Independent state per negotiation; reset completely via start().
    - Basket fixed on first request from available stock; out-of-stock items recorded in dropped.
    - Bid history records ratios of complete bids only.
    - Free text is never parsed or propagated into View.
    """

    def __init__(
        self,
        store: Dict[str, Any],
        policy: Dict[str, Any],
        env: Any,
        gate_env: Optional[Any] = None,
        config: Optional[Any] = None,
    ) -> None:
        self.store = store
        self.policy = policy
        self.env = env
        self.gate_env = gate_env if gate_env is not None else Envelope(store, policy)
        self.config = config
        self.basket: Optional[Basket] = None
        self.dropped: List[str] = []
        self.bids: List[float] = []
        self.last_offer_ratio: Optional[float] = None
        self.turn: int = 0
        self.negotiation_id: Optional[str] = None

    def start(self, negotiation_id: Optional[str] = None) -> None:
        """Reset all state for a new negotiation session."""
        self.negotiation_id = negotiation_id
        self.basket = None
        self.dropped = []
        self.bids = []
        self.last_offer_ratio = None
        self.turn = 0

    def begin(self, msg: Any) -> None:
        """Fix basket and dropped items from first buyer message."""
        self.turn = 1
        wanted: Dict[str, int] = {}
        items = msg.items if hasattr(msg, "items") else (msg.get("items") if isinstance(msg, dict) else None)
        for it in items or []:
            if isinstance(it, dict):
                sku = it.get("sku")
                qty = it.get("qty")
                if (
                    isinstance(sku, str)
                    and sku in self.store
                    and type(qty) is int
                    and not isinstance(qty, bool)
                    and qty > 0
                ):
                    wanted[sku] = wanted.get(sku, 0) + qty

        self.basket = {}
        self.dropped = []
        for s, q in wanted.items():
            avail = self.env.stock(s, self.store) if hasattr(self.env, "stock") else self.store[s]["stock"]
            if avail > 0:
                self.basket[s] = min(q, avail)
            else:
                self.dropped.append(s)

    def view(self, parsed: Any) -> View:
        """Build View dataclass for the current turn."""
        if not isinstance(parsed, ParsedMsg):
            parsed = parse(parsed, self.store)

        # Round tracking: prefer valid msg round, else internal counter
        self.turn += 1
        has_valid_round = (
            type(parsed.round) is int
            and not isinstance(parsed.round, bool)
            and parsed.round >= 1
            and "missing_round" not in parsed.flags
            and "bad_round" not in parsed.flags
        )
        if has_valid_round:
            effective_round = parsed.round
            self.turn = parsed.round
        else:
            effective_round = self.turn

        if self.basket is None:
            self.begin(parsed)

        L = sum(q * self.env.list_price(k) for k, q in self.basket.items()) if self.basket else 0
        F = sum(q * self.env.floor(k) for k, q in self.basket.items()) if self.basket else 0

        # Check buyer items
        items = parsed.items
        bid_complete = False
        if isinstance(items, list) and self.basket:
            seen_skus: set[str] = set()
            valid_items = True
            total_bid = 0.0
            for it in items:
                if not isinstance(it, dict):
                    valid_items = False
                    break
                s = it.get("sku")
                q = it.get("qty")
                p = it.get("unit_price")
                if not isinstance(s, str) or s not in self.basket or s in seen_skus:
                    valid_items = False
                    break
                seen_skus.add(s)
                if type(q) is not int or q != self.basket[s]:
                    valid_items = False
                    break
                if type(p) not in (int, float) or isinstance(p, bool) or not math.isfinite(p):
                    valid_items = False
                    break
                total_bid += q * p

            if valid_items and seen_skus == set(self.basket.keys()):
                bid_complete = True
                if L > 0:
                    ratio = total_bid / L
                    self.bids.append(ratio)
            else:
                partial_policy = (
                    getattr(self.config, "partial_bid_policy", "ignore")
                    if self.config
                    else "ignore"
                )
                if partial_policy == "matched":
                    num = 0.0
                    den = 0.0
                    for it in items:
                        if not isinstance(it, dict):
                            continue
                        sku = it.get("sku")
                        if sku not in self.basket:
                            continue
                        q = it.get("qty")
                        pr = it.get("unit_price")
                        if (
                            not isinstance(q, int)
                            or isinstance(q, bool)
                            or q < 1
                            or not isinstance(pr, (int, float))
                            or isinstance(pr, bool)
                            or not math.isfinite(pr)
                        ):
                            continue
                        num += q * pr
                        den += q * self.env.list_price(sku)
                    if den > 0:
                        self.bids.append(num / den)

        accept_require_complete = (
            getattr(self.config, "accept_require_complete", True)
            if self.config
            else True
        )
        if accept_require_complete:
            bid_valid = gate.bid_valid_as_made(items, self.basket, self.gate_env)
        else:
            # Follow spike's directly_acceptable with gate checks:
            # (known SKU, int qty <= stock, price in [floor, list], no duplicates)
            bid_valid = False
            if isinstance(items, list) and items:
                seen_skus_acc = set()
                valid = True
                for it in items:
                    if not isinstance(it, dict):
                        valid = False
                        break
                    s = it.get("sku")
                    q = it.get("qty")
                    p = it.get("unit_price")
                    if not isinstance(s, str) or s in seen_skus_acc:
                        valid = False
                        break
                    seen_skus_acc.add(s)
                    try:
                        fl = self.gate_env.floor(s)
                        lp = self.gate_env.list_price(s)
                        st = self.gate_env.stock(s) if hasattr(self.gate_env, "stock") else self.store[s]["stock"]
                    except Exception:
                        valid = False
                        break
                    if type(q) is not int or isinstance(q, bool) or not (1 <= q <= st):
                        valid = False
                        break
                    if type(p) not in (int, float) or isinstance(p, bool) or not math.isfinite(p):
                        valid = False
                        break
                    if not (fl <= p <= lp):
                        valid = False
                        break
                bid_valid = valid

        return View(
            round=effective_round,
            msg_type=parsed.type,
            L=L,
            F=F,
            bids=list(self.bids),
            bid_complete=bid_complete,
            bid_valid_as_made=bid_valid,
            last_offer_ratio=self.last_offer_ratio,
        )

    def remember(self, offer: dict, decision: Optional[Any] = None) -> None:
        """Record seller's own outgoing offer ratio."""
        if not isinstance(offer, dict) or offer.get("type") != "offer":
            return
        if decision is not None and getattr(decision, "ratio", None) is not None:
            self.last_offer_ratio = decision.ratio
            return
        items = offer.get("items")
        if isinstance(items, list) and self.basket:
            total = sum(
                i["qty"] * i["unit_price"]
                for i in items
                if isinstance(i, dict)
                and type(i.get("qty")) is int
                and type(i.get("unit_price")) in (int, float)
                and not isinstance(i.get("unit_price"), bool)
            )
            L = sum(q * self.env.list_price(k) for k, q in self.basket.items())
            if L > 0:
                self.last_offer_ratio = total / L
