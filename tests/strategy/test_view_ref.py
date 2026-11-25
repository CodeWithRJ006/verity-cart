"""Tests for experiments/view_ref.py.

Covers:
  1. All 26 contract fixture cases under "ignore" policy (expected: 26/26 pass).
  2. All 26 contract fixture cases under "matched" policy (reports which fail;
     partial-bid cases are EXPECTED to fail — this is by design, not a bug).
  3. Matched-mode vs legacy_spike.Seller.read_bid+priced comparison (>=40 cases).
  4. Source-text test: view_ref.py must not contain forbidden imports.

Store / policy copied verbatim from tests/contract/test_view_cases.py lines 18-27.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Shared fixtures — copied from tests/contract/test_view_cases.py:18-27
# ---------------------------------------------------------------------------
STORE = {
    "S001": {"sku": "S001", "name": "Item 1", "category": "apparel", "price": 1000, "cost": 600, "stock": 10},
    "S002": {"sku": "S002", "name": "Item 2", "category": "apparel", "price": 1200, "cost": 700, "stock": 5},
    "S003": {"sku": "S003", "name": "Item 3 (OOS)", "category": "apparel", "price": 800, "cost": 400, "stock": 0},
    "S004": {"sku": "S004", "name": "Item 4", "category": "apparel", "price": 500, "cost": 300, "stock": 20},
}
POLICY = {
    "max_discount": 0.25,
    "min_margin": {"apparel": 0.3},
}

FIXTURES_PATH = Path(__file__).resolve().parents[2] / "tests" / "contract" / "view_cases.json"
VIEW_REF_PATH = Path(__file__).resolve().parents[2] / "experiments" / "view_ref.py"

# Put kit on path so legacy_spike import works in this test file (not in view_ref.py).
KIT = Path(__file__).resolve().parents[2] / "kit"
if str(KIT) not in sys.path:
    sys.path.insert(0, str(KIT))

import verity.legacy_spike as _spike  # noqa: E402  (allowed in TEST file only)
from experiments.view_ref import ViewRef  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_fixture_cases(policy_name: str, accept_semantics: str = "gate"):
    """Run all 26 fixture cases under *policy_name* and *accept_semantics*.

    Returns (passing_ids, failing_ids, field_mismatches).
    field_mismatches: list of (case_id, field, expected, actual).
    """
    with open(FIXTURES_PATH, "r", encoding="utf-8") as f:
        cases = json.load(f)

    passing_ids = []
    failing_ids = []
    field_mismatches = []

    for case in cases:
        vr = ViewRef(STORE, POLICY, partial_bid_policy=policy_name, accept_semantics=accept_semantics)
        case_ok = True
        for turn in case["turns"]:
            view = vr.observe(turn["incoming"])
            expected = turn["expected_view"]
            for k, exp_val in expected.items():
                actual_val = getattr(view, k)
                if actual_val != exp_val:
                    field_mismatches.append((case["id"], k, exp_val, actual_val))
                    case_ok = False
            if "remember" in turn:
                vr.remember(turn["remember"])

        if case_ok:
            passing_ids.append(case["id"])
        else:
            failing_ids.append(case["id"])

    return passing_ids, failing_ids, field_mismatches


def _ratios_eq(a: Optional[float], b: Optional[float]) -> bool:
    """Float equality that handles NaN (NaN == NaN here) and Inf."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if isinstance(a, float) and isinstance(b, float):
        if math.isnan(a) and math.isnan(b):
            return True
        if math.isnan(a) or math.isnan(b):
            return False
    return a == b  # handles inf == inf correctly


# ---------------------------------------------------------------------------
# Test 1: All 26 fixture cases must pass under "ignore" policy
# ---------------------------------------------------------------------------

def test_fixture_ignore_policy():
    """All 26 contract fixture cases pass under partial_bid_policy='ignore'.

    The fixtures encode the 'ignore' policy (partial bids excluded from bids[]).
    Asserts exactly 26 cases ran and all pass.  Prints pass count.
    """
    passing, failing, mismatches = _run_fixture_cases("ignore")
    n_total = len(passing) + len(failing)
    print(f"\nignore policy: {len(passing)}/{n_total} cases passed")
    if failing:
        for case_id, field, exp, actual in mismatches:
            print(f"  FAIL {case_id}: field={field!r} expected={exp!r} got={actual!r}")
    assert n_total == 26, f"Expected 26 cases, got {n_total}"
    assert len(failing) == 0, (
        f"ignore policy failures (should be 0): {failing}\n"
        f"field mismatches: {mismatches}"
    )


# ---------------------------------------------------------------------------
# Test 2: "matched" policy — partial-bid cases EXPECTED to fail; report them
# ---------------------------------------------------------------------------

# Cases that differ between "ignore" and "matched":
#   case_03: OOS item in request → read_bid picks up S001 (basket match) → bids=[0.9];
#            fixture expects []  (fixture uses ignore)
#   case_04: qty=8 (basket capped to 5) → read_bid uses item qty=8 → adds ratio in t1;
#            fixture expects []  for t1
#   case_08: partial bid (S001 only) in t2 → read_bid adds ratio; fixture bids unchanged
#   case_09: extra SKU S002 in bid → read_bid picks S001; fixture bids unchanged
#   case_10: wrong qty=1 (basket=2) → read_bid uses item qty=1; fixture bids unchanged
#   case_11: duplicate S001 lines → read_bid sums both; fixture bids unchanged
#   case_15: negative price -500 → read_bid includes (no negative check); fixture unchanged
#   case_20: partial bid in t2 → read_bid adds ratio; fixture bids unchanged
#   case_24: S002 qty=1 (basket=2) → read_bid uses item qty=1; fixture unchanged
KNOWN_MATCHED_FAILURES = {
    "case_03_request_with_out_of_stock_sku",
    "case_04_request_qty_capped_at_stock",
    "case_08_partial_bid_missing_sku",
    "case_09_bid_with_extra_sku",
    "case_10_bid_with_wrong_quantity",
    "case_11_duplicate_sku_in_bid",
    "case_15_negative_price_in_bid",
    "case_20_partial_bid_between_two_complete_bids",
    "case_24_multi_sku_quantities_partial_match",
}


def test_fixture_matched_policy_report():
    """Under 'matched' policy, partial-bid cases fail.

    This test REPORTS the failures and verifies that the set of failing cases is
    exactly the known set above.  It does NOT assert zero failures — these are
    expected by design (the spike's read_bid accumulates partial-bid ratios).
    """
    passing, failing, mismatches = _run_fixture_cases("matched")
    n_total = len(passing) + len(failing)
    print(f"\nmatched policy: {len(passing)}/{n_total} cases passed")
    if failing:
        print("Cases failing under matched (expected, by design):")
        for fid in failing:
            # Find the first mismatch for this case to show the diff
            first = next((m for m in mismatches if m[0] == fid), None)
            if first:
                _, field, exp, actual = first
                print(f"  {fid}: field={field!r} expected={exp!r} got={actual!r}")

    # Assert the failing set is exactly what we expect (no surprise regressions)
    assert set(failing) == KNOWN_MATCHED_FAILURES, (
        f"Unexpected matched-policy failure diff:\n"
        f"  extra failures (not expected): {set(failing) - KNOWN_MATCHED_FAILURES}\n"
        f"  missing failures (newly passing): {KNOWN_MATCHED_FAILURES - set(failing)}"
    )


# ---------------------------------------------------------------------------
# Test 3: matched-mode vs legacy_spike.Seller.read_bid + priced (>=40 cases)
#
# Basket used: {S001: 2, S002: 1}
#   S001: price=1000, floor=ceil(max(600/0.7, 1000*0.75))=ceil(857.14)=858
#   S002: price=1200, floor=ceil(max(700/0.7, 1200*0.75))=ceil(1000.000...01)=1001
#   L = 2*1000 + 1*1200 = 3200
# ---------------------------------------------------------------------------

def _build_spike_seller_with_basket():
    """Build legacy_spike.Seller (legacy_spike.py:8-11) and set basket manually."""
    seller = _spike.Seller(STORE, POLICY)
    seller.start("matched_test")           # legacy_spike.py:19-23: initialises state
    seller.basket = {"S001": 2, "S002": 1}
    return seller


# 44 crafted item lists covering complete, partial, extra-sku, wrong-qty, duplicate,
# invalid prices (bool, None, str, inf, nan, negative, zero), invalid qtys
# (bool, float, zero, negative, large), non-list inputs, and edge structures.
_BASKET_REQUEST = {
    "type": "request",
    "round": 1,
    "items": [{"sku": "S001", "qty": 2}, {"sku": "S002", "qty": 1}],
}

MATCHED_CASES = [
    # --- complete bids ------------------------------------------------
    ([{"sku": "S001", "qty": 2, "unit_price": 1000}, {"sku": "S002", "qty": 1, "unit_price": 1200}],
     "complete at list price"),
    ([{"sku": "S001", "qty": 2, "unit_price": 900}, {"sku": "S002", "qty": 1, "unit_price": 1100}],
     "complete below list"),
    ([{"sku": "S001", "qty": 2, "unit_price": 858}, {"sku": "S002", "qty": 1, "unit_price": 1001}],
     "complete at floor"),
    ([{"sku": "S001", "qty": 2, "unit_price": 800}, {"sku": "S002", "qty": 1, "unit_price": 950}],
     "complete below floor"),
    ([{"sku": "S001", "qty": 2, "unit_price": 950.5}, {"sku": "S002", "qty": 1, "unit_price": 1100.0}],
     "complete with float prices"),

    # --- partial bids (missing a basket sku) --------------------------
    ([{"sku": "S001", "qty": 2, "unit_price": 900}], "partial S001 only"),
    ([{"sku": "S002", "qty": 1, "unit_price": 1100}], "partial S002 only"),

    # --- extra sku not in basket --------------------------------------
    ([{"sku": "S001", "qty": 2, "unit_price": 900}, {"sku": "S002", "qty": 1, "unit_price": 1100},
      {"sku": "S004", "qty": 1, "unit_price": 480}], "extra SKU S004"),
    ([{"sku": "S001", "qty": 2, "unit_price": 900}, {"sku": "X999", "qty": 1, "unit_price": 500}],
     "unknown SKU X999 mixed with S001"),
    ([{"sku": "X999", "qty": 1, "unit_price": 500}], "unknown SKU only"),

    # --- wrong quantity -----------------------------------------------
    ([{"sku": "S001", "qty": 1, "unit_price": 900}, {"sku": "S002", "qty": 1, "unit_price": 1100}],
     "S001 qty=1 (basket=2)"),
    ([{"sku": "S001", "qty": 3, "unit_price": 900}], "S001 qty=3 (basket=2), no S002"),

    # --- duplicate sku lines ------------------------------------------
    ([{"sku": "S001", "qty": 1, "unit_price": 900}, {"sku": "S001", "qty": 1, "unit_price": 950}],
     "duplicate S001 lines, no S002"),

    # --- bool prices (excluded by read_bid) ---------------------------
    ([{"sku": "S001", "qty": 2, "unit_price": True}, {"sku": "S002", "qty": 1, "unit_price": 1100}],
     "bool True price on S001"),
    ([{"sku": "S001", "qty": 2, "unit_price": False}, {"sku": "S002", "qty": 1, "unit_price": 1100}],
     "bool False price on S001"),

    # --- None price ---------------------------------------------------
    ([{"sku": "S001", "qty": 2, "unit_price": None}, {"sku": "S002", "qty": 1, "unit_price": 1100}],
     "None price on S001"),

    # --- string prices ------------------------------------------------
    ([{"sku": "S001", "qty": 2, "unit_price": "900"}, {"sku": "S002", "qty": 1, "unit_price": 1100}],
     "string price '900' on S001"),
    ([{"sku": "S001", "qty": 2, "unit_price": "Infinity"}, {"sku": "S002", "qty": 1, "unit_price": 1100}],
     "string 'Infinity' price"),

    # --- negative price (read_bid includes; bid_complete excludes) ----
    ([{"sku": "S001", "qty": 2, "unit_price": -500}, {"sku": "S002", "qty": 1, "unit_price": 1100}],
     "negative price -500 on S001"),
    ([{"sku": "S001", "qty": 2, "unit_price": 0}, {"sku": "S002", "qty": 1, "unit_price": 1100}],
     "zero price on S001 (read_bid includes, priced=True → adds)"),

    # --- NaN / Inf prices (read_bid includes these!) ------------------
    ([{"sku": "S001", "qty": 2, "unit_price": math.nan}, {"sku": "S002", "qty": 1, "unit_price": 1100}],
     "NaN price on S001"),
    ([{"sku": "S001", "qty": 2, "unit_price": math.inf}, {"sku": "S002", "qty": 1, "unit_price": 1100}],
     "+inf price on S001"),
    ([{"sku": "S001", "qty": 2, "unit_price": -math.inf}, {"sku": "S002", "qty": 1, "unit_price": 1100}],
     "-inf price on S001"),

    # --- invalid qty types (excluded by read_bid) ---------------------
    ([{"sku": "S001", "qty": True, "unit_price": 900}, {"sku": "S002", "qty": 1, "unit_price": 1100}],
     "bool True qty on S001"),
    ([{"sku": "S001", "qty": False, "unit_price": 900}, {"sku": "S002", "qty": 1, "unit_price": 1100}],
     "bool False qty on S001"),
    ([{"sku": "S001", "qty": 2.0, "unit_price": 900}, {"sku": "S002", "qty": 1, "unit_price": 1100}],
     "float qty 2.0 on S001"),
    ([{"sku": "S001", "qty": 0, "unit_price": 900}, {"sku": "S002", "qty": 1, "unit_price": 1100}],
     "zero qty on S001 (q < 1)"),
    ([{"sku": "S001", "qty": -1, "unit_price": 900}, {"sku": "S002", "qty": 1, "unit_price": 1100}],
     "negative qty -1 on S001"),

    # --- priced condition failures ------------------------------------
    ([{"sku": "S001", "qty": 2}, {"sku": "S002", "qty": 1}], "no unit_price on either"),
    ([{"sku": "S001", "qty": 2, "unit_price": 900}, {"sku": "S002", "qty": 1}],
     "S002 missing unit_price (priced=False)"),

    # --- non-list inputs ----------------------------------------------
    (None, "None instead of list"),
    ({"sku": "S001", "qty": 2, "unit_price": 900}, "dict instead of list"),
    ("S001", "string instead of list"),
    (42, "integer instead of list"),

    # --- empty and structurally-odd lists ----------------------------
    ([], "empty list"),
    ([1, 2, 3], "non-dict items"),
    ([None, {"sku": "S001", "qty": 2, "unit_price": 900}], "None as first item"),
    ([{"sku": "S001", "qty": 2, "unit_price": 900}, "not_a_dict"], "mix dict+string"),
    ([["sku", "S001"], {"sku": "S002", "qty": 1, "unit_price": 1100}], "list as first item"),

    # --- very large and boundary qty ---------------------------------
    ([{"sku": "S001", "qty": 1000, "unit_price": 900}], "very large qty on S001 only"),
    ([{"sku": "S001", "qty": 2, "unit_price": 900}, {"sku": "S001", "qty": 2, "unit_price": 950},
      {"sku": "S002", "qty": 1, "unit_price": 1100}], "three S001 lines incl. duplicate"),

    # --- price at / just above list ----------------------------------
    ([{"sku": "S001", "qty": 2, "unit_price": 1500}, {"sku": "S002", "qty": 1, "unit_price": 1100}],
     "above-list price on S001"),
    ([{"sku": "S001", "qty": 2, "unit_price": 900}, {"sku": "S002", "qty": 1, "unit_price": 0.001}],
     "tiny float price on S002"),
]


def test_matched_mode_vs_legacy_spike():
    """Compare ViewRef matched-mode bid decisions against legacy_spike.Seller.read_bid+priced.

    For each of the 44 crafted item lists, ViewRef and the spike must agree on:
      - whether a bid was added
      - the ratio value (if added), including NaN and Inf equality

    legacy_spike.Seller (legacy_spike.py:8-11) is built with the fixture dummy store/policy.
    Basket is set by calling start() then assigning self.basket directly (legacy_spike.py:19-23).
    The import of legacy_spike is ONLY in this test file, never in view_ref.py.

    Prints the count of compared cases and any mismatches.
    """
    seller = _build_spike_seller_with_basket()
    mismatches = []
    n_compared = 0

    for items, description in MATCHED_CASES:
        # Spike computation
        spike_ratio = seller.read_bid(items)             # legacy_spike.py:74
        spike_priced = (                                 # legacy_spike.py:165-169
            isinstance(items, list)
            and bool(items)
            and all(isinstance(i, dict) and "unit_price" in i for i in items)
        )
        spike_adds = spike_ratio is not None and spike_priced

        # ViewRef matched computation
        vr = ViewRef(STORE, POLICY, partial_bid_policy="matched")
        vr.observe(_BASKET_REQUEST)              # sets basket; unpriced → no bid added
        view = vr.observe({
            "type": "counter",
            "round": 2,
            "items": items,
        })
        view_adds = len(view.bids) > 0
        view_ratio = view.bids[0] if view_adds else None

        # Compare decisions
        adds_match = spike_adds == view_adds
        ratio_match = _ratios_eq(spike_ratio if spike_adds else None,
                                 view_ratio if view_adds else None)

        if not adds_match or not ratio_match:
            mismatches.append({
                "desc": description,
                "items": items,
                "spike_ratio": spike_ratio,
                "spike_adds": spike_adds,
                "view_ratio": view_ratio,
                "view_adds": view_adds,
            })

        n_compared += 1

    print(f"\nMatched-mode vs legacy_spike.read_bid comparison: {n_compared - len(mismatches)}/{n_compared} agree")
    if mismatches:
        print("MISMATCHES:")
        for m in mismatches:
            print(
                f"  [{m['desc']}]\n"
                f"    spike_ratio={m['spike_ratio']} spike_adds={m['spike_adds']}\n"
                f"    view_ratio={m['view_ratio']}  view_adds={m['view_adds']}"
            )

    assert len(mismatches) == 0, (
        f"{len(mismatches)} mismatches between ViewRef matched-mode and legacy_spike.read_bid"
    )
    assert n_compared >= 40, f"Expected >= 40 cases, ran {n_compared}"


# ---------------------------------------------------------------------------
# Test 4: source-text guard — view_ref.py must not contain forbidden imports
# ---------------------------------------------------------------------------

FORBIDDEN_IMPORT_TOKENS = [
    "verity.parser",
    "verity.envelope",
    "verity.state",
    "verity.gate",
    "verity.renderer",
    "verity.truth",
    "verity.seller",
    "verity.registry",
    "arena.",
]


def test_no_forbidden_imports_in_view_ref():
    """view_ref.py must not import any forbidden verity modules or arena/.

    Checks the source text for each forbidden token (import statement strings).
    """
    source = VIEW_REF_PATH.read_text(encoding="utf-8")
    found = [tok for tok in FORBIDDEN_IMPORT_TOKENS if tok in source]
    assert found == [], (
        f"view_ref.py contains forbidden import token(s): {found}"
    )


# ---------------------------------------------------------------------------
# Test 5: 26 fixture cases must still pass with explicit accept_semantics="gate"
# ---------------------------------------------------------------------------

def test_fixture_gate_semantics_explicit():
    """All 26 contract fixture cases pass with the new accept_semantics='gate' parameter.

    Verifies the new parameter doesn't regress existing behaviour when set explicitly.
    The fixtures were authored against gate semantics (bid_valid_as_made gated on
    bid_complete) so all 26 must pass here.
    """
    passing, failing, mismatches = _run_fixture_cases("ignore", accept_semantics="gate")
    n_total = len(passing) + len(failing)
    print(f"\ngate semantics (explicit): {len(passing)}/{n_total} cases passed")
    if failing:
        for case_id, field, exp, actual in mismatches:
            print(f"  FAIL {case_id}: field={field!r} expected={exp!r} got={actual!r}")
    assert n_total == 26
    assert len(failing) == 0, f"gate semantics regressions: {failing}"


# ---------------------------------------------------------------------------
# Test 6: spike mode computes bid_valid_as_made independently of bid_complete
# ---------------------------------------------------------------------------

def test_spike_mode_bid_complete_independent():
    """In spike mode bid_valid_as_made is NOT gated on bid_complete.

    Proof case A — extra SKU (bid has S001 + S004; basket is {S001: 1}):
      bid_complete=False: S004 is not in basket → Amendment A SKU-set mismatch.
      gate mode: gated on bid_complete → bid_valid_as_made=False.
      spike mode: priced=True (all items have unit_price); directly_acceptable=True
        (S001: q=1, 1<=1<=10, 858<=900<=1000; S004: q=1, 1<=1<=20, 429<=450<=500).
        Result: bid_valid_as_made=True, independent of bid_complete.

    Proof case B — wrong qty (bid has S001 qty=3; basket is {S001: 1}):
      bid_complete=False: qty 3 != basket["S001"]=1 → Amendment A qty mismatch.
      gate mode: bid_valid_as_made=False.
      spike mode: directly_acceptable checks 1<=3<=10 (stock), not vs basket qty
        (legacy_spike.py:107 checks 1<=q<=stock, not q==basket[sku]).
        858<=900<=1000 → True.  bid_valid_as_made=True.
    """
    basket_req = {"type": "request", "round": 1, "items": [{"sku": "S001", "qty": 1}]}

    # --- Case A: extra SKU S004 ---
    # S004 floor = ceil(max(300/0.7, 500*0.75)) = ceil(max(428.57, 375)) = 429
    extra_sku_counter = {
        "type": "counter",
        "round": 2,
        "items": [
            {"sku": "S001", "qty": 1, "unit_price": 900},
            {"sku": "S004", "qty": 1, "unit_price": 450},
        ],
    }

    vr_gate = ViewRef(STORE, POLICY, accept_semantics="gate")
    vr_gate.observe(basket_req)
    view_gate = vr_gate.observe(extra_sku_counter)
    assert view_gate.bid_complete is False, "Case A gate: S004 extra SKU → not complete"
    assert view_gate.bid_valid_as_made is False, "Case A gate: gated on bid_complete"

    vr_spike = ViewRef(STORE, POLICY, accept_semantics="spike")
    vr_spike.observe(basket_req)
    view_spike = vr_spike.observe(extra_sku_counter)
    assert view_spike.bid_complete is False, "Case A spike: S004 extra SKU → still not complete"
    assert view_spike.bid_valid_as_made is True, (
        "Case A spike: priced=True AND directly_acceptable=True (S004 valid per store), "
        "independent of bid_complete"
    )

    # --- Case B: wrong qty (3 vs basket 1) ---
    wrong_qty_counter = {
        "type": "counter",
        "round": 2,
        "items": [{"sku": "S001", "qty": 3, "unit_price": 900}],
    }

    vr_gate2 = ViewRef(STORE, POLICY, accept_semantics="gate")
    vr_gate2.observe(basket_req)
    view_gate2 = vr_gate2.observe(wrong_qty_counter)
    assert view_gate2.bid_complete is False, "Case B gate: qty 3 != basket 1 → not complete"
    assert view_gate2.bid_valid_as_made is False, "Case B gate: gated on bid_complete"

    vr_spike2 = ViewRef(STORE, POLICY, accept_semantics="spike")
    vr_spike2.observe(basket_req)
    view_spike2 = vr_spike2.observe(wrong_qty_counter)
    assert view_spike2.bid_complete is False, "Case B spike: qty 3 != basket 1 → still not complete"
    assert view_spike2.bid_valid_as_made is True, (
        "Case B spike: 1<=3<=10 passes directly_acceptable; priced=True; "
        "DA does not check qty==basket[sku] (legacy_spike.py:107)"
    )


# ---------------------------------------------------------------------------
# Test 7: spike semantics vs legacy_spike.Seller priced AND directly_acceptable
#
# Basket: {S001: 1}  (set via seller.start() + seller.basket=; ViewRef via observe)
# S001: price=1000, floor=ceil(max(600/0.7, 1000*0.75))=ceil(857.14...)=858, stock=10
# S002: price=1200, floor=ceil(max(700/0.7, 1200*0.75))=ceil(1000.000...01)=1001, stock=5
# S003: price=800,  OOS (stock=0)
# S004: price=500,  floor=ceil(max(300/0.7, 500*0.75))=ceil(428.57...)=429, stock=20
# ---------------------------------------------------------------------------

_SPIKE_DA_BASKET_REQ = {
    "type": "request",
    "round": 1,
    "items": [{"sku": "S001", "qty": 1}],
}

# (items, description) — expected result derived dynamically from both implementations.
# Basket for the spike seller (and ViewRef) is {S001: 1}.
SPIKE_DA_CASES = [
    # --- complete, in range (priced=T, DA=T) ---
    ([{"sku": "S001", "qty": 1, "unit_price": 900}], "S001 in range"),
    ([{"sku": "S001", "qty": 1, "unit_price": 1000}], "S001 at list"),
    ([{"sku": "S001", "qty": 1, "unit_price": 858}], "S001 at floor"),

    # --- extra SKU: DA has no basket-set check → passes per-item ---
    ([{"sku": "S001", "qty": 1, "unit_price": 900},
      {"sku": "S002", "qty": 1, "unit_price": 1100}], "extra S002, both in range"),
    ([{"sku": "S001", "qty": 1, "unit_price": 900},
      {"sku": "S004", "qty": 1, "unit_price": 450}], "extra S004, both in range"),
    # S004 alone: not in basket but valid per store
    ([{"sku": "S004", "qty": 1, "unit_price": 450}], "S004 alone, valid per store"),
    ([{"sku": "S002", "qty": 1, "unit_price": 1100}], "S002 alone, valid per store"),

    # --- wrong qty but 1<=q<=stock → DA=True (legacy_spike.py:107) ---
    ([{"sku": "S001", "qty": 2, "unit_price": 900}], "S001 qty=2 (basket=1), passes DA"),
    ([{"sku": "S001", "qty": 10, "unit_price": 900}], "S001 qty at stock=10, passes DA"),

    # --- duplicate SKU lines: DA has no dup-check; both pass per-item ---
    ([{"sku": "S001", "qty": 1, "unit_price": 900},
      {"sku": "S001", "qty": 1, "unit_price": 950}], "duplicate S001 lines, both in range"),

    # --- below floor (priced=T, DA=F) ---
    ([{"sku": "S001", "qty": 1, "unit_price": 800}], "S001 below floor (858)"),
    ([{"sku": "S001", "qty": 1, "unit_price": 857}], "S001 one below floor"),
    ([{"sku": "S001", "qty": 1, "unit_price": 0}], "S001 zero price"),

    # --- above list (priced=T, DA=F) ---
    ([{"sku": "S001", "qty": 1, "unit_price": 1001}], "S001 above list (1000)"),
    ([{"sku": "S001", "qty": 1, "unit_price": 2000}], "S001 well above list"),

    # --- qty above stock (priced=T, DA=F: not 1<=q<=stock) ---
    ([{"sku": "S001", "qty": 11, "unit_price": 900}], "S001 qty 11 > stock 10"),
    ([{"sku": "S001", "qty": 100, "unit_price": 900}], "S001 qty 100 >> stock 10"),
    ([{"sku": "S002", "qty": 6, "unit_price": 1100}], "S002 qty 6 > stock 5"),

    # --- S003 OOS (stock=0 → 1<=1<=0 fails) ---
    ([{"sku": "S003", "qty": 1, "unit_price": 700}], "S003 OOS (stock=0)"),

    # --- S002 below its floor of 1001 ---
    ([{"sku": "S001", "qty": 1, "unit_price": 900},
      {"sku": "S002", "qty": 1, "unit_price": 900}], "S002@900 below S002 floor 1001"),

    # --- bool prices (priced=T: key present; DA=F: isinstance(pr,bool)) ---
    ([{"sku": "S001", "qty": 1, "unit_price": True}], "bool True price"),
    ([{"sku": "S001", "qty": 1, "unit_price": False}], "bool False price"),

    # --- None price (priced=T: key present; DA=F: not isinstance(None,...)) ---
    ([{"sku": "S001", "qty": 1, "unit_price": None}], "None price"),

    # --- string prices (priced=T: key present; DA=F) ---
    ([{"sku": "S001", "qty": 1, "unit_price": "900"}], "string price '900'"),
    ([{"sku": "S001", "qty": 1, "unit_price": "Infinity"}], "string 'Infinity'"),

    # --- negative price (priced=T; DA=F: floor<=neg fails) ---
    ([{"sku": "S001", "qty": 1, "unit_price": -500}], "negative price -500"),

    # --- NaN / Inf prices: DA returns False (858<=NaN → False; NaN comp never raises) ---
    ([{"sku": "S001", "qty": 1, "unit_price": math.nan}], "NaN price"),
    ([{"sku": "S001", "qty": 1, "unit_price": math.inf}], "+inf price"),
    ([{"sku": "S001", "qty": 1, "unit_price": -math.inf}], "-inf price"),

    # --- bool qty (priced=T; DA=F: isinstance(q,bool)) ---
    ([{"sku": "S001", "qty": True, "unit_price": 900}], "bool True qty"),
    ([{"sku": "S001", "qty": False, "unit_price": 900}], "bool False qty"),

    # --- None / float / zero / negative qty ---
    ([{"sku": "S001", "qty": None, "unit_price": 900}], "None qty"),
    ([{"sku": "S001", "qty": 1.0, "unit_price": 900}], "float qty 1.0"),
    ([{"sku": "S001", "qty": 0, "unit_price": 900}], "zero qty"),
    ([{"sku": "S001", "qty": -1, "unit_price": 900}], "negative qty"),

    # --- unknown sku (priced=T; DA=F: row=None) ---
    ([{"sku": "X999", "qty": 1, "unit_price": 900}], "unknown sku X999"),

    # --- missing 'unit_price' key → priced=False → combined=False immediately ---
    ([{"sku": "S001", "qty": 1}], "missing unit_price key (priced=False)"),
    ([{"sku": "S001", "qty": 1, "unit_price": 900},
      {"sku": "S002", "qty": 1}], "S002 missing unit_price (priced=False)"),

    # --- non-list inputs → priced=False ---
    (None, "None input"),
    ({"sku": "S001", "qty": 1, "unit_price": 900}, "dict input"),
    ("string", "string input"),
    (42, "integer input"),

    # --- empty list → DA: not bool([]) → False ---
    ([], "empty list"),

    # --- non-dict items → priced=False ---
    ([1, 2, 3], "non-dict items"),
    ([None, {"sku": "S001", "qty": 1, "unit_price": 900}], "None as first item"),
    ([{"sku": "S001", "qty": 1, "unit_price": 900}, "not_a_dict"], "string as last item"),
]


def test_spike_semantics_vs_legacy_spike():
    """Compare ViewRef accept_semantics='spike' bid_valid_as_made against
    the spike's combined expression priced AND directly_acceptable(items).

    Basket is {S001: 1} in both implementations:
      - Spike seller: seller.start("test") (legacy_spike.py:19-23) then
        seller.basket = {"S001": 1} assigned directly (the basket field is a plain
        dict attr set by _respond at legacy_spike.py:150, so direct assignment is safe).
      - ViewRef: first observe() call with an unpriced request containing S001 qty=1
        forms the basket via _form_basket (legacy_spike.py:140-155 mirror).

    Spike computation (in that order, matching legacy_spike.py:165-170):
        priced = isinstance(items,list) and bool(items) and
                 all(isinstance(i,dict) and 'unit_price' in i for i in items)
        result = priced and seller.directly_acceptable(items)

    ViewRef computation:
        view.bid_valid_as_made  (from observe() with accept_semantics='spike')

    RAISE ANALYSIS: for all 44 cases in SPIKE_DA_CASES, the spike's
    directly_acceptable (legacy_spike.py:95-116) does NOT raise:
      - Non-list/empty inputs: guarded at line 96 (not isinstance or not bool).
      - Non-dict items: guarded at line 99.
      - Unknown sku: store.get() returns None; row is None guard at line 104 fires
        BEFORE self.floor() at line 113, so floor() is never called on unknown skus.
      - Invalid price types (None, bool, str): guarded at lines 111-112.
      - NaN / Inf prices: 858<=NaN evaluates to False in Python (IEEE 754); no raise.
      - Negative/zero prices: floor<=neg evaluates to False; no raise.
    The respond() wrapper at legacy_spike.py:130-134 therefore never fires for
    any of these cases.  ViewRef intentionally does not catch exceptions either;
    if future store/policy data could cause a raise, MiniSeller's respond wrapper
    will handle it, mirroring the spike exactly.

    Prints: count compared and any mismatches.
    """
    # Build spike seller with basket {S001: 1}
    seller = _spike.Seller(STORE, POLICY)   # legacy_spike.py:9-11
    seller.start("da_test")                  # legacy_spike.py:19-23
    seller.basket = {"S001": 1}             # direct assignment (plain dict attr)

    mismatches = []
    n_compared = 0
    n_spike_raised = 0
    n_view_raised = 0

    for items, description in SPIKE_DA_CASES:
        # Spike: priced AND directly_acceptable (legacy_spike.py:165-170)
        try:
            priced = (
                isinstance(items, list)
                and bool(items)
                and all(isinstance(i, dict) and "unit_price" in i for i in items)
            )
            spike_result = priced and seller.directly_acceptable(items)
            spike_raised = False
        except Exception as exc:  # noqa: BLE001
            spike_raised = True
            spike_result = None
            spike_exc_repr = repr(exc)
            n_spike_raised += 1

        # ViewRef spike mode
        try:
            vr = ViewRef(STORE, POLICY, accept_semantics="spike")
            vr.observe(_SPIKE_DA_BASKET_REQ)   # forms basket {S001:1}
            view = vr.observe({"type": "counter", "round": 2, "items": items})
            view_result = view.bid_valid_as_made
            view_raised = False
        except Exception as exc:  # noqa: BLE001
            view_raised = True
            view_result = None
            view_exc_repr = repr(exc)
            n_view_raised += 1

        # Comparison: raise must agree; value must agree when neither raises
        if spike_raised != view_raised:
            mismatches.append((
                description, items,
                f"RAISE MISMATCH: spike_raised={spike_raised} "
                f"({spike_exc_repr if spike_raised else 'no exc'}) "
                f"view_raised={view_raised} "
                f"({view_exc_repr if view_raised else 'no exc'})",
            ))
        elif not spike_raised and spike_result != view_result:
            mismatches.append((description, items, f"spike={spike_result} view={view_result}"))

        n_compared += 1

    agree = n_compared - len(mismatches)
    print(
        f"\nSpike semantics (priced AND directly_acceptable) vs ViewRef spike mode:"
        f" {agree}/{n_compared} agree"
        f" (spike raised: {n_spike_raised}, view raised: {n_view_raised})"
    )
    if mismatches:
        print("MISMATCHES:")
        for desc, itms, detail in mismatches:
            print(f"  [{desc}] items={itms!r}  {detail}")

    assert n_compared >= 40, f"Expected >= 40 cases, ran {n_compared}"
    assert len(mismatches) == 0, (
        f"{len(mismatches)} mismatches between ViewRef spike mode and legacy_spike:"
        f" {[(d, det) for d, _, det in mismatches]}"
    )
