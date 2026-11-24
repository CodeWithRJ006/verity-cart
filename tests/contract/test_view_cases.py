"""Tests contract conformance between state.view and expected View fixtures."""
import json
from pathlib import Path

from verity.envelope import Envelope
from verity.parser import parse
from verity.state import NegotiationState

FIXTURES_PATH = Path(__file__).resolve().parent / "view_cases.json"


def test_view_cases():
    assert FIXTURES_PATH.exists(), f"Missing fixtures file: {FIXTURES_PATH}"
    with open(FIXTURES_PATH, "r", encoding="utf-8") as f:
        cases = json.load(f)

    # Minimal dummy store and policy for testing
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

    for case in cases:
        state = NegotiationState(store, policy, env)
        for turn in case["turns"]:
            incoming = turn["incoming"]
            parsed = parse(incoming)
            view = state.view(parsed)
            expected = turn["expected_view"]
            for k, exp_val in expected.items():
                actual_val = getattr(view, k)
                assert actual_val == exp_val, f"Case {case['id']} turn mismatch on {k}: expected {exp_val}, got {actual_val}"
            if "remember" in turn:
                state.remember(turn["remember"])
