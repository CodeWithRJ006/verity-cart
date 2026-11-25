"""Tests contract conformance for partial_bid_policy='matched' view cases."""
import json
from pathlib import Path

from verity.config import Config
from verity.contracts import Action, Decision, Mode
from verity.envelope import Envelope
from verity.parser import parse
from verity.state import NegotiationState

FIXTURES_PATH = Path(__file__).resolve().parent / "view_cases_matched.json"


def test_view_cases_matched():
    assert FIXTURES_PATH.exists(), f"Missing fixtures file: {FIXTURES_PATH}"
    with open(FIXTURES_PATH, "r", encoding="utf-8") as f:
        cases = json.load(f)

    store = {
        "S001": {"sku": "S001", "name": "Item 1", "category": "apparel", "price": 1000, "cost": 600, "stock": 10},
        "S002": {"sku": "S002", "name": "Item 2", "category": "apparel", "price": 1200, "cost": 700, "stock": 5},
        "S003": {"sku": "S003", "name": "Item 3 (OOS)", "category": "apparel", "price": 800, "cost": 400, "stock": 0},
        "S004": {"sku": "S004", "name": "Item 4", "category": "apparel", "price": 500, "cost": 300, "stock": 20},
    }
    policy = {
        "max_discount": 0.25,
        "min_margin": {"apparel": 0.3},
    }
    env = Envelope(store, policy)
    cfg = Config(partial_bid_policy="matched")

    for case in cases:
        state = NegotiationState(store, policy, env, config=cfg)
        for turn in case["turns"]:
            incoming = turn["incoming"]
            parsed = parse(incoming, store)
            view = state.view(parsed)
            expected = turn["expected_view"]
            for k, exp_val in expected.items():
                actual_val = getattr(view, k)
                assert actual_val == exp_val, (
                    f"Case {case['id']} turn {turn['incoming']['round']} mismatch on {k}: "
                    f"expected {exp_val}, got {actual_val}"
                )
            if "remember" in turn:
                rem = turn["remember"]
                if isinstance(rem, dict) and "decision_ratio" in rem:
                    dec = Decision(
                        action=Action.COUNTER,
                        total=1000,
                        mode=Mode.AT_MOST,
                        ratio=rem["decision_ratio"],
                    )
                    state.remember(rem["offer"], decision=dec)
                else:
                    state.remember(rem)
