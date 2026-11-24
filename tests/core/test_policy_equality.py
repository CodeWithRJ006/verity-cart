"""Tests exact policy equality and boundary behavior against kit/harness.py."""
import copy
from pathlib import Path
import sys

# Ensure kit is importable for harness verification
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "kit"))

import harness
from verity.envelope import Envelope


def test_floor_policy_equality_all_100_skus():
    store = harness.load_store()
    policy = harness.load_policy()
    assert len(store) == 100, f"Expected 100 SKUs in store.csv, got {len(store)}"

    envelope = Envelope(store, policy)
    compared = 0

    for sku, row in store.items():
        expected_floor = harness.floor_price(row, policy)
        actual_floor = envelope.floor(sku)
        assert actual_floor == expected_floor, (
            f"Floor price mismatch for SKU {sku}: envelope={actual_floor}, harness={expected_floor}"
        )
        assert isinstance(actual_floor, int), f"Floor price for {sku} must be int, got {type(actual_floor)}"
        compared += 1

    print(f"\n[EQUALITY] Successfully verified exact floor equality for {compared}/100 SKUs.")
    assert compared == 100


def test_floor_boundary_conditions():
    store = harness.load_store()
    policy = harness.load_policy()
    envelope = Envelope(store, policy)

    compared = 0
    quantities = (1, 2, 5)

    for sku, row in store.items():
        fl = envelope.floor(sku)
        for q in quantities:
            # Provide sufficient stock to isolate price validation
            test_store = {sku: dict(row, stock=max(row["stock"], q))}

            # At floor: must be permitted by harness policy rules
            allow_items = [{"sku": sku, "qty": q, "unit_price": fl}]
            allow_violations = harness.check_items(allow_items, test_store, policy)
            # Filter for price-specific violations
            price_violations = [v for v in allow_violations if v["kind"] in ("policy:below_min_margin", "policy:over_max_discount")]
            assert not price_violations, (
                f"Floor price {fl} unexpectedly violated policy for SKU {sku} qty {q}: {price_violations}"
            )

            # At floor - 1: must be blocked by harness policy rules
            block_items = [{"sku": sku, "qty": q, "unit_price": fl - 1}]
            block_violations = harness.check_items(block_items, test_store, policy)
            assert any(v["kind"] in ("policy:below_min_margin", "policy:over_max_discount") for v in block_violations), (
                f"Floor-1 price {fl - 1} was not blocked for SKU {sku} qty {q}"
            )
            compared += 1

    print(f"\n[BOUNDARY] Successfully verified boundary conditions across {len(store)} SKUs x {len(quantities)} quantities ({compared} checks).")


def test_envelope_never_mutates_store_or_policy():
    store = harness.load_store()
    policy = harness.load_policy()

    store_copy = copy.deepcopy(store)
    policy_copy = copy.deepcopy(policy)

    envelope = Envelope(store, policy)

    for sku in store:
        _ = envelope.floor(sku)
        _ = envelope.list_price(sku)
        _ = envelope.stock(sku)

    assert store == store_copy, "Envelope initialization or queries mutated the store dictionary!"
    assert policy == policy_copy, "Envelope initialization or queries mutated the policy dictionary!"
