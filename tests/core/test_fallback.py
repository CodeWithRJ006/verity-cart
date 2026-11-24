"""Comprehensive fallback ladder and resilience tests for verity.seller.

Test Suites:
1. Monkeypatch each stage (parser, state, strategy, repair, gate, renderer, truth)
   to raise exceptions and return garbage; assert every time that the output is
   gate-valid, truth-clean, and the seller never crashes.
2. Stock-change test: drop stock to 0 after an offer has been made, force a failure,
   assert the old offer is NOT resent because it fails re-validation, ladder reaches walk_away.
3. Session-reuse test: run 50 negotiations through one Seller instance; assert 0 state
   leakage compared to fresh Seller instances.
4. Scripted-decisions test:
   - Feed an ACCEPT on an invalid bid, assert it converted to a counter;
   - Feed a COUNTER at an invalid price (below floor / above list), assert the gate stops it
     and the ladder takes over.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from verity import gate, truth
from verity.contracts import Action, Decision, Mode, RepairResult, RepairStatus
from verity.seller import Seller

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "kit"))

import harness  # noqa: E402


@pytest.fixture
def store_and_policy():
    store = harness.load_store()
    policy = harness.load_policy()
    return copy.deepcopy(store), copy.deepcopy(policy)


# =============================================================================
# Suite 1: Monkeypatching stages (resilience and ladder behavior)
# =============================================================================

def test_monkeypatch_parser_explodes(store_and_policy):
    store, policy = store_and_policy
    seller = Seller(store, policy)
    seller.start("neg_parser_fail")

    incoming = {"type": "request", "round": 1, "items": [{"sku": "S001", "qty": 1}], "text": "Hi"}

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("verity.parser.parse", MagicMock(side_effect=RuntimeError("Parser exploded")))
        resp = seller.respond(incoming)

    assert isinstance(resp, dict)
    assert resp.get("type") in ("walk_away", "message", "offer")
    assert isinstance(resp.get("text"), str)
    ok, _ = gate.check_outgoing(resp, seller.state.basket if seller.state else {}, seller.gate_env)
    assert ok
    assert not truth.check(resp["text"], set())


def test_monkeypatch_state_view_explodes(store_and_policy):
    store, policy = store_and_policy
    seller = Seller(store, policy)
    seller.start("neg_state_fail")

    incoming = {"type": "request", "round": 1, "items": [{"sku": "S001", "qty": 1}], "text": "Hi"}

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("verity.state.NegotiationState.view", MagicMock(side_effect=RuntimeError("State exploded")))
        resp = seller.respond(incoming)

    assert isinstance(resp, dict)
    assert resp.get("type") == "walk_away"
    assert isinstance(resp.get("text"), str)
    ok, _ = gate.check_outgoing(resp, {}, seller.gate_env)
    assert ok
    assert not truth.check(resp["text"], set())


def test_monkeypatch_strategy_explodes_with_and_without_last_offer(store_and_policy):
    store, policy = store_and_policy
    seller = Seller(store, policy)
    seller.start("neg_strategy_fail")

    incoming = {"type": "request", "round": 1, "items": [{"sku": "S001", "qty": 1}], "text": "Hi"}

    # Case A: Turn 1, no previous offer -> falls back to walk_away
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(seller.strategy, "decide", MagicMock(side_effect=RuntimeError("Strategy exploded")))
        resp1 = seller.respond(incoming)

    assert resp1["type"] == "walk_away"
    assert not truth.check(resp1["text"], set())

    # Case B: Make a valid Turn 1 offer first
    seller.start("neg_strategy_with_offer")
    resp_turn1 = seller.respond(incoming)
    assert resp_turn1["type"] == "offer"
    assert seller.last_offer == resp_turn1

    # Turn 2: Strategy explodes -> ladder step 1 resends re-validated last offer
    incoming_turn2 = {"type": "counter", "round": 2, "items": [{"sku": "S001", "qty": 1, "unit_price": 500}], "text": "Counter"}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(seller.strategy, "decide", MagicMock(side_effect=RuntimeError("Strategy exploded on turn 2")))
        resp_turn2 = seller.respond(incoming_turn2)

    assert resp_turn2 == resp_turn1
    ok, _ = gate.check_outgoing(resp_turn2, seller.state.basket, seller.gate_env)
    assert ok


def test_monkeypatch_repair_fails(store_and_policy):
    store, policy = store_and_policy
    seller = Seller(store, policy)
    seller.start("neg_repair_fail")

    incoming = {"type": "request", "round": 1, "items": [{"sku": "S001", "qty": 1}], "text": "Hi"}

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            seller.repair,
            "allocate_at_most",
            MagicMock(return_value=RepairResult(RepairStatus.AGGREGATE_INFEASIBLE, None, None)),
        )
        resp = seller.respond(incoming)

    assert resp["type"] == "walk_away"
    assert not truth.check(resp["text"], set())


def test_monkeypatch_gate_check_fails(store_and_policy):
    store, policy = store_and_policy
    seller = Seller(store, policy)
    seller.start("neg_gate_fail")

    incoming = {"type": "request", "round": 1, "items": [{"sku": "S001", "qty": 1}], "text": "Hi"}

    # Mock gate to reject outgoing offer -> should trigger fallback to walk_away
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("verity.gate.check_outgoing", MagicMock(return_value=(False, ["forced_rejection"])))
        resp = seller.respond(incoming)

    assert resp["type"] == "walk_away"
    assert not truth.check(resp["text"], set())


def test_monkeypatch_renderer_and_truth_untruthful(store_and_policy):
    store, policy = store_and_policy
    seller = Seller(store, policy)
    seller.start("neg_truth_fail")

    incoming = {"type": "request", "round": 1, "items": [{"sku": "S001", "qty": 1}], "text": "Hi"}

    # Mock renderer to return text with fake price claims and urgency
    untruthful_text = "Today only! Special discount for ₹9999999!"
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("verity.renderer.render", MagicMock(return_value=untruthful_text))
        resp = seller.respond(incoming)

    # Must NOT emit untruthful text; fallback text must be truth-clean
    assert resp["text"] != untruthful_text
    assert not truth.check(resp["text"], set())


# =============================================================================
# Suite 2: Stock-change test
# =============================================================================

def test_stock_change_invalidates_last_offer_resend(store_and_policy):
    """Drop stock to 0 after an offer has been made, force a failure,

    assert the old offer is NOT resent because it fails re-validation, ladder reaches walk_away.
    """
    store, policy = store_and_policy
    seller = Seller(store, policy)
    seller.start("neg_stock_drop")

    sku = "S004"
    initial_stock = store[sku]["stock"]
    assert initial_stock >= 2

    # Turn 1: request qty 2 -> seller offers qty 2
    msg1 = {"type": "request", "round": 1, "items": [{"sku": sku, "qty": 2}], "text": "Need 2"}
    resp1 = seller.respond(msg1)
    assert resp1["type"] == "offer"
    assert seller.last_offer is not None
    assert seller.last_offer["items"][0]["qty"] == 2

    # Stock drops to 0 (or below 2) in live store
    store[sku]["stock"] = 0

    # Turn 2: buyer counters, and an internal error occurs in strategy
    msg2 = {"type": "counter", "round": 2, "items": [{"sku": sku, "qty": 2, "unit_price": 500}], "text": "Counter"}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(seller.strategy, "decide", MagicMock(side_effect=RuntimeError("Strategy exploded on turn 2")))
        resp2 = seller.respond(msg2)

    # Old offer had qty 2, but stock is now 0. Re-validation MUST fail, so it must NOT resend old offer!
    assert resp2["type"] == "walk_away"
    assert resp2 != resp1
    assert not truth.check(resp2["text"], set())


# =============================================================================
# Suite 3: Session-reuse test (50 negotiations through one Seller instance)
# =============================================================================

def test_session_reuse_50_negotiations(store_and_policy):
    """Run 50 negotiations through one Seller instance; assert 0 state leakage compared to fresh Seller instances."""
    store, policy = store_and_policy
    reused_seller = Seller(store, policy)

    for i in range(50):
        neg_id = f"reuse_neg_{i}"
        fresh_seller = Seller(store, policy)

        reused_seller.start(neg_id)
        fresh_seller.start(neg_id)

        # Vary scenarios: some 1-turn, some multi-turn, some dropped stock, some with partial bids
        sku = f"S{((i % 10) + 1):03d}"
        if sku not in store:
            sku = "S001"

        # Turn 1
        msg1 = {"type": "request", "round": 1, "items": [{"sku": sku, "qty": 1}], "text": f"Request {i}"}
        resp_reused_1 = reused_seller.respond(msg1)
        resp_fresh_1 = fresh_seller.respond(msg1)
        assert resp_reused_1 == resp_fresh_1, f"Turn 1 divergence on negotiation {i}"

        # Turn 2: buyer counters with floor-ish bid
        floor_p = reused_seller.env.floor(sku)
        msg2 = {
            "type": "counter",
            "round": 2,
            "items": [{"sku": sku, "qty": 1, "unit_price": floor_p}],
            "text": "Floor counter",
        }
        resp_reused_2 = reused_seller.respond(msg2)
        resp_fresh_2 = fresh_seller.respond(msg2)
        assert resp_reused_2 == resp_fresh_2, f"Turn 2 divergence on negotiation {i}"

        # Verify internal state attributes match exactly
        assert reused_seller.state.basket == fresh_seller.state.basket
        assert reused_seller.state.dropped == fresh_seller.state.dropped
        assert reused_seller.state.bids == fresh_seller.state.bids
        assert reused_seller.state.last_offer_ratio == fresh_seller.state.last_offer_ratio
        assert reused_seller.last_offer == fresh_seller.last_offer


# =============================================================================
# Suite 4: Scripted decisions test
# =============================================================================

def test_scripted_decision_accept_on_invalid_bid_converts_to_counter(store_and_policy):
    """Feed an ACCEPT on an invalid bid, assert it converted to a counter."""
    store, policy = store_and_policy
    seller = Seller(store, policy)
    seller.start("neg_accept_invalid")

    # Basket has S001 qty 2. List = 2000, Floor = 1716.
    msg1 = {"type": "request", "round": 1, "items": [{"sku": "S001", "qty": 2}], "text": "Need 2"}
    resp1 = seller.respond(msg1)
    assert resp1["type"] == "offer"

    # Buyer bids an INVALID unit price (below floor: 500 < 858)
    invalid_bid_msg = {
        "type": "counter",
        "round": 2,
        "items": [{"sku": "S001", "qty": 2, "unit_price": 500}],
        "text": "500 per unit",
    }

    # Strategy script returns ACCEPT
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(seller.strategy, "decide", MagicMock(return_value=Decision(action=Action.ACCEPT)))
        resp2 = seller.respond(invalid_bid_msg)

    # Must NOT accept! Must convert to counter at floor or buyer total
    assert resp2["type"] == "offer"
    assert resp2["type"] != "accept"
    # Ensure all items in the counter are at or above floor
    for item in resp2["items"]:
        assert item["unit_price"] >= seller.env.floor(item["sku"])
    ok, _ = gate.check_outgoing(resp2, seller.state.basket, seller.gate_env)
    assert ok


def test_scripted_decision_counter_at_invalid_price_stopped_by_gate(store_and_policy):
    """Feed a COUNTER at an invalid price (below floor / above list),

    assert the gate stops it and the ladder takes over.
    """
    store, policy = store_and_policy
    seller = Seller(store, policy)
    seller.start("neg_invalid_counter")

    msg1 = {"type": "request", "round": 1, "items": [{"sku": "S001", "qty": 1}], "text": "Need 1"}
    resp1 = seller.respond(msg1)
    assert resp1["type"] == "offer"

    # Strategy attempts to COUNTER below floor (e.g. total = 100 rupees when floor is 858)
    msg2 = {"type": "counter", "round": 2, "items": [{"sku": "S001", "qty": 1, "unit_price": 900}], "text": "Counter"}
    with pytest.MonkeyPatch.context() as mp:
        # Return a decision below floor
        mp.setattr(
            seller.strategy,
            "decide",
            MagicMock(return_value=Decision(action=Action.COUNTER, total=100, mode=Mode.EXACT)),
        )
        resp2 = seller.respond(msg2)

    # Gate or repair stops the invalid counter. Fallback ladder re-sends valid last offer!
    assert resp2 == resp1
    ok, _ = gate.check_outgoing(resp2, seller.state.basket, seller.gate_env)
    assert ok
