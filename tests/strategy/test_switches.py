"""Switch-level tests for verity/strategy.py.

A. echo_buyer_total=False  -> normal counter instead of echoing the buyer's total
                              (ACCEPT behaviour unchanged)
B. round-10 margin         -> one source of truth, exercised at 0.0 / 0.03 / 0.08
C. r10_require_rising      -> floor offer only with a strictly rising bid history
D. markup branch (m > 0)   -> ratio=None, because the spike never updates last_o
                              there (legacy_spike.py:191-195)
E. differential sweep      -> MiniSeller(cfg) vs legacy_spike.Seller(store, policy,
                              params=cfg) on seeds [1,2,3] x the 3 public buyers.

legacy_spike.Seller accepts a params dict that overrides its P defaults
(legacy_spike.py:11-12: ``self.p = dict(P, **(params or {}))``), so the spike can
be driven with exactly the same parameters as the Config under test.
"""
from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "kit"
if str(KIT) not in sys.path:
    sys.path.insert(0, str(KIT))

import buyers  # noqa: E402
from harness import load_policy, load_store, run_negotiation  # noqa: E402

from experiments.mini_seller import MiniSeller  # noqa: E402
from verity.config import Config  # noqa: E402
from verity.contracts import Action, Mode, View  # noqa: E402
from verity.legacy_spike import Seller as SpikeSeller  # noqa: E402
from verity.strategy import Strategy  # noqa: E402

# legacy_spike.P keys (legacy_spike.py:5) — the only knobs the spike understands.
SPIKE_PARAM_KEYS = ("T", "e", "slack", "m", "g", "walk_slack")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _view(
    *,
    round: int = 1,
    L: int = 1000,
    F: int = 700,
    bids=(),
    bid_complete: bool = True,
    bid_valid_as_made: bool = False,
    last_offer_ratio=None,
    msg_type: str = "counter",
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
# A. echo_buyer_total
# ---------------------------------------------------------------------------

def test_echo_buyer_total_default_echoes_buyer_total():
    """Default True = spike: take, not acceptable as made -> echo int(b * L), EXACT."""
    # r=3, F/L=0.7, T=6, e=0.5 -> target 0.7 + 0.3*sqrt(4/6) = 0.9449,
    # min with last_o=0.9 -> 0.9.  b=0.92 >= 0.9 -> take.
    v = _view(round=3, bids=[0.92], last_offer_ratio=0.9, bid_valid_as_made=False)
    d = _decide(v)
    assert d.action == Action.COUNTER
    assert d.mode == Mode.EXACT
    assert d.reason == "take_echo"
    assert d.total == 920
    assert d.ratio == pytest.approx(0.92)


def test_echo_buyer_total_false_returns_normal_counter():
    """echo_buyer_total=False: no re-slice; counter at max(target, floor)."""
    cfg = Config.from_switches("echo_buyer_total=false")
    v = _view(round=3, bids=[0.92], last_offer_ratio=0.9, bid_valid_as_made=False)
    d = _decide(v, cfg)
    assert d.action == Action.COUNTER
    assert d.mode == Mode.AT_MOST
    assert d.reason == "take_counter"
    assert d.total == 900
    assert d.ratio == pytest.approx(0.9)


def test_echo_buyer_total_false_clamps_counter_to_floor():
    """The disabled-echo counter still respects the floor (max(o, F/L))."""
    cfg = Config.from_switches("echo_buyer_total=false")
    # Round 10, bid above floor, target collapsed to the floor ratio.
    v = _view(round=10, bids=[0.95], L=1000, F=700, last_offer_ratio=0.96)
    d = _decide(v, cfg)
    assert d.action == Action.COUNTER
    assert d.mode == Mode.AT_MOST
    assert d.total == 700
    assert d.ratio == pytest.approx(0.7)


def test_echo_buyer_total_false_does_not_change_accept():
    """ACCEPT behaviour is unchanged by echo_buyer_total."""
    cfg = Config.from_switches("echo_buyer_total=false")
    v = _view(round=3, bids=[0.92], last_offer_ratio=0.9, bid_valid_as_made=True)
    d = _decide(v, cfg)
    assert d.action == Action.ACCEPT
    assert d.ratio == pytest.approx(0.92)


# ---------------------------------------------------------------------------
# B/C. round-10 margin + r10_require_rising
#   L=1000, F=900 -> floor_ratio=0.90.  est = bids[-1] + inc*g*2 with g=0.5.
#     rising  [0.80, 0.88] -> est 0.96
#     flat    [0.86, 0.86] -> est 0.86
#     falling [0.92, 0.88] -> est 0.88
#   thresholds 0.90 * walk_slack: 0.900 (margin 0.00), 0.873 (0.03), 0.828 (0.08)
# ---------------------------------------------------------------------------

R10_BIDS = {
    "rising": [0.80, 0.88],
    "flat": [0.86, 0.86],
    "falling": [0.92, 0.88],
}

# (require_rising, shape) -> {margin: floor offer?}; values hardcoded on purpose.
R10_EXPECTED = {
    (False, "rising"): {0.0: True, 0.03: True, 0.08: True},
    (False, "flat"): {0.0: False, 0.03: False, 0.08: True},
    (False, "falling"): {0.0: False, 0.03: True, 0.08: True},
    (True, "rising"): {0.0: True, 0.03: True, 0.08: True},
    (True, "flat"): {0.0: False, 0.03: False, 0.08: False},
    (True, "falling"): {0.0: False, 0.03: False, 0.08: False},
}

R10_CASES = [
    (require_rising, shape, margin, expect_offer)
    for (require_rising, shape), by_margin in R10_EXPECTED.items()
    for margin, expect_offer in by_margin.items()
]


@pytest.mark.parametrize("require_rising,shape,margin,expect_offer", R10_CASES)
def test_r10_margin_and_require_rising(require_rising, shape, margin, expect_offer):
    """Round-10 below-floor branch: floor offer vs WALK_AWAY."""
    cfg = Config.from_switches(
        f"r10_close_margin={margin},r10_require_rising={str(require_rising).lower()}"
    )
    # from_switches is the alias surface: walk_slack must track 1 - margin.
    assert cfg.walk_slack == pytest.approx(1.0 - margin)
    v = _view(round=10, bids=R10_BIDS[shape], L=1000, F=900, last_offer_ratio=1.0)
    d = _decide(v, cfg)
    if expect_offer:
        assert d.action == Action.COUNTER, f"expected floor offer, got {d}"
        assert d.total == 900
        assert d.ratio is None
        assert d.reason == "r10_floor"
    else:
        assert d.action == Action.WALK_AWAY, f"expected WALK_AWAY, got {d}"
        assert d.reason == "r10_walk"


def test_r10_require_rising_needs_strictly_rising_history():
    """Equal final bids (flat) never satisfy the rising test, even with one step up."""
    cfg = Config.from_switches("r10_require_rising=true,m=0")
    # est is high enough (0.96) but bids[-1] == bids[-2] -> walk.
    v = _view(round=10, bids=[0.88, 0.88], L=1000, F=900, last_offer_ratio=1.0)
    assert _decide(v, cfg).action == Action.WALK_AWAY
    # A single below-floor bid cannot be rising either (len(bids) >= 2 required),
    # even though est alone would clear the threshold.
    v1 = _view(round=10, bids=[0.88], L=1000, F=900, last_offer_ratio=1.0)
    assert _decide(v1, cfg).action == Action.WALK_AWAY
    # Without the switch the same view still offers at the floor.
    assert _decide(v1, Config()).action == Action.COUNTER


def test_r10_require_rising_does_not_affect_earlier_rounds():
    """The switch only gates the round >= max_round below-floor branch."""
    v = _view(round=3, bids=[0.60], L=1000, F=900, last_offer_ratio=1.0)
    default = _decide(v, Config())
    strict = _decide(v, Config.from_switches("r10_require_rising=true"))
    assert default == strict
    assert default.action == Action.COUNTER


def test_r10_close_margin_matches_default_walk_slack():
    """0.03 spelling is exactly the default margin (single source of truth)."""
    assert Config.from_switches("r10_close_margin=0.03") == Config()
    assert Config(walk_slack=0.92).r10_close_margin == pytest.approx(0.08)


# ---------------------------------------------------------------------------
# D. markup branch
# ---------------------------------------------------------------------------

def test_markup_branch_returns_ratio_none():
    """m > 0 markup offer must not update last_o: ratio is None (legacy_spike.py:191-195)."""
    cfg = Config(m=0.05)
    # r=10, b=0.86 above floor 0.7, rising bids -> markup branch.
    v = _view(round=10, bids=[0.80, 0.86], L=1000, F=700, last_offer_ratio=1.0)
    d = _decide(v, cfg)
    assert d.action == Action.COUNTER
    assert d.reason == "markup"
    assert d.ratio is None
    # pr = min(1.0, 0.86 + 0.05 * 0.06) = 0.863 -> 863 rupees
    assert d.total == 863


def test_markup_disabled_takes_echo_path():
    """m=0 (the default) never reaches markup; the take path echoes instead."""
    v = _view(round=10, bids=[0.80, 0.86], L=1000, F=700, last_offer_ratio=1.0)
    d = _decide(v, Config())
    assert d.reason == "take_echo"
    assert d.ratio == pytest.approx(0.86)


# ---------------------------------------------------------------------------
# E. differential sweep: MiniSeller(cfg) vs legacy_spike.Seller(params=cfg)
# ---------------------------------------------------------------------------

class _Recorder:
    """Pass-through wrapper: snapshots each seller reply without altering it."""

    def __init__(self, seller):
        self.seller = seller
        self.turns = []

    def start(self, negotiation_id):
        self.seller.start(negotiation_id)

    def respond(self, msg):
        out = self.seller.respond(msg)
        self.turns.append({
            "out": out,
            "view": getattr(self.seller, "last_view", None),
            "last_o": getattr(self.seller, "last_o", None),
        })
        return out


def _canon(x) -> str:
    return json.dumps(x, sort_keys=True, default=repr)


def _sig(msg):
    """(type, order-insensitive items) signature of a seller message."""
    if not isinstance(msg, dict):
        return None
    items = msg.get("items")
    if not isinstance(items, list):
        key = None
    else:
        key = tuple(sorted(_canon(it) for it in items))
    return (msg.get("type"), key)


def _param_sets(n: int) -> "list[dict]":
    """Deterministic pseudo-random parameter sets for the differential sweep."""
    rng = random.Random(20261125)
    out = []
    for _ in range(n):
        out.append({
            "T": round(rng.uniform(3.0, 9.0), 3),
            "e": round(rng.uniform(0.3, 2.0), 3),
            "slack": round(rng.uniform(0.0, 0.03), 4),
            "g": round(rng.uniform(0.0, 1.0), 3),
            "walk_slack": round(rng.uniform(0.90, 1.0), 4),
            "m": rng.choice([0.0, 0.05]),
        })
    return out


def _compare(store, policy, sc, cfg, params):
    """Play one scenario with both sellers; return a first-divergence trace or None."""
    buyer_cls = buyers.BUYERS[sc["buyer"]]
    buyer_spike = buyer_cls(sc, store, random.Random(sc["seed"]))
    buyer_mini = buyer_cls(sc, store, random.Random(sc["seed"]))
    spike = _Recorder(SpikeSeller(store, policy, params=dict(params)))
    mini = _Recorder(MiniSeller(store, policy, cfg=cfg))

    # The spike must really be running the parameters under test.
    for k in SPIKE_PARAM_KEYS:
        assert spike.seller.p[k] == getattr(cfg, k), f"spike param {k} not overridden"

    res_spike = run_negotiation(spike, buyer_spike, store, policy, sc["id"])
    res_mini = run_negotiation(mini, buyer_mini, store, policy, sc["id"])

    label = f"params={params} seed={sc['seed']} buyer={sc['buyer']} scenario={sc['id']}"
    for k in range(max(len(spike.turns), len(mini.turns))):
        st = spike.turns[k] if k < len(spike.turns) else None
        mt = mini.turns[k] if k < len(mini.turns) else None
        s_sig = _sig(st["out"]) if st is not None else None
        m_sig = _sig(mt["out"]) if mt is not None else None
        if s_sig != m_sig:
            lines = [f"MISMATCH {label} at seller turn {k + 1}"]
            if st is not None:
                lines.append(f"  spike last_o={st['last_o']!r} out={st['out']!r}")
            else:
                lines.append("  spike: no turn at this index")
            if mt is not None:
                lines.append(f"  mini  view={mt['view']!r}")
                lines.append(f"  mini  last_o={mt['last_o']!r} out={mt['out']!r}")
            else:
                lines.append("  mini: no turn at this index")
            return "\n".join(lines)

    outcomes_differ = (
        res_spike["ended"] != res_mini["ended"]
        or _canon(res_spike["deal"]) != _canon(res_mini["deal"])
    )
    if outcomes_differ:
        return "\n".join([
            f"MISMATCH {label} outcome",
            f"  spike ended={res_spike['ended']!r} deal={res_spike['deal']!r}",
            f"  mini  ended={res_mini['ended']!r} deal={res_mini['deal']!r}",
        ])
    return None


def test_differential_param_sweep_vs_legacy_spike(monkeypatch):
    """12 parameter sets x seeds [1,2,3] x 3 public buyers must match the spike."""
    store, policy = load_store(), load_policy()
    sets = _param_sets(12)
    # Count the reasons the strategy actually produces, so we can prove the sweep
    # exercises the m > 0 markup branch instead of passing vacuously.
    counts: Counter = Counter()
    orig_decide = Strategy.decide

    def _counting_decide(self, view):
        decision = orig_decide(self, view)
        counts[decision.reason] += 1
        return decision

    monkeypatch.setattr(Strategy, "decide", _counting_decide)
    mismatches = []
    n = 0
    for params in sets:
        cfg = Config(**params)
        for seed in (1, 2, 3):
            scenarios = buyers.make_scenarios(store, policy, 3, seed, buyers.BUYERS)
            for sc in scenarios:
                n += 1
                trace = _compare(store, policy, sc, cfg, params)
                if trace is not None:
                    mismatches.append(trace)

    print(f"\nparameter sets: {len(sets)}; negotiations compared: {n}")
    print(f"decision reasons: {dict(sorted(counts.items()))}")
    for trace in mismatches[:10]:
        print(trace)
    if len(mismatches) > 10:
        print(f"... {len(mismatches) - 10} more mismatch trace(s) not shown")

    assert n == 108, f"expected 12 parameter sets x 3 seeds x 3 buyers = 108, ran {n}"
    assert not mismatches, f"{len(mismatches)} of {n} negotiation(s) diverged from the spike"
    assert counts["markup"] >= 1, (
        "sweep never reached the m > 0 markup branch: "
        f"reasons={dict(sorted(counts.items()))}"
    )
