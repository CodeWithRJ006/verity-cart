# verity/strategy_baseline.py — owned by Dev2. Python 3.9, stdlib only.
"""B0 ablation: the kit example seller's acceptance rule behind the Strategy API.

Rule source: kit/example_seller.py:24-58.  The example never reads the buyer's
text (kit/example_seller.py:3-4) and never walks away once a basket is formed
except when nothing is in stock (kit/example_seller.py:33-34), which the
orchestrator handles before the strategy is called (verity/seller.py:107-118).
It is therefore expressible from View alone:

    accept      kit/example_seller.py:40-41, 47-58
                message is a request or counter, the bid is exactly our basket
                (View.bid_complete, verity/state.py:120-145) and the gate says
                the bid is valid as made (View.bid_valid_as_made, which carries
                floor <= price <= list, verity/state.py:147-189).
    open        kit/example_seller.py:35: prices start at list, so the first
                offer is the list total L.
    decay       kit/example_seller.py:36-38: on every *later* counter, move a
                quarter of the gap to the floor.  The example does it per line
                with ceil; View exposes only totals, so B0 does it on the
                aggregate total with the same integer arithmetic:
                    T = round(last_offer_ratio * L)
                    total = ceil((3 * T + F) / 4)
    repeat      kit/example_seller.py:36: a request after turn 1 does not move
                prices, so the previous offer is repeated.

The example has no target curve, no estimate, no echo/reslice and no round-10
rule; B0 uses none of them and ignores Config values entirely (it only stores
the Config so the registry can construct it, verity/seller.py:61).
"""
from __future__ import annotations

from typing import Optional

from verity.config import Config
from verity.contracts import Action, Decision, Mode, View

# kit/example_seller.py:40 — the example only accepts on these two types.
ACCEPT_TYPES = ("request", "counter")


class Strategy:
    """Decide like the kit example seller, from View fields only.

    Signature matches verity.strategy.Strategy: __init__(cfg) and
    decide(view) -> Decision (verity/registry.py:13-15, verity/seller.py:61,126).
    """

    def __init__(self, cfg: Optional[Config] = None) -> None:
        # Stored only so the registry's strategy_cls(cfg) call type-checks; B0
        # never reads a strategy parameter and never raises at construction.
        self._cfg = cfg

    def decide(self, view: View) -> Decision:
        L, F = view.L, view.F
        if L <= 0:
            # kit/example_seller.py:33-34 — nothing in stock to sell.
            return Decision(action=Action.WALK_AWAY, reason="baseline_empty")

        # Accept first: kit/example_seller.py:40-41 runs before the offer.
        if (
            view.msg_type in ACCEPT_TYPES
            and view.bid_complete
            and view.bid_valid_as_made
        ):
            return Decision(action=Action.ACCEPT, reason="baseline_accept")

        last_o = view.last_offer_ratio

        # kit/example_seller.py:29-38 — the decay is in the `elif`, so it is
        # skipped on the first message even when that message is a "counter".
        if last_o is None:
            total = L
            ratio = 1.0
            reason = "baseline_open"
        elif view.msg_type == "counter":
            prev = round(last_o * L)
            if prev < F:
                prev = F
            elif prev > L:
                prev = L
            # ceil((3 * prev + F) / 4) with integer arithmetic only.
            total = -(-(3 * prev + F) // 4)
            if total < F:
                total = F
            elif total > L:
                total = L
            ratio = total / L
            reason = "baseline_counter"
        else:
            # A later "request" does not move the example's prices: repeat.
            prev = round(last_o * L)
            total = max(F, min(L, prev))
            ratio = total / L
            reason = "baseline_repeat"

        return Decision(
            action=Action.COUNTER,
            total=total,
            mode=Mode.AT_MOST,
            reason=reason,
            ratio=ratio,
        )
