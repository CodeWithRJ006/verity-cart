"""Tests robustness, boundary safety, and garbage resistance of verity/parser.py."""
import math
import random
import string
import pytest

from verity.parser import parse, ParsedMsg


def test_parser_table_driven_cases():
    store = {"S001": {"stock": 10}, "S002": {"stock": 5}}

    cases = [
        # Duplicate SKU
        (
            {"type": "counter", "round": 2, "items": [{"sku": "S001", "qty": 1, "unit_price": 500}, {"sku": "S001", "qty": 1, "unit_price": 600}]},
            {"flags": ["dup_sku"], "line_count": 1}
        ),
        # NaN in price
        (
            {"type": "counter", "round": 2, "items": [{"sku": "S001", "qty": 1, "unit_price": float("nan")}]},
            {"flags": ["bad_price:S001"], "line_count": 0}
        ),
        # Inf in price
        (
            {"type": "counter", "round": 2, "items": [{"sku": "S001", "qty": 1, "unit_price": float("inf")}]},
            {"flags": ["bad_price:S001"], "line_count": 0}
        ),
        # -Inf in price
        (
            {"type": "counter", "round": 2, "items": [{"sku": "S001", "qty": 1, "unit_price": float("-inf")}]},
            {"flags": ["bad_price:S001"], "line_count": 0}
        ),
        # True as qty (bool is subclass of int)
        (
            {"type": "counter", "round": 2, "items": [{"sku": "S001", "qty": True, "unit_price": 500}]},
            {"flags": ["bad_qty:S001"], "line_count": 0}
        ),
        # False as unit_price
        (
            {"type": "counter", "round": 2, "items": [{"sku": "S001", "qty": 2, "unit_price": False}]},
            {"flags": ["bad_price:S001"], "line_count": 0}
        ),
        # String as qty ("5")
        (
            {"type": "counter", "round": 2, "items": [{"sku": "S001", "qty": "5", "unit_price": 500}]},
            {"flags": ["bad_qty:S001"], "line_count": 0}
        ),
        # Float as qty (5.5)
        (
            {"type": "counter", "round": 2, "items": [{"sku": "S001", "qty": 5.5, "unit_price": 500}]},
            {"flags": ["bad_qty:S001"], "line_count": 0}
        ),
        # Negative qty and price
        (
            {"type": "counter", "round": 2, "items": [{"sku": "S001", "qty": -1, "unit_price": -100}]},
            {"flags": ["bad_qty:S001"], "line_count": 0}
        ),
        # Missing keys completely
        (
            {},
            {"flags": ["bad_type", "missing_round"], "line_count": None, "type": "unknown", "round": 1}
        ),
        # None items
        (
            {"type": "offer", "round": 1, "items": None},
            {"line_count": None, "round": 1}
        ),
        # Items not a list
        (
            {"type": "offer", "round": 1, "items": "not a list"},
            {"flags": ["bad_items"], "line_count": None}
        ),
        # Nested junk
        (
            {"type": "request", "round": 1, "items": [{"sku": {"nested": "obj"}, "qty": [1, 2], "unit_price": None}, "junk_string", 42]},
            {"flags": ["bad_sku", "item_not_dict", "item_not_dict"], "line_count": 0}
        ),
        # 10k-character string in text and SKU
        (
            {"type": "counter", "round": 1, "text": "x" * 10000, "items": [{"sku": "y" * 10000, "qty": 1, "unit_price": 500}]},
            {"flags": ["unknown_sku:" + "y" * 10000], "line_count": 0}
        ),
    ]

    for raw, expected in cases:
        parsed = parse(raw, store=store)
        assert isinstance(parsed, ParsedMsg)
        if "flags" in expected:
            for flag in expected["flags"]:
                assert any(flag in f for f in parsed.flags), f"Expected flag {flag} not in {parsed.flags} for case {raw}"
        if "line_count" in expected:
            if expected["line_count"] is None:
                assert parsed.lines is None
            else:
                assert len(parsed.lines) == expected["line_count"]
        if "type" in expected:
            assert parsed.type == expected["type"]
        if "round" in expected:
            assert parsed.round == expected["round"]


def test_parser_seeded_random_garbage_corpus():
    rng = random.Random(42)
    corpus_size = 5000
    store = {"S001": {"stock": 10}, "S002": {"stock": 5}}

    garbage_types = [
        None,
        True,
        False,
        0,
        -42,
        3.14,
        float("nan"),
        float("inf"),
        "",
        "request",
        "counter",
        "a" * 100,
        [],
        [1, 2, "three"],
        {},
        {"nested": True},
    ]

    for i in range(corpus_size):
        # Generate random message structures
        mode = rng.randint(0, 5)
        if mode == 0:
            msg = rng.choice(garbage_types)
        elif mode == 1:
            msg = {rng.choice(string.ascii_letters): rng.choice(garbage_types) for _ in range(rng.randint(0, 10))}
        elif mode == 2:
            # Semi-structured message with mutated fields
            items = []
            for _ in range(rng.randint(0, 5)):
                items.append({
                    "sku": rng.choice([None, "", "S001", "S002", "S999", 123, True, "dup"]),
                    "qty": rng.choice([None, -1, 0, 1, 2, True, False, "1", 1.5, float("nan")]),
                    "unit_price": rng.choice([None, -10, 0, 500, True, False, "500", 500.5, float("inf"), float("nan")])
                })
            msg = {
                "type": rng.choice(["request", "counter", "accept", "walk_away", None, 123, ""]),
                "round": rng.choice([None, -1, 0, 1, 5, 10, True, False, "5", 5.5]),
                "items": items if rng.random() > 0.1 else rng.choice(garbage_types),
                "text": "".join(rng.choices(string.printable, k=rng.randint(0, 200)))
            }
        else:
            # Deeply nested junk
            msg = {"data": [rng.choice(garbage_types) for _ in range(rng.randint(1, 5))]}

        # Invariant: parse must NEVER raise on any input
        try:
            res = parse(msg, store=store)
            assert isinstance(res, ParsedMsg)
            assert isinstance(res.flags, list)
            assert isinstance(res.round, int) and res.round >= 1
            assert isinstance(res.type, str)
        except Exception as e:
            pytest.fail(f"parse() raised {type(e).__name__} on input {msg!r} at iteration {i}: {e}")

    print(f"\n[CORPUS] Successfully fuzz-tested {corpus_size} random garbage payloads without exceptions.")
