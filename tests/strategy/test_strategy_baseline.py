"""Unit and differential tests for verity/strategy_baseline.py (ablation row B0).

Unit tests drive synthetic Views through every branch of the kit example
seller's rule (kit/example_seller.py:24-58):

  open    first message -> offer at list (kit/example_seller.py:35)
  decay   later "counter" -> close a quarter of the gap to the floor (:36-38)
  repeat  later "request" -> previous offer again (:36)
  accept  complete, valid bid on a request or counter (:40-41, 47-58)
  walk    L == 0, i.e. nothing in stock (:33-34)
  cfg     strategy parameters are stored but never read

Differential test: 4 seeds x the 3 public buyers through
kit/harness.run_negotiation, comparing each seller turn's message type and
TOTAL (sum qty*unit_price; for an accept, the total of the bid being accepted).
Per-line prices are NOT compared: the example rounds each line up
(kit/example_seller.py:38) while B0 allocates its total through repair.
"""
from __future__ import annotations

import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "kit"
if str(KIT) not in sys.path:
    sys.path.insert(0, str(KIT))

import buyers  # noqa: E402
from harness import load_class, load_policy, load_store, run_negotiation  # noqa: E402

from verity.config import Config  # noqa: E402
from verity.contracts import Action, Mode, View  # noqa: E402
from verity.seller import Seller as VeritySeller  # noqa: E402
from verity.strategy_baseline import Strategy  # noqa: E402


def _view(
    *,
    round: int = 1,
    msg_type: str = "request",
    L: int = 1000,
    F: int = 700,
    bids=(),
    bid_complete: bool = False,
    bid_valid_as_made: bool = False,
    last_offer_ratio=None,
) -> View:
    return View(
        round=round,
        msg_type=msg_type,
        L=L,
        F=F,
        bids=list(bids),
        bid_complete=bid_complete,
        bid_valid_as_made=bid_valid_as_made,
        last_offer_ratio=last_offer_ratio,
    )


def _decide(view: View, cfg=None):
    return Strategy(cfg if cfg is not None else Config()).decide(view)


# ---------------------------------------------------------------------------
# open
# ---------------------------------------------------------------------------

def test_first_turn_offers_list():
    d = _decide(_view(round=1, bids=[], last_offer_ratio=None))
    assert d.action == Action.COUNTER
    assert d.mode == Mode.AT_MOST
    assert d.total == 1000
    assert d.ratio == 1.0
    assert d.reason == "baseline_open"


def test_first_message_counter_is_not_decayed():
    """kit/example_seller.py:29-38: the decay is in the `elif`, so a first
    message of type "counter" still offers at list, undecayed."""
    v = _view(round=1, msg_type="counter", bids=[0.9], last_offer_ratio=None)
    d = _decide(v)
    assert d.reason == "baseline_open"
    assert d.total == 1000
    assert d.ratio == 1.0


# ---------------------------------------------------------------------------
# accept
# ---------------------------------------------------------------------------

def test_accept_on_complete_valid_request():
    v = _view(msg_type="request", bids=[0.92], bid_complete=True,
              bid_valid_as_made=True, last_offer_ratio=None)
    d = _decide(v)
    assert d.action == Action.ACCEPT
    assert d.reason == "baseline_accept"


def test_accept_on_complete_valid_counter():
    v = _view(msg_type="counter", bids=[0.75], bid_complete=True,
              bid_valid_as_made=True, last_offer_ratio=0.8)
    assert _decide(v).action == Action.ACCEPT


def test_no_accept_when_bid_incomplete():
    """Structural half of acceptable(): every line, exact quantities."""
    v = _view(msg_type="counter", bids=[0.95], bid_complete=False,
              bid_valid_as_made=True, last_offer_ratio=0.9)
    d = _decide(v)
    assert d.action == Action.COUNTER
    assert d.reason == "baseline_counter"


def test_no_accept_when_bid_invalid_as_made():
    """Price half of acceptable(): each line at or above its floor."""
    v = _view(msg_type="counter", bids=[0.3], bid_complete=True,
              bid_valid_as_made=False, last_offer_ratio=0.9)
    assert _decide(v).action == Action.COUNTER


def test_no_accept_on_other_message_types():
    """kit/example_seller.py:40 accepts only on request and counter."""
    v = _view(msg_type="message", bids=[0.95], bid_complete=True,
              bid_valid_as_made=True, last_offer_ratio=0.9)
    assert _decide(v).action == Action.COUNTER


# ---------------------------------------------------------------------------
# decay / repeat (integer arithmetic)
# ---------------------------------------------------------------------------

def test_counter_decays_a_quarter_of_the_gap():
    # T = round(0.9 * 1000) = 900; ceil((3*900 + 700)/4) = ceil(850) = 850.
    v = _view(msg_type="counter", bids=[0.7], last_offer_ratio=0.9)
    d = _decide(v)
    assert d.action == Action.COUNTER
    assert d.mode == Mode.AT_MOST
    assert d.total == 850
    assert d.ratio == 0.85
    assert d.reason == "baseline_counter"


def test_counter_rounds_up_with_integer_ceil():
    # T = 710; (3*710 + 700) / 4 = 707.5 -> 708 (ceil, not round-to-even).
    d = _decide(_view(msg_type="counter", last_offer_ratio=0.71))
    assert d.total == 708


def test_counter_never_goes_below_floor():
    # T = 700: (2100 + 700) / 4 = 700 exactly.
    d = _decide(_view(msg_type="counter", last_offer_ratio=0.7))
    assert d.total == 700
    # A ratio that rounds below the floor is clamped.
    d = _decide(_view(msg_type="counter", last_offer_ratio=0.5))
    assert d.total == 700
    assert d.ratio == 0.7


def test_counter_from_list_still_decays():
    # T = 1000; ceil((3*1000 + 700)/4) = 925, as the example's per-line ceil does.
    d = _decide(_view(msg_type="counter", last_offer_ratio=1.0))
    assert d.total == 925


def test_floor_equals_list_stays_put():
    v = _view(msg_type="counter", L=1000, F=1000, last_offer_ratio=1.0)
    d = _decide(v)
    assert d.total == 1000
    assert d.ratio == 1.0


def test_later_request_repeats_previous_offer():
    """kit/example_seller.py:36 only decays on "counter"."""
    d = _decide(_view(msg_type="request", last_offer_ratio=0.85))
    assert d.total == 850
    assert d.ratio == 0.85
    assert d.reason == "baseline_repeat"


# ---------------------------------------------------------------------------
# walk + config independence
# ---------------------------------------------------------------------------

def test_empty_basket_walks():
    d = _decide(_view(L=0, F=0, bids=[], last_offer_ratio=None))
    assert d.action == Action.WALK_AWAY
    assert d.reason == "baseline_empty"


def test_strategy_parameters_are_ignored():
    """B0 is the example's rule: no target curve, markup, slack or round rule."""
    tuned = Config(T=1.0, e=2.0, slack=0.5, m=0.4, g=1.0, walk_slack=0.8,
                   max_round=3, accept_require_complete=True)
    views = [
        _view(msg_type="request", last_offer_ratio=None),
        _view(msg_type="counter", last_offer_ratio=0.9),
        _view(msg_type="request", last_offer_ratio=0.85),
        _view(msg_type="counter", last_offer_ratio=0.7),
        _view(msg_type="counter", bid_complete=True, bid_valid_as_made=True,
              last_offer_ratio=0.9),
    ]
    for v in views:
        assert Strategy(Config()).decide(v) == Strategy(tuned).decide(v)


def test_construction_never_raises_for_any_valid_config():
    for allocator in ("proportional", "greedy"):
        assert Strategy(Config(allocator=allocator))._cfg is not None


# ---------------------------------------------------------------------------
# differential: B0 through verity.seller vs kit/example_seller.py
# ---------------------------------------------------------------------------

def _turns(result):
    """(type, TOTAL) per seller turn; TOTAL of an accept is the accepted bid."""
    out = []
    last_bid = None
    for m in result["transcript"]:
        if m.get("from") == "buyer":
            items = m.get("items")
            if m.get("type") in ("request", "counter") and isinstance(items, list):
                try:
                    last_bid = sum(i["qty"] * i["unit_price"] for i in items)
                except (KeyError, TypeError):
                    last_bid = None
            continue
        kind = m.get("type")
        if kind == "offer":
            items = m.get("items") or []
            total = sum(i["qty"] * i["unit_price"] for i in items)
        elif kind == "accept":
            total = last_bid
        else:
            total = None
        out.append((kind, total))
    return out


def test_differential_vs_example_seller(monkeypatch):
    """Seeds 0-3 x 3 buyers: identical message types, totals within 4*sum(qty).

    Derived bound: the example rounds each line up, so its total exceeds the
    unrounded aggregate by delta in [0, Q) with Q = sum(qty) (one ceil error per
    unit, kit/example_seller.py:38).  Both sides then contract toward F by 0.75:
    d_{k+1} <= 0.75*d_k + Q  =>  d <= 4Q.  B0's own ceil adds at most 1 per
    round, already inside that budget for Q >= 1.
    """
    store, policy = load_store(), load_policy()
    # load_class partitions on ":" (kit/harness.py:273), so a Windows drive
    # letter cannot appear in the path: pass it relative to the cwd.
    example_path = os.path.relpath(str(KIT / "example_seller.py"))
    example_cls = load_class(example_path, "Seller")

    monkeypatch.setenv("VERITY_IMPL", "baseline")
    monkeypatch.delenv("VERITY_SWITCHES", raising=False)
    monkeypatch.delenv("VERITY_LOG", raising=False)

    turns_compared = 0
    total_mismatches = 0
    max_delta = 0
    type_mismatches = []
    first_total_trace = None

    for seed in (0, 1, 2, 3):
        scenarios = buyers.make_scenarios(store, policy, 3, seed, buyers.BUYERS)
        for sc in scenarios:
            example = example_cls(store, policy)
            baseline = VeritySeller(store, policy)
            buyer_ex = buyers.BUYERS[sc["buyer"]](sc, store, random.Random(sc["seed"]))
            buyer_bl = buyers.BUYERS[sc["buyer"]](sc, store, random.Random(sc["seed"]))
            res_ex = run_negotiation(example, buyer_ex, store, policy, sc["id"])
            res_bl = run_negotiation(baseline, buyer_bl, store, policy, sc["id"])

            basket_qty = sum(
                min(i["qty"], store[i["sku"]]["stock"])
                for i in sc["items"]
                if i["sku"] in store and store[i["sku"]]["stock"] > 0
            )
            bound = 4 * basket_qty
            t_ex, t_bl = _turns(res_ex), _turns(res_bl)

            if len(t_ex) != len(t_bl):
                type_mismatches.append(
                    "seed=%d buyer=%s id=%s: turn count %d vs %d\n  example=%r\n  baseline=%r"
                    % (seed, sc["buyer"], sc["id"], len(t_ex), len(t_bl), t_ex, t_bl)
                )
                continue

            for k, ((kind_ex, total_ex), (kind_bl, total_bl)) in enumerate(zip(t_ex, t_bl)):
                turns_compared += 1
                if kind_ex != kind_bl:
                    type_mismatches.append(
                        "seed=%d buyer=%s id=%s turn %d: type %r vs %r\n"
                        "  example =%r\n  baseline=%r"
                        % (seed, sc["buyer"], sc["id"], k + 1,
                           kind_ex, kind_bl, total_ex, total_bl)
                    )
                    continue
                if total_ex is None and total_bl is None:
                    continue
                delta = abs((total_ex or 0) - (total_bl or 0))
                max_delta = max(max_delta, delta)
                if delta:
                    total_mismatches += 1
                    if first_total_trace is None:
                        first_total_trace = (
                            "seed=%d buyer=%s id=%s turn %d type=%s "
                            "example=%r baseline=%r delta=%d bound=%d"
                            % (seed, sc["buyer"], sc["id"], k + 1, kind_ex,
                               total_ex, total_bl, delta, bound)
                        )
                assert delta <= bound, (
                    "total delta %d exceeds derived bound 4*%d on seed=%d buyer=%s id=%s "
                    "turn %d (example=%r baseline=%r)"
                    % (delta, basket_qty, seed, sc["buyer"], sc["id"], k + 1,
                       total_ex, total_bl)
                )

    rate = (total_mismatches / turns_compared) if turns_compared else 0.0
    print("\nnegotiations compared: 12 (%d buyer-scenario turns)" % turns_compared)
    print("type mismatches: %d" % len(type_mismatches))
    print("total mismatches: %d/%d (%.1f%%), max |delta|: %d"
          % (total_mismatches, turns_compared, 100 * rate, max_delta))
    if first_total_trace:
        print("first total delta: " + first_total_trace)

    assert not type_mismatches, "\n".join(type_mismatches[:3])
    assert turns_compared > 0
