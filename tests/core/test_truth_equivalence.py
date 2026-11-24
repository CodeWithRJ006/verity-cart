"""Equivalence test: asserts truth.check and harness.check_text produce identical flags."""
from pathlib import Path
import random
import string
import sys
import pytest

# Ensure kit is importable for harness verification
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "kit"))

import harness
from verity import truth


def test_truth_equivalence_50000_strings():
    rng = random.Random(1337)
    store = harness.load_store()
    policy = harness.load_policy()

    sample_skus = list(store.keys())[:10]

    # Pre-crafted phrases covering all regex patterns in harness
    phrases = [
        "today only", "offer expires", "offer ends", "last chance", "act now", "act fast",
        "hurry", "limited time", "before it's gone", "other buyers are interested",
        "someone else wants it", "price will rise", "only valid until tomorrow",
        "selling fast", "going fast", "high demand", "flying off the shelves",
        "limited stock", "running low", "running out", "almost gone", "few left", "low on stock",
        "last one", "last piece", "last item",
        "sold out", "out of stock", "none left", "no stock",
        "only 2 left", "just 1 remaining", "3 units remaining", "we have 5 in stock",
        "we got 10 units available", "we've got 4 pieces",
        "service charge", "handling charge", "convenience charge", "processing charge",
        "packaging charge", "delivery charge", "shipping charge", "plus gst", "taxes extra",
        "no delivery charge", "free of shipping charge", "without fee",
    ]

    iterations = 50000
    mismatches = []

    for i in range(iterations):
        # Generate varied contexts
        ctx_skus = set(rng.sample(sample_skus, k=rng.randint(1, 4)))
        ctx_amounts = {rng.randint(50, 5000) for _ in range(rng.randint(1, 6))}
        ctx_percents = {round(rng.uniform(5, 50), 1) for _ in range(rng.randint(1, 4))}
        wanted = {sku: rng.randint(1, 5) for sku in ctx_skus}

        ctx = {
            "store": store,
            "skus": ctx_skus,
            "amounts": ctx_amounts,
            "percents": ctx_percents,
            "wanted": wanted,
        }

        # Build varied text payloads
        roll = rng.randint(0, 6)
        if roll == 0:
            # Pure price / number variation
            n = rng.choice(list(ctx_amounts) + [rng.randint(50, 10000)])
            text = f"I can offer this for ₹{n:,}."
        elif roll == 1:
            # Percentage variation
            p = rng.choice(list(ctx_percents) + [round(rng.uniform(1, 60), 1)])
            text = f"We provide a discount of {p}%."
        elif roll == 2:
            # Regex phrase injected
            phrase = rng.choice(phrases)
            prefix = "Please note: " if rng.random() > 0.5 else "We don't have "
            text = f"{prefix}{phrase} for this deal."
        elif roll == 3:
            # Stock claim variation with random counts
            count = rng.choice(["one", "two", "three", "5", "10", "20", "50"])
            text = f"We have {count} units left in stock."
        elif roll == 4:
            # Fee claim with or without negation
            fee = rng.choice(["delivery charge", "shipping charge", "gst extra", "taxes extra"])
            if rng.random() > 0.5:
                text = f"Price is ₹1,000 without {fee}."
            else:
                text = f"Total is ₹1,000 plus {fee}."
        elif roll == 5:
            # Combination of random alphanumeric garbage and punctuation
            text = "".join(rng.choices(string.ascii_letters + string.digits + " ₹,.-%!", k=rng.randint(10, 80)))
        else:
            # Completely clean realistic sentence
            text = "Thank you for negotiating with us. We agree to this deal."

        harness_res = harness.check_text(text, ctx)
        truth_res = truth.check(text, ctx)

        h_kinds = [v["kind"] for v in harness_res]
        t_kinds = [v["kind"] for v in truth_res]

        if h_kinds != t_kinds:
            mismatches.append((text, h_kinds, t_kinds))
            if len(mismatches) >= 10:
                break

    print(f"\n[EQUIVALENCE] Evaluated {iterations} test strings against harness.check_text.")
    print(f"[EQUIVALENCE] Total mismatches: {len(mismatches)}")
    assert len(mismatches) == 0, f"Found {len(mismatches)} discrepancies! Sample: {mismatches[:3]}"
