"""Differential test: MiniSeller vs legacy_spike.Seller through the kit harness.

For seeds [0, 1, 2, 3, 7, 8, 9] x the 3 public buyers, both sellers play an
identical fresh scenario, built exactly as kit/evaluate.py builds them
(kit/evaluate.py:134 make_scenarios, kit/evaluate.py:73 buyer construction), and
driven by kit/harness.run_negotiation (kit/harness.py:206).

Seller messages must agree per round on (type, sorted items) and the outcomes
must agree on ended, deal and violations.

The two recorders are pass-through wrappers around start()/respond() only: they
let a failing trace show the spike's last_o/bids next to the View MiniSeller saw,
without re-running the scenario.
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "kit"
if str(KIT) not in sys.path:
    sys.path.insert(0, str(KIT))

import buyers  # noqa: E402
from harness import load_policy, load_store, run_negotiation  # noqa: E402

from experiments.mini_seller import MiniSeller  # noqa: E402
from verity.legacy_spike import Seller as SpikeSeller  # noqa: E402

SEEDS = [0, 1, 2, 3, 7, 8, 9]
BUYER_NAMES = ["cooperative", "hard_bargainer", "manipulator"]


# ---------------------------------------------------------------------------
# Recording wrappers (test-only; kit/harness.py only calls start()/respond())
# ---------------------------------------------------------------------------

class _SpikeRecorder:
    """Pass-through that snapshots the spike's own state after every turn."""

    def __init__(self, seller):
        self.seller = seller
        self.turns = []

    def start(self, negotiation_id):
        self.seller.start(negotiation_id)

    def respond(self, msg):
        out = self.seller.respond(msg)
        self.turns.append({
            "round": msg.get("round"),
            "out": out,
            "last_o": getattr(self.seller, "last_o", None),
            "bids": list(getattr(self.seller, "bids", None) or []),
            "basket": getattr(self.seller, "basket", None),
        })
        return out


class _MiniRecorder:
    """Pass-through that captures MiniSeller's View and view_ref basket."""

    def __init__(self, seller):
        self.seller = seller
        self.turns = []

    def start(self, negotiation_id):
        self.seller.start(negotiation_id)

    def respond(self, msg):
        out = self.seller.respond(msg)
        view_ref = getattr(self.seller, "_view_ref", None)
        self.turns.append({
            "round": msg.get("round"),
            "out": out,
            "view": getattr(self.seller, "last_view", None),
            "basket": getattr(view_ref, "_basket", None),
        })
        return out


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------

def _canon(x) -> str:
    return json.dumps(x, sort_keys=True, default=repr)


def _item_key(items):
    """Order-insensitive, type-safe key for a message's items list."""
    if not isinstance(items, list):
        return None
    return tuple(sorted(_canon(it) for it in items))


def _sig(msg) -> tuple:
    """(type, sorted items) signature of a seller message."""
    return (msg.get("type"), _item_key(msg.get("items")))


def _first_divergence(seed, sc, res_spike, res_mini, spike, mini):
    """Return a printable trace of the first divergence, or None if identical."""
    label = f"seed={seed} buyer={sc['buyer']} scenario={sc['id']}"
    n_turns = max(len(spike.turns), len(mini.turns))
    for k in range(n_turns):
        st = spike.turns[k] if k < len(spike.turns) else None
        mt = mini.turns[k] if k < len(mini.turns) else None
        s_sig = _sig(st["out"]) if st is not None else None
        m_sig = _sig(mt["out"]) if mt is not None else None
        if s_sig != m_sig:
            lines = [f"MISMATCH {label} at seller turn {k + 1}"]
            if st is not None:
                lines.append(
                    f"  spike last_o={st['last_o']!r} bids={st['bids']!r} "
                    f"basket={st['basket']!r}"
                )
                lines.append(f"  spike out={st['out']!r}")
            else:
                lines.append("  spike: no turn at this index")
            if mt is not None:
                lines.append(f"  mini  view={mt['view']!r}")
                lines.append(f"  mini  basket={mt['basket']!r}")
                lines.append(f"  mini  out={mt['out']!r}")
            else:
                lines.append("  mini: no turn at this index")
            return "\n".join(lines)

    outcomes_differ = (
        res_spike["ended"] != res_mini["ended"]
        or _canon(res_spike["deal"]) != _canon(res_mini["deal"])
        or _canon(res_spike["violations"]) != _canon(res_mini["violations"])
    )
    if outcomes_differ:
        lines = [f"MISMATCH {label} outcome"]
        lines.append(
            f"  spike ended={res_spike['ended']!r} deal={res_spike['deal']!r} "
            f"violations={res_spike['violations']!r}"
        )
        lines.append(
            f"  mini  ended={res_mini['ended']!r} deal={res_mini['deal']!r} "
            f"violations={res_mini['violations']!r}"
        )
        if mini.turns:
            lines.append(f"  mini  last view={mini.turns[-1]['view']!r}")
            lines.append(f"  mini  last spike-free basket={mini.turns[-1]['basket']!r}")
        return "\n".join(lines)
    return None


def _play(store, policy, sc, echo_alloc="at_most"):
    """Play one scenario twice: spike vs MiniSeller, fresh buyers with equal RNG."""
    buyer_cls = buyers.BUYERS[sc["buyer"]]
    buyer_spike = buyer_cls(sc, store, random.Random(sc["seed"]))
    buyer_mini = buyer_cls(sc, store, random.Random(sc["seed"]))
    spike = _SpikeRecorder(SpikeSeller(store, policy))
    mini = _MiniRecorder(MiniSeller(store, policy, echo_alloc=echo_alloc))
    res_spike = run_negotiation(spike, buyer_spike, store, policy, sc["id"])
    res_mini = run_negotiation(mini, buyer_mini, store, policy, sc["id"])
    return res_spike, res_mini, spike, mini


# ---------------------------------------------------------------------------
# Test 1: the differential itself — zero mismatches over 21 scenarios
# ---------------------------------------------------------------------------

def test_mini_seller_matches_legacy_spike():
    """Seller messages and outcomes are identical to the spike over 7 seeds x 3 buyers."""
    store, policy = load_store(), load_policy()
    seed_counts = {seed: 0 for seed in SEEDS}
    mismatches = []
    n = 0

    for seed in SEEDS:
        # kit/evaluate.py:134 — n=3 cycles buyer types in make_scenarios.
        scenarios = buyers.make_scenarios(store, policy, 3, seed, buyers.BUYERS)
        for sc in scenarios:
            res_spike, res_mini, spike, mini = _play(store, policy, sc)
            n += 1
            seed_counts[seed] += 1

            # The pipeline's basket must exist once the first message was seen.
            assert mini.turns, f"no seller turn recorded for {sc['id']}"
            assert mini.turns[0]["basket"] is not None, (
                f"view_ref._basket still None after first message ({sc['id']})"
            )

            trace = _first_divergence(seed, sc, res_spike, res_mini, spike, mini)
            if trace is not None:
                mismatches.append(trace)

    print(
        f"\nscenarios compared: {n} "
        f"({len(SEEDS)} seeds x {len(BUYER_NAMES)} public buyers; "
        f"per seed: {list(seed_counts.values())})"
    )
    for trace in mismatches:
        print(trace)

    assert n == 21, f"expected 21 scenarios, ran {n}"
    assert not mismatches, f"{len(mismatches)} scenario(s) diverged from the spike"


# ---------------------------------------------------------------------------
# Test 2: MiniSeller never raises out of respond() on malformed messages
# ---------------------------------------------------------------------------

MALFORMED_MESSAGES = [
    {},
    {"type": None, "items": None},
    {"type": "request"},
    {"type": "request", "items": "not a list"},
    {"type": "request", "items": {"sku": "S001", "qty": 1}},
    {"type": "request", "items": [None, 3, "x", [], {}]},
    {"type": "counter", "items": [{"sku": "S001", "qty": 2, "unit_price": math.nan}]},
    {"type": "counter", "items": [{"sku": "S001", "qty": 2, "unit_price": math.inf}]},
    {"type": "counter", "items": [{"sku": "S001", "qty": -5, "unit_price": -1}]},
    {"type": "counter", "items": [{"sku": "S999", "qty": 1, "unit_price": 100}]},
    {"type": "counter", "items": [{"sku": "S001", "qty": 10**9, "unit_price": 10**9}]},
    {"type": "counter", "items": [{"sku": None, "qty": True, "unit_price": True}]},
    {"type": "counter", "items": [{"sku": "S001"}]},
    {"type": "offer", "items": [{"sku": "S001", "qty": 1, "unit_price": 500}]},
    {"type": "weird", "items": 42},
    {"type": "request", "round": "not an int", "items": [{"sku": "S001", "qty": 1}]},
]


def test_mini_seller_never_raises_on_malformed_messages():
    """Any exception inside respond() is converted to a walk_away, per the spike."""
    store, policy = load_store(), load_policy()
    allowed = {"offer", "accept", "walk_away", "message"}
    kinds = []
    for msg in MALFORMED_MESSAGES:
        seller = MiniSeller(store, policy)
        seller.start("malformed")
        try:
            out = seller.respond(msg)
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(
                f"MiniSeller raised on {msg!r}: {exc!r}"
            ) from exc
        assert isinstance(out, dict), f"non-dict reply for {msg!r}: {out!r}"
        assert out.get("type") in allowed, f"unexpected reply type for {msg!r}: {out!r}"
        kinds.append(out.get("type"))

    print(f"\nmalformed messages handled without raising: {len(MALFORMED_MESSAGES)}"
          f" -> {sorted(set(kinds))}")
    assert len(kinds) == len(MALFORMED_MESSAGES)


# ---------------------------------------------------------------------------
# Test 3: echo_alloc="exact" runs end to end (no equality claim)
# ---------------------------------------------------------------------------

def test_echo_alloc_exact_runs():
    """The exact-echo allocator completes every scenario without error."""
    store, policy = load_store(), load_policy()
    n = 0
    for seed in SEEDS:
        scenarios = buyers.make_scenarios(store, policy, 3, seed, buyers.BUYERS)
        for sc in scenarios:
            buyer = buyers.BUYERS[sc["buyer"]](sc, store, random.Random(sc["seed"]))
            seller = MiniSeller(store, policy, echo_alloc="exact")
            result = run_negotiation(seller, buyer, store, policy, sc["id"])
            assert result["ended"] is not None, f"{sc['id']} never ended"
            assert all(
                m["type"] in {"offer", "accept", "walk_away", "message"}
                for m in result["transcript"] if m["from"] == "seller"
            )
            n += 1
    print(f"\necho_alloc='exact' negotiations completed: {n}")
    assert n == 21


# ---------------------------------------------------------------------------
# Test 4: basket access contract — formed on the first message, never None
# ---------------------------------------------------------------------------

def test_basket_is_formed_after_first_message():
    """view_ref._basket is populated (and stock-capped) after the first respond()."""
    store, policy = load_store(), load_policy()
    seller = MiniSeller(store, policy)
    seller.start("basket")
    assert seller._view_ref is not None
    assert seller._view_ref._basket is None, "basket must start unset"

    out = seller.respond({
        "type": "request",
        "round": 1,
        "items": [{"sku": "S001", "qty": 2}],
    })
    assert out["type"] == "offer"
    basket = seller._view_ref._basket
    assert basket is not None, "view_ref._basket must be set after the first message"
    # S001 has stock 1 in kit/store.csv, so the requested qty 2 is capped to 1.
    assert basket == {"S001": 1}
