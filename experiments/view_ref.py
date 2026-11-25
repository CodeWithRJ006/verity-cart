# experiments/view_ref.py — owned by Dev2.  Python 3.9, stdlib only.
# Independent second implementation of the View builder.
# DO NOT import Dev1 modules (parser, envelope, state, gate, renderer, truth,
# seller, registry) or anything under arena/; that defeats independence.
from __future__ import annotations

import math
from typing import Dict, List, Optional

from tests.strategy.env_double import EnvDouble
from verity.contracts import View


class ViewRef:
    """Stateful per-negotiation View builder.

    partial_bid_policy="matched":
        Literal port of legacy_spike read_bid (legacy_spike.py:74-93) + priced
        condition (legacy_spike.py:165-169).  A bid is appended to bids[] iff
        read_bid != None AND priced.  Denominator = sum(q_item * list_price) for
        matched lines only, NOT the basket total L.

    partial_bid_policy="ignore":
        Only *complete* bids enter bids[].  Complete means:
          - items is a list; every item is a dict
          - SKU set equals basket SKU set exactly (no extras, no missing, no dups)
          - each item qty equals basket[sku] (basket already capped at stock)
          - each unit_price is a real, finite, non-negative, non-bool int or float
            (Handbook Amendment A: excludes bool, str, None, NaN, Inf, negative)
        The 26 contract fixture cases encode this policy.

    accept_semantics="gate" (default):
        bid_valid_as_made = bid_complete AND every price in [floor_i, list_i].
        Only computed when bid_complete is True; unchanged from previous behaviour.

    accept_semantics="spike":
        bid_valid_as_made = priced AND directly_acceptable(items) — a literal port
        of the spike's acceptance test (legacy_spike.py:165-169 + 95-116).
        Computed for EVERY request/counter with a non-empty basket, independent of
        bid_complete (the spike's _respond does not gate on completeness).
        bid_complete retains its Amendment A meaning in both modes.

        Relationship to spike's directly_acceptable (legacy_spike.py:95-116):
        directly_acceptable checks per-item (1 <= q <= stock, floor <= p <= list)
        WITHOUT verifying that the item SKU set equals the basket.  Therefore:

          case_09 (extra SKU S002 in bid, basket={S001:1}):
            directly_acceptable -> True  (S001 valid, S002 also passes per-item checks)
            ViewRef gate -> bid_complete=False (S002 not in basket) -> bid_valid_as_made=False
            ViewRef spike -> bid_valid_as_made=True (priced AND DA, independent of bid_complete)
            Quoted: legacy_spike.py:95-116 — no basket-set check present.

          case_10 (wrong qty=1, basket={S001:2}):
            directly_acceptable -> True  (1 <= 1 <= stock=10, price in range)
            ViewRef gate -> bid_complete=False (qty 1 != basket["S001"]=2) -> False
            ViewRef spike -> bid_valid_as_made=True if price in range, independent of bid_complete
            Quoted: legacy_spike.py:107 checks 1 <= q <= stock, not q == basket[sku].
    """

    def __init__(
        self,
        store: dict,
        policy: dict,
        partial_bid_policy: str = "matched",
        accept_semantics: str = "gate",
    ) -> None:
        if partial_bid_policy not in {"matched", "ignore"}:
            raise ValueError(
                f"partial_bid_policy must be 'matched' or 'ignore',"
                f" got {partial_bid_policy!r}"
            )
        if accept_semantics not in {"gate", "spike"}:
            raise ValueError(
                f"accept_semantics must be 'gate' or 'spike',"
                f" got {accept_semantics!r}"
            )
        self._store = store
        self._policy = policy
        self._partial_bid_policy = partial_bid_policy
        self._accept_semantics = accept_semantics
        self._env = EnvDouble(store, policy)

        # Per-negotiation mutable state
        self._basket: Optional[Dict[str, int]] = None
        self._L: int = 0
        self._F: int = 0
        self._bids: List[float] = []
        self._last_offer_ratio: Optional[float] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def observe(self, msg: dict) -> View:
        """Process one incoming buyer message; return the current View.

        Basket is fixed on the very first call regardless of message type,
        mirroring legacy_spike.py:140 where basket is set when self.basket is None.
        """
        msg_type: str = msg.get("type", "")
        round_num: int = msg.get("round", 1)
        items = msg.get("items")

        # Basket formation: fixed on the first call (legacy_spike.py:140-155)
        if self._basket is None:
            self._basket = self._form_basket(items)
            self._L = sum(q * self._env.list_price(s) for s, q in self._basket.items())
            self._F = sum(q * self._env.floor(s) for s, q in self._basket.items())

        bid_complete = False
        bid_valid_as_made = False

        # Bid analysis only on request / counter messages (legacy_spike.py:163)
        if self._basket and msg_type in ("request", "counter"):
            bid_complete = self._is_complete(items)

            if self._accept_semantics == "gate":
                # gate: bid_valid_as_made only when structurally complete (Amendment A)
                if bid_complete:
                    bid_valid_as_made = self._is_valid_as_made_gate(items)
            else:
                # spike: bid_valid_as_made = priced AND directly_acceptable,
                # computed for EVERY request/counter with a non-empty basket,
                # regardless of bid_complete (legacy_spike.py:165-169, 95-116).
                bid_valid_as_made = self._is_valid_as_made_spike(items)

            self._update_bids(items, bid_complete)

        return View(
            round=round_num,
            msg_type=msg_type,
            L=self._L,
            F=self._F,
            bids=list(self._bids),
            bid_complete=bid_complete,
            bid_valid_as_made=bid_valid_as_made,
            last_offer_ratio=self._last_offer_ratio,
        )

    def remember(self, offer_msg: dict) -> None:
        """Record our outgoing offer; sets last_offer_ratio = sum(q*price) / L.

        Matches the format of case_26's 'remember' field (view_cases.json:1431-1441):
        {"type": "offer", "items": [{"sku":..., "qty":..., "unit_price":...}], ...}
        """
        if not self._L:
            self._last_offer_ratio = None
            return
        items = offer_msg.get("items") or []
        total: float = 0.0
        for it in items:
            if not isinstance(it, dict):
                continue
            q = it.get("qty")
            p = it.get("unit_price")
            if (
                isinstance(q, int)
                and not isinstance(q, bool)
                and isinstance(p, (int, float))
                and not isinstance(p, bool)
            ):
                total += q * p
        self._last_offer_ratio = total / self._L

    def set_last_offer_ratio(self, x: Optional[float]) -> None:
        """Let a MiniSeller store strategy's TARGET ratio instead of the offer ratio."""
        self._last_offer_ratio = x

    # ------------------------------------------------------------------
    # Private: basket formation
    # ------------------------------------------------------------------

    def _form_basket(self, items) -> Dict[str, int]:
        """Form basket from first-request items (legacy_spike.py:140-155).

        Aggregates duplicate SKUs, caps qty at stock, drops OOS SKUs.
        Note: spike basket formation does not exclude bool-typed qty (no isinstance(qty, bool)
        check at lines 143-149); only read_bid has that guard.  We mirror spike exactly here.
        """
        wanted: Dict[str, int] = {}
        if isinstance(items, list):
            for it in items:
                sku = it.get("sku") if isinstance(it, dict) else None
                qty = it.get("qty") if isinstance(it, dict) else None
                if (
                    sku in self._store
                    and isinstance(qty, int)
                    and qty > 0
                ):
                    wanted[sku] = wanted.get(sku, 0) + qty
        return {
            s: min(q, self._store[s]["stock"])
            for s, q in wanted.items()
            if self._store[s]["stock"] > 0
        }

    # ------------------------------------------------------------------
    # Private: completeness and validity checks
    # ------------------------------------------------------------------

    @staticmethod
    def _price_ok_for_complete(pr) -> bool:
        """Price acceptable for bid_complete: int/float, not bool, finite, >= 0.

        Handbook Amendment A exclusions: bool, NaN, Inf, str, None, negative.
        """
        if isinstance(pr, bool) or not isinstance(pr, (int, float)):
            return False
        return math.isfinite(pr) and pr >= 0

    def _is_complete(self, items) -> bool:
        """Bid is structurally complete (Handbook Amendment A).

        Checks:
          1. items is a list; every element is a dict
          2. SKU set equals basket SKU set exactly — no extras, no missing, no dups
          3. Each item qty == basket[sku]
          4. Each unit_price is a real, finite, non-negative, non-bool int/float
        """
        if not isinstance(items, list) or self._basket is None:
            return False
        seen: Dict[str, int] = {}
        for it in items:
            if not isinstance(it, dict):
                return False
            sku = it.get("sku")
            if sku not in self._basket:
                return False          # extra or unknown SKU
            if sku in seen:
                return False          # duplicate SKU
            seen[sku] = 1
            q = it.get("qty")
            pr = it.get("unit_price")
            if (
                not isinstance(q, int)
                or isinstance(q, bool)
                or q != self._basket[sku]
            ):
                return False
            if not self._price_ok_for_complete(pr):
                return False
        return set(seen.keys()) == set(self._basket.keys())

    def _is_valid_as_made_gate(self, items) -> bool:
        """gate mode: all prices in [floor_i, list_i].  Called only when bid_complete=True."""
        for it in items:
            sku = it.get("sku") if isinstance(it, dict) else None
            pr = it.get("unit_price") if isinstance(it, dict) else None
            if sku not in self._basket:
                return False
            if pr is None or isinstance(pr, bool) or not isinstance(pr, (int, float)):
                return False
            if pr < self._env.floor(sku) or pr > self._env.list_price(sku):
                return False
        return True

    # ------------------------------------------------------------------
    # Private: spike-mode validity — literal ports of legacy_spike logic
    # ------------------------------------------------------------------

    def _directly_acceptable_spike(self, items) -> bool:
        """Verbatim port of legacy_spike.Seller.directly_acceptable (legacy_spike.py:95-116).

        Checks every item individually: sku in store, 1 <= qty <= stock,
        floor(sku) <= price <= list_price.  Does NOT check basket SKU-set match
        or qty == basket[sku].

        EXCEPTION POLICY: exceptions are NOT caught here.
        The spike's respond() wraps _respond in a try/except at legacy_spike.py:130-134
        and returns walk_away on any exception.  MiniSeller will replicate that wrapper.
        In practice, for the fixture store/policy, this method never raises:
          - row=None guard at legacy_spike.py:104 fires before self.floor() at line 113.
          - NaN/Inf comparisons return False, not raise.
        """
        if not isinstance(items, list) or not items:        # legacy_spike.py:96
            return False
        for it in items:
            if not isinstance(it, dict):                    # legacy_spike.py:99
                return False
            row = self._store.get(it.get("sku"))            # legacy_spike.py:101
            q, pr = it.get("qty"), it.get("unit_price")    # legacy_spike.py:102
            if (                                            # legacy_spike.py:103-109
                row is None
                or not isinstance(q, int)
                or isinstance(q, bool)
                or not 1 <= q <= row["stock"]
            ):
                return False
            if (                                            # legacy_spike.py:110-115
                not isinstance(pr, (int, float))
                or isinstance(pr, bool)
                or not self._env.floor(it["sku"]) <= pr <= row["price"]
            ):
                return False
        return True                                         # legacy_spike.py:116

    def _is_valid_as_made_spike(self, items) -> bool:
        """spike mode: priced AND directly_acceptable(items).

        Mirrors the combined expression from legacy_spike.py:_respond:
          priced (lines 165-169) evaluated first (short-circuits);
          directly_acceptable (lines 95-116) evaluated only if priced.

        Called for EVERY request/counter with a non-empty basket, NOT gated on
        bid_complete.  bid_complete retains its Amendment A meaning independently.

        Exceptions from _directly_acceptable_spike propagate uncaught — see that
        method's docstring for the exception policy.
        """
        # priced condition (legacy_spike.py:165-169) — short-circuits
        priced = (
            isinstance(items, list)
            and bool(items)
            and all(isinstance(i, dict) and "unit_price" in i for i in items)
        )
        if not priced:
            return False
        return self._directly_acceptable_spike(items)

    # ------------------------------------------------------------------
    # Private: matched-mode helpers — literal spike ports
    # ------------------------------------------------------------------

    def _read_bid_matched(self, items) -> Optional[float]:
        """Verbatim port of legacy_spike.Seller.read_bid (legacy_spike.py:74-93).

        Ratio of price to list over the buyer's priced lines on basket SKUs.
        Denominator uses item qty * store list_price (NOT basket total L).
        Returns None if unusable: not a list, or no valid matched lines (den == 0).
        Note: does NOT filter negative prices — only excludes bool and non-numeric.
        """
        if not isinstance(items, list):
            return None
        num: float = 0
        den: float = 0
        for it in items:
            if not isinstance(it, dict) or it.get("sku") not in self._basket:
                continue
            q, pr = it.get("qty"), it.get("unit_price")
            if (                                      # legacy_spike.py:83-90
                not isinstance(q, int)
                or isinstance(q, bool)
                or q < 1
                or not isinstance(pr, (int, float))
                or isinstance(pr, bool)
            ):
                continue
            num += q * pr
            den += q * self._store[it["sku"]]["price"]
        return num / den if den else None

    @staticmethod
    def _is_priced(items) -> bool:
        """Verbatim port of spike's `priced` condition (legacy_spike.py:165-169).

        True iff items is a non-empty list of dicts all containing the key "unit_price".
        """
        return (
            isinstance(items, list)
            and bool(items)
            and all(isinstance(i, dict) and "unit_price" in i for i in items)
        )

    # ------------------------------------------------------------------
    # Private: bids list update
    # ------------------------------------------------------------------

    def _update_bids(self, items, bid_complete: bool) -> None:
        """Append a bid ratio to bids[] according to the configured policy."""
        if self._partial_bid_policy == "ignore":
            # Only complete bids: ratio = sum(q*p) / L over ALL basket lines
            if bid_complete and self._L > 0:
                total: float = sum(
                    it["qty"] * it["unit_price"]
                    for it in items
                )
                self._bids.append(total / self._L)
        else:
            # "matched": literal spike bid-append (legacy_spike.py:170-171)
            ratio = self._read_bid_matched(items)
            if ratio is not None and self._is_priced(items):
                self._bids.append(ratio)
