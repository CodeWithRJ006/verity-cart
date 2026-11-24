"""Tests that all renderer templates produce 0 truth flags across 20,000 random offers."""
import random
import sys
from pathlib import Path

from verity import renderer, truth

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "kit"))

import harness  # noqa: E402


def test_renderer_clean_20000_offers():
    rng = random.Random(42)
    store = harness.load_store()
    policy = harness.load_policy()
    skus = list(store.keys())

    iterations = 20000
    templates = ["open", "counter", "accept", "walkaway_nostock", "walkaway_final", "plain_fallback"]
    flagged = []

    for i in range(iterations):
        # Pick 1-4 random SKUs for the basket
        basket_skus = rng.sample(skus, k=rng.randint(1, 4))
        items = []
        for sku in basket_skus:
            row = store[sku]
            qty = rng.randint(1, max(1, min(3, row["stock"])))
            price = rng.randint(row["cost"], row["price"])
            items.append({"sku": sku, "qty": qty, "unit_price": price})

        total = sum(it["qty"] * it["unit_price"] for it in items)
        dropped = [rng.choice(skus)] if rng.random() > 0.8 else []

        # Build context matching what harness Context creates
        ctx_obj = harness.Context(store, policy)
        kind = rng.choice(templates)

        if kind == "walkaway_nostock":
            # An out-of-stock walkaway happens when a requested SKU in ctx.skus has stock 0
            nostock_sku = rng.choice(skus)
            ctx_obj.add_items([{"sku": nostock_sku, "qty": 1}])
            ctx_obj.wanted[nostock_sku] = 1
            test_store = dict(store, **{nostock_sku: dict(store[nostock_sku], stock=0)})
            ctx = ctx_obj.as_dict()
            ctx["store"] = test_store
            text = renderer.render(kind, items=[], total=0, dropped=[nostock_sku], store=test_store)
        else:
            ctx_obj.add_items(items)
            ctx = ctx_obj.as_dict()
            text = renderer.render(kind, items=items, total=total, dropped=dropped, store=store)

        h_flags = harness.check_text(text, ctx)
        t_flags = truth.check(text, ctx)

        if h_flags or t_flags:
            flagged.append((kind, text, h_flags, t_flags))
            if len(flagged) >= 10:
                break

    print(f"\n[RENDERER] Verified {iterations} rendered messages across {templates}.")
    print(f"[RENDERER] Total flagged outputs: {len(flagged)}")
    assert len(flagged) == 0, f"Renderer produced truth flags: {flagged[:3]}"


def test_forbidden_phrases_audit():
    """Documents and asserts detection of every forbidden phrase the harness flags."""
    forbidden_catalog = {
        "pressure": [
            "today only", "offer expires", "offer ends", "last chance", "act now", "act fast",
            "hurry", "limited time", "before it's gone", "other buyers are", "someone else",
            "price will rise", "only valid until", "selling fast", "going fast", "high demand", "flying off"
        ],
        "scarcity": [
            "limited stock", "running low", "running out", "almost gone", "few left", "low stock"
        ],
        "stock": [
            "last one", "last piece", "last item", "only 1 left", "2 remaining", "we have 5 in stock"
        ],
        "hidden_fee": [
            "delivery charge", "shipping charge", "handling charge", "service charge",
            "convenience charge", "processing charge", "packaging charge", "gst extra",
            "plus gst", "plus tax", "taxes extra"
        ]
    }

    dummy_ctx = {"store": {}, "skus": set(), "amounts": set(), "percents": set(), "wanted": {}}
    for category, phrases in forbidden_catalog.items():
        for phrase in phrases:
            flags = [v["kind"] for v in truth.check(f"Special terms: {phrase}", dummy_ctx)]
            assert len(flags) > 0, f"Forbidden phrase '{phrase}' in category '{category}' was not flagged!"
