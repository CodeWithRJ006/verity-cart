# experiments/mini_seller.py — owned by Dev2. Python 3.9, stdlib only.
"""MiniSeller: the feasibility spike rebuilt as ViewRef -> Strategy -> repair.

Independence contract: this module must NOT import verity.seller/state/parser/
envelope/gate/renderer/truth/registry or arena/.  It speaks plain dicts to the
buyer, exactly like verity/legacy_spike.py.

Per incoming message the pipeline is:

    ViewRef(store, policy, partial_bid_policy=cfg.partial_bid_policy,
            accept_semantics="spike").observe(msg)
        -> Strategy(cfg).decide(view)
        -> repair.allocate_at_most / allocate_exact(basket, EnvDouble, total)
        -> {"type": ..., "items": [{"sku", "qty", "unit_price"}, ...]}

All money is integer rupees.  No text is added to seller messages: no public
buyer reads the seller's "text" (kit/buyers.py:76-85 reads only "round",
"type" and "items"), and kit/harness.py:196-201 accepts a message without it.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from experiments.view_ref import ViewRef
from tests.strategy.env_double import EnvDouble
from verity import repair
from verity.config import Config
from verity.contracts import Action, Mode, RepairStatus, View
from verity.strategy import Strategy


class MiniSeller:
    """Spike-equivalent seller whose money decisions go through the contract View.

    store:  {sku: row from store.csv}
    policy: policy.json dict
    cfg:    verity.config.Config; defaults are the spike's constants
            (verity/legacy_spike.py:5 P, config.py:10-14), so a default MiniSeller
            must behave like legacy_spike.Seller.
    echo_alloc: "at_most" reproduces the spike, which echoes the buyer's total by
            calling reslice(int(b * L)) (verity/legacy_spike.py:198-201); "exact"
            uses repair.allocate_exact and falls back to allocate_at_most when the
            status is not EXACT.
    """

    def __init__(
        self,
        store: dict,
        policy: dict,
        cfg: Optional[Config] = None,
        echo_alloc: str = "at_most",
        accept_semantics: str = "spike",
    ) -> None:
        if echo_alloc not in ("at_most", "exact"):
            raise ValueError(
                f"echo_alloc must be 'at_most' or 'exact', got {echo_alloc!r}"
            )
        self.store = store
        self.policy = policy
        self.cfg = cfg if cfg is not None else Config()
        self.echo_alloc = echo_alloc
        self.accept_semantics = accept_semantics
        self._env = EnvDouble(store, policy)
        # Strategy raises NotImplementedError at construction for unsupported cfg.
        self._strategy = Strategy(self.cfg)
        self._view_ref: Optional[ViewRef] = None
        # Debug hook for tests: the View produced on the most recent respond().
        self.last_view: Optional[View] = None

    # ------------------------------------------------------------------
    # protocol
    # ------------------------------------------------------------------

    def start(self, negotiation_id: str) -> None:
        """Begin a negotiation: fresh per-negotiation ViewRef state.

        legacy_spike.Seller.start (verity/legacy_spike.py:19-23) resets basket,
        bids and last_o; ViewRef holds the same state and is recreated here.
        """
        self._view_ref = ViewRef(
            self.store,
            self.policy,
            partial_bid_policy=self.cfg.partial_bid_policy,
            accept_semantics=self.accept_semantics,
        )
        self.last_view = None

    def respond(self, message: dict) -> dict:
        """Never raise: any exception becomes a walk_away.

        Mirrors legacy_spike.Seller.respond (verity/legacy_spike.py:130-134) and
        kit/harness.py:237-240 still treats a crash as a lost turn if one escapes.
        """
        try:
            return self._respond(message)
        except Exception:
            return {"type": "walk_away"}

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _respond(self, msg: dict) -> dict:
        msg_type = msg.get("type")

        # legacy_spike.py:137-138 — greeting reply, before any basket formation.
        if msg_type in ("walk_away", "accept"):
            return {"type": "message", "text": "Thank you, goodbye."}

        assert self._view_ref is not None, "start() must be called before respond()"
        view = self._view_ref.observe(msg)
        self.last_view = view

        # legacy_spike.py:156-160 — empty basket after formation is a walk_away.
        # ViewRef.L is 0 exactly when _form_basket produced no sellable SKU
        # (view_ref.py:106-108), which is the spike's "if not self.basket" test.
        if view.L == 0:
            return {"type": "walk_away"}

        decision = self._strategy.decide(view)

        # legacy_spike.py:196-197 — accept the buyer's items exactly as made.
        if decision.action == Action.ACCEPT:
            return {"type": "accept"}
        # legacy_spike.py:185-189 — no close enough price left.
        if decision.action == Action.WALK_AWAY:
            return {"type": "walk_away"}

        # COUNTER: allocate per line inside [floor, list] with integer rupees.
        #
        # Basket source: ViewRef keeps the fixed basket private and exposes no
        # getter (view_ref.py:84 initialises it, view_ref.py:105-106 forms it once
        # on the first message).  repair.allocate_* needs that same Basket, so we
        # read the single source of truth instead of re-implementing basket
        # formation here — two implementations could silently drift apart.
        basket: Dict[str, int] = self._view_ref._basket  # type: ignore[assignment]

        if decision.mode == Mode.AT_MOST:
            result = repair.allocate_at_most(basket, self._env, decision.total)
        elif self.echo_alloc == "at_most":
            # Spike echo: reslice(int(b * L)) (legacy_spike.py:198-201).  Same
            # allocator as AT_MOST, applied to the buyer's total.
            result = repair.allocate_at_most(basket, self._env, decision.total)
        else:
            result = repair.allocate_exact(basket, self._env, decision.total)
            if result.status != RepairStatus.EXACT:
                result = repair.allocate_at_most(basket, self._env, decision.total)

        # Strategy clamps every COUNTER total to [F, L] (strategy.py:118-136,
        # 148-157), so this cannot fire; kept as a total safety net because
        # prices is None only for AGGREGATE_INFEASIBLE (repair.py:37-38).
        if result.prices is None:
            return {"type": "walk_away"}

        # legacy_spike.py:177, 199, 203 — last_o is the TARGET ratio of this offer,
        # never the repaired per-line ratio.  Ratio None (round-10 floor offer,
        # legacy_spike.py:182-186) leaves last_o untouched, like the spike.
        if decision.ratio is not None:
            self._view_ref.set_last_offer_ratio(decision.ratio)

        items: List[dict] = [
            {"sku": sku, "qty": qty, "unit_price": int(result.prices[sku])}
            for sku, qty in basket.items()
        ]
        return {"type": "offer", "items": items}
