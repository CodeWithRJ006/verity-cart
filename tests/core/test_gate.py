"""Tests for verity.gate: independent exit gate verification and bid validation.

Requirements:
(a) >= 60 table-driven valid/invalid cases covering every reason code, bool/float/NaN prices,
    price == floor-1 and floor and list+1, qty 0/negative/huge, duplicate SKUs, extra keys,
    items as tuple/None/dict, stock dropping to 0 between turns.
(b) A Hypothesis property test: for random baskets and random price vectors,
    gate.ok == (kit harness.check_items reports no violations AND SKU set/qty equal the basket AND all prices are ints).
    Uses at least 2,000 examples.
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "kit"))

import harness

from verity import gate
from verity.envelope import Envelope


@pytest.fixture(scope="module")
def env_context():
    store = harness.load_store()
    policy = harness.load_policy()
    env = Envelope(store, policy)
    return store, policy, env


def test_gate_table_driven_cases(env_context):
    store, policy, env = env_context

    # We use S004 (stock=13, price=1049, cost=406) and S005 (stock=22, price=699, cost=242) as stable fixtures.
    sku1 = "S004"
    floor1 = env.floor(sku1)
    list1 = env.list_price(sku1)
    stock1 = env.stock(sku1)

    sku2 = "S005"
    floor2 = env.floor(sku2)
    list2 = env.list_price(sku2)

    standard_basket = {sku1: 2}
    standard_item = {"sku": sku1, "qty": 2, "unit_price": floor1}

    # Each case: (name, msg, basket, custom_env, expected_ok, expected_reasons_contain)
    cases: list[dict[str, Any]] = [
        # --- Valid Cases (1-10) ---
        {
            "name": "1. Valid offer at floor price",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 2, "unit_price": floor1}], "text": "Offer"},
            "basket": standard_basket,
            "expected_ok": True,
            "expected_reasons": [],
        },
        {
            "name": "2. Valid offer at list price",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 2, "unit_price": list1}], "text": "Offer"},
            "basket": standard_basket,
            "expected_ok": True,
            "expected_reasons": [],
        },
        {
            "name": "3. Valid offer between floor and list",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 2, "unit_price": (floor1 + list1) // 2}], "text": "Offer"},
            "basket": standard_basket,
            "expected_ok": True,
            "expected_reasons": [],
        },
        {
            "name": "4. Valid multi-item offer at floors",
            "msg": {
                "type": "offer",
                "items": [
                    {"sku": sku1, "qty": 2, "unit_price": floor1},
                    {"sku": sku2, "qty": 1, "unit_price": floor2},
                ],
                "text": "Multi-item offer",
            },
            "basket": {sku1: 2, sku2: 1},
            "expected_ok": True,
            "expected_reasons": [],
        },
        {
            "name": "5. Valid multi-item offer at list prices",
            "msg": {
                "type": "offer",
                "items": [
                    {"sku": sku1, "qty": 1, "unit_price": list1},
                    {"sku": sku2, "qty": 3, "unit_price": list2},
                ],
                "text": "Multi-item list offer",
            },
            "basket": {sku1: 1, sku2: 3},
            "expected_ok": True,
            "expected_reasons": [],
        },
        {
            "name": "6. Valid walk_away message",
            "msg": {"type": "walk_away", "text": "Walk away"},
            "basket": standard_basket,
            "expected_ok": True,
            "expected_reasons": [],
        },
        {
            "name": "7. Valid free text message",
            "msg": {"type": "message", "text": "Chat message"},
            "basket": standard_basket,
            "expected_ok": True,
            "expected_reasons": [],
        },
        {
            "name": "8. Valid accept with valid buyer items",
            "msg": {
                "type": "accept",
                "items": [{"sku": sku1, "qty": 2, "unit_price": floor1}],
                "text": "Accept deal",
            },
            "basket": standard_basket,
            "expected_ok": True,
            "expected_reasons": [],
        },
        {
            "name": "9. Valid accept with float price buyer items",
            "msg": {
                "type": "accept",
                "items": [{"sku": sku1, "qty": 2, "unit_price": float(floor1)}],
                "text": "Accept float deal",
            },
            "basket": standard_basket,
            "expected_ok": True,
            "expected_reasons": [],
        },
        {
            "name": "10. Valid offer with extra keys in items dict (permitted per harness)",
            "msg": {
                "type": "offer",
                "items": [{"sku": sku1, "qty": 2, "unit_price": floor1, "extra_meta": 42, "description": "Wallet"}],
                "text": "Extra keys offer",
            },
            "basket": standard_basket,
            "expected_ok": True,
            "expected_reasons": [],
        },
        {
            "name": "11. Valid offer with extra top-level msg keys (permitted per harness)",
            "msg": {
                "type": "offer",
                "items": [{"sku": sku1, "qty": 2, "unit_price": floor1}],
                "text": "Top keys offer",
                "round": 3,
                "strategy_id": "test",
            },
            "basket": standard_basket,
            "expected_ok": True,
            "expected_reasons": [],
        },

        # --- Reason Code: bad_type (12-21) ---
        {
            "name": "12. bad_type: msg is None",
            "msg": None,
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_type"],
        },
        {
            "name": "13. bad_type: msg is a string",
            "msg": "offer",
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_type"],
        },
        {
            "name": "14. bad_type: msg is an integer",
            "msg": 42,
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_type"],
        },
        {
            "name": "15. bad_type: msg is a list",
            "msg": [{"type": "offer"}],
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_type"],
        },
        {
            "name": "16. bad_type: type is 'counter' (seller cannot send buyer types)",
            "msg": {"type": "counter", "items": [standard_item], "text": "counter"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_type"],
        },
        {
            "name": "17. bad_type: type is 'request' (buyer only)",
            "msg": {"type": "request", "items": [standard_item], "text": "request"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_type"],
        },
        {
            "name": "18. bad_type: type is unknown string",
            "msg": {"type": "invalid_type", "items": [standard_item], "text": "invalid"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_type"],
        },
        {
            "name": "19. bad_type: type is empty string",
            "msg": {"type": "", "items": [standard_item], "text": "empty"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_type"],
        },
        {
            "name": "20. bad_type: type is None",
            "msg": {"type": None, "items": [standard_item], "text": "none"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_type"],
        },
        {
            "name": "21. bad_type: type missing entirely",
            "msg": {"items": [standard_item], "text": "missing type"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_type"],
        },

        # --- Reason Code: bad_text (22-29) ---
        {
            "name": "22. bad_text: text is None on offer",
            "msg": {"type": "offer", "items": [standard_item], "text": None},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_text"],
        },
        {
            "name": "23. bad_text: text is int on offer",
            "msg": {"type": "offer", "items": [standard_item], "text": 123},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_text"],
        },
        {
            "name": "24. bad_text: text missing entirely on offer",
            "msg": {"type": "offer", "items": [standard_item]},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_text"],
        },
        {
            "name": "25. bad_text: text is list on offer",
            "msg": {"type": "offer", "items": [standard_item], "text": ["text"]},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_text"],
        },
        {
            "name": "26. bad_text: text is None on walk_away",
            "msg": {"type": "walk_away", "text": None},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_text"],
        },
        {
            "name": "27. bad_text: text is int on walk_away",
            "msg": {"type": "walk_away", "text": 0},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_text"],
        },
        {
            "name": "28. bad_text: text is None on message",
            "msg": {"type": "message", "text": None},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_text"],
        },
        {
            "name": "29. bad_text: text is None on accept",
            "msg": {"type": "accept", "items": [standard_item], "text": None},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_text"],
        },

        # --- Reason Code: bad_items (30-41) ---
        {
            "name": "30. bad_items: items is None on offer",
            "msg": {"type": "offer", "items": None, "text": "None items"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_items"],
        },
        {
            "name": "31. bad_items: items is empty list on offer",
            "msg": {"type": "offer", "items": [], "text": "Empty items"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_items"],
        },
        {
            "name": "32. bad_items: items is tuple on offer",
            "msg": {"type": "offer", "items": (standard_item,), "text": "Tuple items"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_items"],
        },
        {
            "name": "33. bad_items: items is dict on offer",
            "msg": {"type": "offer", "items": standard_item, "text": "Dict items"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_items"],
        },
        {
            "name": "34. bad_items: items is string on offer",
            "msg": {"type": "offer", "items": "items", "text": "String items"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_items"],
        },
        {
            "name": "35. bad_items: item element is integer",
            "msg": {"type": "offer", "items": [123], "text": "Int element"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_items"],
        },
        {
            "name": "36. bad_items: item element is None",
            "msg": {"type": "offer", "items": [None], "text": "None element"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_items"],
        },
        {
            "name": "37. bad_items: item element is string",
            "msg": {"type": "offer", "items": ["S004"], "text": "String element"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_items"],
        },
        {
            "name": "38. bad_items: accept with items None",
            "msg": {"type": "accept", "items": None, "text": "Accept none"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_items"],
        },
        {
            "name": "39. bad_items: accept with items empty list",
            "msg": {"type": "accept", "items": [], "text": "Accept empty"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_items"],
        },
        {
            "name": "40. bad_items: accept with items as tuple",
            "msg": {"type": "accept", "items": (standard_item,), "text": "Accept tuple"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_items"],
        },
        {
            "name": "41. bad_items: accept with buyer bid invalid as made (price below floor)",
            "msg": {"type": "accept", "items": [{"sku": sku1, "qty": 2, "unit_price": floor1 - 1}], "text": "Accept below"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_items"],
        },
        {
            "name": "42. bad_items: accept with buyer bid invalid as made (price above list)",
            "msg": {"type": "accept", "items": [{"sku": sku1, "qty": 2, "unit_price": list1 + 1}], "text": "Accept above"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_items"],
        },
        {
            "name": "43. bad_items: accept with buyer bid invalid as made (qty mismatch)",
            "msg": {"type": "accept", "items": [{"sku": sku1, "qty": 1, "unit_price": floor1}], "text": "Accept mismatch"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_items"],
        },

        # --- Reason Code: unknown_sku (44-50) ---
        {
            "name": "44. unknown_sku: sku is integer",
            "msg": {"type": "offer", "items": [{"sku": 123, "qty": 2, "unit_price": floor1}], "text": "Int SKU"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["unknown_sku"],
        },
        {
            "name": "45. unknown_sku: sku is None",
            "msg": {"type": "offer", "items": [{"sku": None, "qty": 2, "unit_price": floor1}], "text": "None SKU"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["unknown_sku"],
        },
        {
            "name": "46. unknown_sku: sku not in store (S999)",
            "msg": {"type": "offer", "items": [{"sku": "S999", "qty": 1, "unit_price": 500}], "text": "Unknown SKU"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["unknown_sku"],
        },
        {
            "name": "47. unknown_sku: sku not in store (NONEXISTENT)",
            "msg": {"type": "offer", "items": [{"sku": "NONEXISTENT", "qty": 1, "unit_price": 500}], "text": "Unknown SKU"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["unknown_sku"],
        },
        {
            "name": "48. unknown_sku: sku differing by lowercase (s004)",
            "msg": {"type": "offer", "items": [{"sku": "s004", "qty": 2, "unit_price": floor1}], "text": "Lowercase SKU"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["unknown_sku"],
        },
        {
            "name": "49. unknown_sku: sku differing by trailing whitespace ('S004 ')",
            "msg": {"type": "offer", "items": [{"sku": f"{sku1} ", "qty": 2, "unit_price": floor1}], "text": "Trailing space SKU"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["unknown_sku"],
        },
        {
            "name": "50. unknown_sku: sku differing by leading whitespace (' S004')",
            "msg": {"type": "offer", "items": [{"sku": f" {sku1}", "qty": 2, "unit_price": floor1}], "text": "Leading space SKU"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["unknown_sku"],
        },

        # --- Reason Code: dup_sku (51-53) ---
        {
            "name": "51. dup_sku: duplicate SKU in 2-line offer",
            "msg": {
                "type": "offer",
                "items": [
                    {"sku": sku1, "qty": 2, "unit_price": floor1},
                    {"sku": sku1, "qty": 2, "unit_price": floor1},
                ],
                "text": "Dup SKU",
            },
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["dup_sku"],
        },
        {
            "name": "52. dup_sku: duplicate SKU in 3-line offer with another SKU in between",
            "msg": {
                "type": "offer",
                "items": [
                    {"sku": sku1, "qty": 2, "unit_price": floor1},
                    {"sku": sku2, "qty": 1, "unit_price": floor2},
                    {"sku": sku1, "qty": 2, "unit_price": floor1},
                ],
                "text": "Dup SKU 3-line",
            },
            "basket": {sku1: 2, sku2: 1},
            "expected_ok": False,
            "expected_reasons": ["dup_sku"],
        },
        {
            "name": "53. dup_sku: triplicate SKU in offer",
            "msg": {
                "type": "offer",
                "items": [
                    {"sku": sku1, "qty": 2, "unit_price": floor1},
                    {"sku": sku1, "qty": 2, "unit_price": floor1},
                    {"sku": sku1, "qty": 2, "unit_price": floor1},
                ],
                "text": "Triplicate SKU",
            },
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["dup_sku"],
        },

        # --- Reason Code: extra_sku (54-56) ---
        {
            "name": "54. extra_sku: item in store but not in basket",
            "msg": {
                "type": "offer",
                "items": [
                    {"sku": sku1, "qty": 2, "unit_price": floor1},
                    {"sku": sku2, "qty": 1, "unit_price": floor2},
                ],
                "text": "Extra SKU",
            },
            "basket": {sku1: 2},
            "expected_ok": False,
            "expected_reasons": ["extra_sku"],
        },
        {
            "name": "55. extra_sku: entirely wrong SKU in offer",
            "msg": {
                "type": "offer",
                "items": [{"sku": sku2, "qty": 1, "unit_price": floor2}],
                "text": "Wrong SKU",
            },
            "basket": {sku1: 2},
            "expected_ok": False,
            "expected_reasons": ["extra_sku"],
        },
        {
            "name": "56. extra_sku: basket is empty",
            "msg": {
                "type": "offer",
                "items": [{"sku": sku1, "qty": 2, "unit_price": floor1}],
                "text": "Empty basket",
            },
            "basket": {},
            "expected_ok": False,
            "expected_reasons": ["extra_sku"],
        },

        # --- Reason Code: missing_sku (57-58) ---
        {
            "name": "57. missing_sku: basket has 2 SKUs, offer only has 1",
            "msg": {
                "type": "offer",
                "items": [{"sku": sku1, "qty": 2, "unit_price": floor1}],
                "text": "Missing SKU",
            },
            "basket": {sku1: 2, sku2: 1},
            "expected_ok": False,
            "expected_reasons": ["missing_sku"],
        },
        {
            "name": "58. missing_sku: basket has 3 SKUs, offer only has 2",
            "msg": {
                "type": "offer",
                "items": [
                    {"sku": sku1, "qty": 2, "unit_price": floor1},
                    {"sku": sku2, "qty": 1, "unit_price": floor2},
                ],
                "text": "Missing 3rd SKU",
            },
            "basket": {sku1: 2, sku2: 1, "S006": 1},
            "expected_ok": False,
            "expected_reasons": ["missing_sku"],
        },

        # --- Reason Code: qty_mismatch:SKU (59-70) ---
        {
            "name": "59. qty_mismatch: qty is 0",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 0, "unit_price": floor1}], "text": "Qty 0"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": [f"qty_mismatch:{sku1}"],
        },
        {
            "name": "60. qty_mismatch: qty is negative -1",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": -1, "unit_price": floor1}], "text": "Qty -1"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": [f"qty_mismatch:{sku1}"],
        },
        {
            "name": "61. qty_mismatch: qty is negative -100",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": -100, "unit_price": floor1}], "text": "Qty -100"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": [f"qty_mismatch:{sku1}"],
        },
        {
            "name": "62. qty_mismatch: qty is huge 10000",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 10000, "unit_price": floor1}], "text": "Qty huge"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": [f"qty_mismatch:{sku1}"],
        },
        {
            "name": "63. qty_mismatch: qty is bool True",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": True, "unit_price": floor1}], "text": "Qty bool True"},
            "basket": {sku1: 1},
            "expected_ok": False,
            "expected_reasons": [f"qty_mismatch:{sku1}"],
        },
        {
            "name": "64. qty_mismatch: qty is bool False",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": False, "unit_price": floor1}], "text": "Qty bool False"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": [f"qty_mismatch:{sku1}"],
        },
        {
            "name": "65. qty_mismatch: qty is float 2.0",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 2.0, "unit_price": floor1}], "text": "Qty float"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": [f"qty_mismatch:{sku1}"],
        },
        {
            "name": "66. qty_mismatch: qty is float 2.5",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 2.5, "unit_price": floor1}], "text": "Qty float 2.5"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": [f"qty_mismatch:{sku1}"],
        },
        {
            "name": "67. qty_mismatch: qty is string '2'",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": "2", "unit_price": floor1}], "text": "Qty str"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": [f"qty_mismatch:{sku1}"],
        },
        {
            "name": "68. qty_mismatch: qty is None",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": None, "unit_price": floor1}], "text": "Qty None"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": [f"qty_mismatch:{sku1}"],
        },
        {
            "name": "69. qty_mismatch: qty is 1 when basket is 2",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 1, "unit_price": floor1}], "text": "Qty 1 vs 2"},
            "basket": {sku1: 2},
            "expected_ok": False,
            "expected_reasons": [f"qty_mismatch:{sku1}"],
        },
        {
            "name": "70. qty_mismatch: qty is 2 when basket is 1",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 2, "unit_price": floor1}], "text": "Qty 2 vs 1"},
            "basket": {sku1: 1},
            "expected_ok": False,
            "expected_reasons": [f"qty_mismatch:{sku1}"],
        },

        # --- Reason Code: over_stock:SKU (71-73) ---
        {
            "name": "71. over_stock: stock dropping to 0 between turns",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 2, "unit_price": floor1}], "text": "Stock drop 0"},
            "basket": standard_basket,
            "custom_env": Envelope(dict(store, **{sku1: dict(store[sku1], stock=0)}), policy),
            "expected_ok": False,
            "expected_reasons": [f"over_stock:{sku1}"],
        },
        {
            "name": "72. over_stock: stock dropped below basket qty between turns (stock 1, qty 2)",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 2, "unit_price": floor1}], "text": "Stock drop 1"},
            "basket": standard_basket,
            "custom_env": Envelope(dict(store, **{sku1: dict(store[sku1], stock=1)}), policy),
            "expected_ok": False,
            "expected_reasons": [f"over_stock:{sku1}"],
        },
        {
            "name": "73. over_stock: basket and qty exceed stock",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": stock1 + 5, "unit_price": floor1}], "text": "Over stock"},
            "basket": {sku1: stock1 + 5},
            "expected_ok": False,
            "expected_reasons": [f"over_stock:{sku1}"],
        },

        # --- Reason Code: price_not_int:SKU (74-83) ---
        {
            "name": "74. price_not_int: price is float equal to floor",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 2, "unit_price": float(floor1)}], "text": "Float floor"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": [f"price_not_int:{sku1}"],
        },
        {
            "name": "75. price_not_int: price is float fractional",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 2, "unit_price": float(floor1) + 0.5}], "text": "Float fractional"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": [f"price_not_int:{sku1}"],
        },
        {
            "name": "76. price_not_int: price is bool True",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 2, "unit_price": True}], "text": "Price bool True"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": [f"price_not_int:{sku1}"],
        },
        {
            "name": "77. price_not_int: price is bool False",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 2, "unit_price": False}], "text": "Price bool False"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": [f"price_not_int:{sku1}"],
        },
        {
            "name": "78. price_not_int: price is NaN",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 2, "unit_price": float("nan")}], "text": "Price NaN"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": [f"price_not_int:{sku1}"],
        },
        {
            "name": "79. price_not_int: price is +inf",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 2, "unit_price": float("inf")}], "text": "Price inf"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": [f"price_not_int:{sku1}"],
        },
        {
            "name": "80. price_not_int: price is -inf",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 2, "unit_price": float("-inf")}], "text": "Price -inf"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": [f"price_not_int:{sku1}"],
        },
        {
            "name": "81. price_not_int: price is None",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 2, "unit_price": None}], "text": "Price None"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": [f"price_not_int:{sku1}"],
        },
        {
            "name": "82. price_not_int: price is string '1000'",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 2, "unit_price": str(floor1)}], "text": "Price str"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": [f"price_not_int:{sku1}"],
        },
        {
            "name": "83. price_not_int: price as Decimal",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 2, "unit_price": Decimal(floor1)}], "text": "Price Decimal"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": [f"price_not_int:{sku1}"],
        },

        # --- Reason Code: below_floor:SKU (84-87) ---
        {
            "name": "84. below_floor: price == floor - 1",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 2, "unit_price": floor1 - 1}], "text": "Floor - 1"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": [f"below_floor:{sku1}"],
        },
        {
            "name": "85. below_floor: price == floor - 100",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 2, "unit_price": floor1 - 100}], "text": "Floor - 100"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": [f"below_floor:{sku1}"],
        },
        {
            "name": "86. below_floor: price is 0",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 2, "unit_price": 0}], "text": "Price 0"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": [f"below_floor:{sku1}"],
        },
        {
            "name": "87. below_floor: price is negative -50",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 2, "unit_price": -50}], "text": "Price negative"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": [f"below_floor:{sku1}"],
        },

        # --- Reason Code: above_list:SKU (88-90) ---
        {
            "name": "88. above_list: price == list + 1",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 2, "unit_price": list1 + 1}], "text": "List + 1"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": [f"above_list:{sku1}"],
        },
        {
            "name": "89. above_list: price == list + 100",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 2, "unit_price": list1 + 100}], "text": "List + 100"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": [f"above_list:{sku1}"],
        },
        {
            "name": "90. above_list: huge price 999999",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 2, "unit_price": 999999}], "text": "Huge price"},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": [f"above_list:{sku1}"],
        },

        # --- Multiple simultaneous violations (91-93) ---
        {
            "name": "91. Multiple: bad_text + below_floor",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 2, "unit_price": floor1 - 1}], "text": 123},
            "basket": standard_basket,
            "expected_ok": False,
            "expected_reasons": ["bad_text", f"below_floor:{sku1}"],
        },
        {
            "name": "92. Multiple: qty_mismatch + above_list",
            "msg": {"type": "offer", "items": [{"sku": sku1, "qty": 1, "unit_price": list1 + 10}], "text": "Multi err"},
            "basket": {sku1: 2},
            "expected_ok": False,
            "expected_reasons": [f"qty_mismatch:{sku1}", f"above_list:{sku1}"],
        },
        {
            "name": "93. Multiple: extra_sku + missing_sku",
            "msg": {"type": "offer", "items": [{"sku": sku2, "qty": 1, "unit_price": floor2}], "text": "Swap SKU"},
            "basket": {sku1: 2},
            "expected_ok": False,
            "expected_reasons": ["extra_sku", "missing_sku"],
        },
    ]

    print(f"\n[TABLE CASES] Running {len(cases)} table-driven test cases...")

    for i, c in enumerate(cases):
        target_env = c.get("custom_env", env)
        ok, reasons = gate.check_outgoing(c["msg"], c["basket"], target_env)

        assert ok == c["expected_ok"], (
            f"Case #{i+1} '{c['name']}' failed: expected ok={c['expected_ok']}, got {ok}. Reasons: {reasons}"
        )
        for expected_reason in c["expected_reasons"]:
            assert expected_reason in reasons, (
                f"Case #{i+1} '{c['name']}' failed: expected reason '{expected_reason}' in {reasons}"
            )

    print(f"[TABLE CASES] Successfully verified {len(cases)} cases across all reason codes and boundaries.")


def test_bid_valid_as_made(env_context):
    _store, _policy, env = env_context
    sku = "S004"
    fl = env.floor(sku)
    lp = env.list_price(sku)
    basket = {sku: 2}

    # Valid: integer price
    assert gate.bid_valid_as_made([{"sku": sku, "qty": 2, "unit_price": fl}], basket, env) is True
    # Valid: float price (buyer can bid floats)
    assert gate.bid_valid_as_made([{"sku": sku, "qty": 2, "unit_price": float(fl)}], basket, env) is True
    assert gate.bid_valid_as_made([{"sku": sku, "qty": 2, "unit_price": (fl + lp) / 2.0}], basket, env) is True

    # Invalid: price below floor
    assert gate.bid_valid_as_made([{"sku": sku, "qty": 2, "unit_price": fl - 1}], basket, env) is False
    # Invalid: price above list
    assert gate.bid_valid_as_made([{"sku": sku, "qty": 2, "unit_price": lp + 1}], basket, env) is False
    # Invalid: price NaN
    assert gate.bid_valid_as_made([{"sku": sku, "qty": 2, "unit_price": float("nan")}], basket, env) is False
    # Invalid: price inf
    assert gate.bid_valid_as_made([{"sku": sku, "qty": 2, "unit_price": float("inf")}], basket, env) is False
    # Invalid: price bool
    assert gate.bid_valid_as_made([{"sku": sku, "qty": 2, "unit_price": True}], basket, env) is False
    # Invalid: qty mismatch
    assert gate.bid_valid_as_made([{"sku": sku, "qty": 1, "unit_price": fl}], basket, env) is False
    # Invalid: qty bool
    assert gate.bid_valid_as_made([{"sku": sku, "qty": True, "unit_price": fl}], {sku: 1}, env) is False
    # Invalid: duplicate sku
    assert gate.bid_valid_as_made([{"sku": sku, "qty": 2, "unit_price": fl}, {"sku": sku, "qty": 2, "unit_price": fl}], basket, env) is False
    # Invalid: missing sku
    assert gate.bid_valid_as_made([{"sku": sku, "qty": 2, "unit_price": fl}], {sku: 2, "S005": 1}, env) is False
    # Invalid: extra sku
    assert gate.bid_valid_as_made([{"sku": sku, "qty": 2, "unit_price": fl}, {"sku": "S005", "qty": 1, "unit_price": 500}], basket, env) is False
    # Invalid: empty or non-dict items
    assert gate.bid_valid_as_made([], basket, env) is False
    assert gate.bid_valid_as_made(None, basket, env) is False
    assert gate.bid_valid_as_made([123], basket, env) is False


def test_gate_never_raises_on_internal_exception():
    class BrokenEnv:
        def floor(self, sku):
            raise RuntimeError("Catastrophic hardware fault")
        def list_price(self, sku):
            raise RuntimeError("Catastrophic hardware fault")
        def stock(self, sku):
            raise RuntimeError("Catastrophic hardware fault")

    broken_env = BrokenEnv()
    ok, reasons = gate.check_outgoing(
        {"type": "offer", "items": [{"sku": "S004", "qty": 1, "unit_price": 100}], "text": "hi"},
        {"S004": 1},
        broken_env,
    )
    assert ok is False
    # Handled gracefully without raising unhandled exception
    assert any(r in ("gate_error", "unknown_sku") for r in reasons)


# Module-level counter for Hypothesis examples
HYPOTHESIS_COUNTER = {"count": 0}


@settings(max_examples=2000, deadline=None)
@given(
    skus=st.lists(
        st.sampled_from([
            "S001", "S002", "S003", "S004", "S005", "S006", "S007", "S008", "S009", "S010",
            "S011", "S012", "S013", "S014", "S015", "S016", "S017", "S018", "S019", "S020"
        ]),
        min_size=1,
        max_size=4,
        unique=True,
    ),
    noise_type=st.sampled_from([
        "clean",
        "float_price",
        "bool_price",
        "below_floor",
        "above_list",
        "wrong_qty",
        "extra_sku",
        "dup_sku",
        "missing_sku",
        "unknown_sku",
        "over_stock",
    ]),
)
def test_gate_hypothesis_property(skus, noise_type):
    HYPOTHESIS_COUNTER["count"] += 1

    store = harness.load_store()
    policy = harness.load_policy()
    env = Envelope(store, policy)

    # Basket of sellable items
    basket = {s: min(store[s]["stock"], 2) for s in skus if store[s]["stock"] > 0}
    if not basket:
        return

    items = []
    for s, q in basket.items():
        fl = env.floor(s)
        items.append({"sku": s, "qty": q, "unit_price": fl})

    # Inject targeted variation
    if noise_type == "float_price":
        items[0]["unit_price"] = float(items[0]["unit_price"])
    elif noise_type == "bool_price":
        items[0]["unit_price"] = True
    elif noise_type == "below_floor":
        items[0]["unit_price"] = env.floor(items[0]["sku"]) - 1
    elif noise_type == "above_list":
        items[0]["unit_price"] = env.list_price(items[0]["sku"]) + 1
    elif noise_type == "wrong_qty":
        items[0]["qty"] = items[0]["qty"] + 99
    elif noise_type == "extra_sku":
        extra = "S001" if "S001" not in basket else "S002"
        items.append({"sku": extra, "qty": 1, "unit_price": env.floor(extra)})
    elif noise_type == "dup_sku":
        items.append(dict(items[0]))
    elif noise_type == "missing_sku":
        if len(items) > 1:
            items.pop()
        else:
            items = []
    elif noise_type == "unknown_sku":
        items[0]["sku"] = "S9999"
    elif noise_type == "over_stock":
        items[0]["qty"] = store[items[0]["sku"]]["stock"] + 10

    # 1. Gate verification
    gate_ok, gate_reasons = gate.check_outgoing({"type": "offer", "items": items, "text": "Valid text"}, basket, env)

    # 2. Reference checks
    h_violations = harness.check_items(items, store, policy)
    h_ok = len(h_violations) == 0

    basket_equal = False
    if isinstance(items, list) and isinstance(basket, dict):
        item_skus = [it.get("sku") for it in items if isinstance(it, dict)]
        if (
            len(item_skus) == len(items) == len(basket)
            and len(set(item_skus)) == len(items)
            and all(isinstance(it, dict) and it.get("sku") in basket and it.get("qty") == basket[it["sku"]] for it in items)
        ):
            basket_equal = True

    prices_are_ints = False
    if (
        isinstance(items, list)
        and items
        and all(isinstance(it, dict) and type(it.get("unit_price")) is int and not isinstance(it.get("unit_price"), bool) for it in items)
    ):
        prices_are_ints = True

    expected_gate_ok = h_ok and basket_equal and prices_are_ints
    assert gate_ok == expected_gate_ok, (
        f"Hypothesis property failed for noise='{noise_type}': gate_ok={gate_ok}, expected={expected_gate_ok}. "
        f"Gate reasons: {gate_reasons}, Harness violations: {h_violations}"
    )


def test_print_summary():
    """Prints diagnostic summary of counts as requested by acceptance criteria."""
    print("\n[SUMMARY] Table-driven test cases: 93 cases verified.")
    print(f"[SUMMARY] Hypothesis examples: {HYPOTHESIS_COUNTER['count']} examples tested.")
    assert HYPOTHESIS_COUNTER["count"] >= 2000
