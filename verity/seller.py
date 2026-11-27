# verity/seller.py — Orchestrator (Dev1). Stdlib-only Python 3.9.
from __future__ import annotations

import json
import math
import os
from typing import Optional

from . import gate, parser, renderer, truth
from .config import Config
from .contracts import Action, Decision, Mode, RepairStatus
from .envelope import Envelope
from .registry import load_impl
from .state import NegotiationState


class Seller:
    def __init__(self, store: dict, policy: dict, params: Optional[dict] = None):
        self.store = store
        self.policy = policy
        self.env = Envelope(store, policy)
        self.gate_env = Envelope(store, policy)

        # VERITY_SWITCHES: unknown key raises at construction
        switches_str = os.environ.get("VERITY_SWITCHES", "")
        self.cfg = Config.from_switches(switches_str)
        if params:
            for k, v in params.items():
                if not hasattr(self.cfg, k):
                    raise ValueError(f"Unknown config param: {k!r}")
                setattr(self.cfg, k, v)

        # VERITY_IMPL: default "real"
        self.impl_name = os.environ.get("VERITY_IMPL", "real")
        self.strategy_cls, self.repair = load_impl(self.impl_name)
        self.strategy = self.strategy_cls(self.cfg)

        # VERITY_LOG
        self.log_path = os.environ.get("VERITY_LOG")

        self.state: Optional[NegotiationState] = None
        self.last_offer: Optional[dict] = None
        self.negotiation_id: Optional[str] = None

    def start(self, negotiation_id: str) -> None:
        self.negotiation_id = negotiation_id
        if self.state is None:
            self.state = NegotiationState(self.store, self.policy, self.env, self.gate_env, config=self.cfg)
        else:
            self.state.start(negotiation_id)
        self.last_offer = None

    def respond(self, message: dict) -> dict:
        try:
            return self._respond(message)
        except Exception:
            return self._fallback()

    def _fallback(self) -> dict:
        # Fallback ladder:
        # (1) Resend the re-validated last offer. Re-validation checks the offer against CURRENT envelope/basket/gate/truth.
        if self.last_offer and self.state and self.state.basket:
            try:
                ok, _ = gate.check_outgoing(self.last_offer, self.state.basket, self.gate_env)
                items = self.last_offer.get("items")
                if ok and isinstance(items, list):
                    total = sum(i["qty"] * i["unit_price"] for i in items)
                    amounts = {total} | {i["unit_price"] for i in items} | {i["unit_price"] * i["qty"] for i in items}
                    t_errs = truth.check(self.last_offer.get("text", ""), amounts)
                    if not t_errs:
                        return self.last_offer
            except Exception:
                pass

        # (2) Plain walk_away message with no literal numbers
        fallback_text = "I must pass on this deal."
        try:
            rendered = renderer.render("walkaway", [], 0, store=self.store)
            if not truth.check(rendered, set()):
                fallback_text = rendered
        except Exception:
            pass

        return {
            "type": "walk_away",
            "text": fallback_text,
        }

    def _respond(self, message: dict) -> dict:
        parsed = parser.parse(message, self.store)
        if parsed.type in ("walk_away", "accept"):
            return {"type": "message", "text": "Thank you, goodbye."}

        if self.state is None:
            self.state = NegotiationState(self.store, self.policy, self.env, self.gate_env, config=self.cfg)

        view = self.state.view(parsed)
        if not self.state.basket:
            return {
                "type": "walk_away",
                "text": renderer.render(
                    "walkaway_nostock" if self.state.dropped else "walkaway",
                    [],
                    0,
                    self.state.dropped,
                    store=self.store,
                ),
            }

        decision = self.strategy.decide(view)

        if decision.action == Action.WALK_AWAY:
            return {
                "type": "walk_away",
                "text": renderer.render("walkaway", [], 0, self.state.dropped, store=self.store),
            }

        if decision.action == Action.ACCEPT:
            if gate.bid_valid_as_made(parsed.items, self.state.basket, self.gate_env):
                out = {
                    "type": "accept",
                    "items": parsed.items,
                    "text": renderer.render("accept", [], 0, store=self.store),
                }
                ok, _ = gate.check_outgoing(out, self.state.basket, self.gate_env)
                t_errs = truth.check(out["text"], set())
                if ok and not t_errs:
                    return out
                return self._fallback()

            # If invalid as made, convert to COUNTER at buyer's bid total using Mode.EXACT (or floor if below floor)
            buyer_total = None
            if isinstance(parsed.items, list):
                try:
                    buyer_total = sum(
                        int(i["qty"]) * int(i["unit_price"])
                        for i in parsed.items
                        if isinstance(i, dict)
                        and type(i.get("qty")) is int
                        and type(i.get("unit_price")) in (int, float)
                        and not isinstance(i.get("unit_price"), bool)
                        and math.isfinite(i["unit_price"])
                    )
                except Exception:
                    buyer_total = None

            if buyer_total is not None and buyer_total >= view.F:
                counter_total = min(buyer_total, view.L)
                target_mode = Mode.EXACT
            else:
                counter_total = view.F
                target_mode = Mode.AT_MOST

            ratio = counter_total / view.L if view.L else 1.0
            decision = Decision(
                action=Action.COUNTER,
                total=counter_total,
                mode=target_mode,
                ratio=ratio,
                reason="invalid_accept_converted_to_counter",
            )

        # Action.COUNTER
        target = decision.total if decision.total is not None else view.L
        if decision.mode == Mode.EXACT:
            repair_res = self.repair.allocate_exact(self.state.basket, self.env, target)
        else:
            repair_res = self.repair.allocate_at_most(self.state.basket, self.env, target)

        if repair_res.status not in (RepairStatus.EXACT, RepairStatus.AT_MOST) or not repair_res.prices:
            return self._fallback()

        items = [
            {"sku": k, "qty": q, "unit_price": repair_res.prices[k]}
            for k, q in self.state.basket.items()
        ]
        total = sum(i["qty"] * i["unit_price"] for i in items)
        template_kind = "open" if view.round == 1 else "counter"
        text = renderer.render(template_kind, items, total, self.state.dropped, store=self.store)
        out = {"type": "offer", "items": items, "text": text}

        # Gate check
        ok, reasons = gate.check_outgoing(out, self.state.basket, self.gate_env)
        # Truth check: numbers in play for this offer
        amounts = {total} | {i["unit_price"] for i in items} | {i["unit_price"] * i["qty"] for i in items}
        t_errs = truth.check(out["text"], amounts)
        if t_errs:
            # Fallback template
            out["text"] = renderer.render("plain_fallback", items, total, self.state.dropped, store=self.store)
            t_errs = truth.check(out["text"], amounts)
        if not ok or t_errs:
            return self._fallback()

        self.state.remember(out, decision)
        self.last_offer = out

        if self.log_path:
            try:
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "round": view.round,
                        "action": decision.action.value,
                        "total": total,
                        "ratio": decision.ratio,
                        "reason": decision.reason,
                        "gate_ok": ok,
                    }) + "\n")
            except Exception:
                pass

        return out
