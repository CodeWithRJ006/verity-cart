"""Unit tests for verity/strategy.py.

Covers 8 edge cases:
  1. r=1, no bid              -> COUNTER at L (ratio 1.0)
  2. bid below floor at r<10  -> COUNTER above bid, non-increasing
  3. bid above list           -> ACCEPT (bid_valid_as_made guards this)
  4. flat bids                -> monotone non-increasing offers
  5. falling bids             -> offers never below F
  6. single-line basket       -> basic sanity
  7. F == L (zero slack)      -> only valid price is F=L
  8. round-10 below floor     -> with/without rising bids (walk or floor offer)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[2] / "kit"
if str(KIT) not in sys.path:
    sys.path.insert(0, str(KIT))

from verity.config import Config  # noqa: E402
from verity.contracts import Action, Decision, View  # noqa: E402
from verity.strategy import Strategy  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _view(
    *,
    round: int = 1,
    msg_type: str = "counter",
    L: int = 1000,
    F: int = 700,
    bids: "list[float]" = (),
    bid_complete: bool = True,
    bid_valid_as_made: bool = False,
    last_offer_ratio: "float | None" = None,
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


def _cfg(**kw) -> Config:
    return Config(**kw)


def _decide(view: View, cfg: "Config | None" = None) -> Decision:
    if cfg is None:
        cfg = _cfg()
    return Strategy(cfg).decide(view)


# ---------------------------------------------------------------------------
# Case 1: r=1, no bid -> COUNTER at L, ratio=1.0
# ---------------------------------------------------------------------------

def test_r1_no_bid_offers_list():
    """With no bids, strategy must offer at list price (legacy_spike.py:174-178)."""
    v = _view(round=1, bids=[], L=1000, F=700, last_offer_ratio=None)
    d = _decide(v)
    assert d.action == Action.COUNTER
    assert d.total == 1000
    assert d.ratio == 1.0


# ---------------------------------------------------------------------------
# Case 2: bid below floor at r < 10 -> COUNTER, offer monotone non-increasing
# ---------------------------------------------------------------------------

def test_bid_below_floor_counters_above():
    """Bid at 50% list while floor is 70%: strategy should counter above bid."""
    # F/L = 0.70; bid = 0.50 < floor_ratio -> must counter >= F
    v = _view(round=2, bids=[0.50], L=1000, F=700, last_offer_ratio=1.0)
    d = _decide(v)
    assert d.action == Action.COUNTER
    assert d.total is not None
    assert d.total >= 700, f"total {d.total} below floor 700"
    assert d.total <= 1000, f"total {d.total} above list 1000"


def test_offers_monotone_non_increasing():
    """Successive bids: each counter offer ratio must not exceed the previous."""
    cfg = _cfg(T=6.0, e=0.5)
    L, F = 1000, 600
    # Simulate bids rising slowly
    bid_sequence = [0.70, 0.72, 0.74]
    ratios = []
    last_o = None
    for r, b in enumerate(bid_sequence, start=1):
        v = _view(round=r, bids=bid_sequence[:r], L=L, F=F, last_offer_ratio=last_o)
        d = Strategy(cfg).decide(v)
        assert d.action == Action.COUNTER
        assert d.total is not None
        assert d.total >= F
        ratio = d.total / L
        ratios.append(ratio)
        last_o = d.ratio  # state.py would persist this

    # Monotone non-increasing
    for i in range(1, len(ratios)):
        assert ratios[i] <= ratios[i - 1] + 1e-9, (
            f"offer ratio increased at step {i}: {ratios[i - 1]:.4f} -> {ratios[i]:.4f}"
        )


# ---------------------------------------------------------------------------
# Case 3: bid above list price (bid_valid_as_made ensures it was acceptable)
# ---------------------------------------------------------------------------

def test_bid_at_list_accepted_when_valid():
    """bid ratio = 1.0 (at list) and bid_valid_as_made=True -> ACCEPT."""
    v = _view(round=1, bids=[1.0], L=1000, F=700,
              bid_complete=True, bid_valid_as_made=True, last_offer_ratio=None)
    d = _decide(v)
    assert d.action == Action.ACCEPT


def test_bid_valid_false_no_accept():
    """Even if take is triggered, bid_valid_as_made=False -> no ACCEPT."""
    v = _view(round=1, bids=[1.0], L=1000, F=700,
              bid_complete=True, bid_valid_as_made=False, last_offer_ratio=None)
    d = _decide(v)
    # Cannot accept; must counter or walk
    assert d.action != Action.ACCEPT


# ---------------------------------------------------------------------------
# Case 4: flat bids (no movement) -> strategy still non-increasing, never below F
# ---------------------------------------------------------------------------

def test_flat_bids_never_below_floor():
    """Flat bids at 60%: offers must stay >= F throughout."""
    cfg = _cfg()
    L, F = 1000, 700
    bid = 0.60
    last_o = None
    for r in range(1, 9):
        v = _view(round=r, bids=[bid] * r, L=L, F=F, last_offer_ratio=last_o)
        d = Strategy(cfg).decide(v)
        assert d.total is not None
        assert d.total >= F, f"round {r}: total {d.total} < floor {F}"
        last_o = d.ratio


# ---------------------------------------------------------------------------
# Case 5: falling bids -> offers never below F
# ---------------------------------------------------------------------------

def test_falling_bids_never_below_floor():
    """Bids that fall should not drive our offer below floor."""
    cfg = _cfg()
    L, F = 1000, 700
    bids = [0.90, 0.80, 0.70, 0.60, 0.50]
    last_o = None
    for r, _ in enumerate(bids, start=1):
        v = _view(round=r, bids=bids[:r], L=L, F=F, last_offer_ratio=last_o)
        d = Strategy(cfg).decide(v)
        assert d.total is not None
        assert d.total >= F, f"round {r}: total {d.total} < floor {F}"
        last_o = d.ratio


# ---------------------------------------------------------------------------
# Case 6: single-line basket
# ---------------------------------------------------------------------------

def test_single_sku_basket_basic():
    """Single SKU: strategy runs without error and returns valid total."""
    v = _view(round=1, bids=[], L=500, F=350)
    d = _decide(v)
    assert d.action == Action.COUNTER
    assert d.total == 500  # no bid -> list price


def test_single_sku_counter():
    v = _view(round=3, bids=[0.75], L=500, F=350, last_offer_ratio=1.0)
    d = _decide(v)
    assert d.action == Action.COUNTER
    assert d.total is not None
    assert 350 <= d.total <= 500


# ---------------------------------------------------------------------------
# Case 7: F == L (zero margin; only one valid price point)
# ---------------------------------------------------------------------------

def test_f_equals_l_offers_exactly_f():
    """When F == L, the only valid total is F (== L). Counter must equal F."""
    L = F = 1000
    v = _view(round=1, bids=[], L=L, F=F)
    d = _decide(v)
    assert d.action == Action.COUNTER
    assert d.total == L


def test_f_equals_l_bid_at_ratio_1():
    """F==L, bid=1.0 -> ACCEPT when bid_valid_as_made."""
    L = F = 1000
    v = _view(round=2, bids=[1.0], L=L, F=F,
              bid_complete=True, bid_valid_as_made=True, last_offer_ratio=1.0)
    d = _decide(v)
    assert d.action == Action.ACCEPT


# ---------------------------------------------------------------------------
# Case 8: round-10 below floor — walk vs floor offer
# ---------------------------------------------------------------------------

def test_r10_below_floor_walks_when_est_low():
    """Round 10, bid below floor, est < floor*walk_slack -> WALK_AWAY."""
    cfg = _cfg(walk_slack=0.97)
    L, F = 1000, 800
    # floor_ratio = 0.80, walk_slack threshold = 0.776
    # single bid well below floor, no movement -> est = bid (inc=0)
    # est=0.50 < 0.776 -> walk
    v = _view(round=10, bids=[0.50], L=L, F=F, last_offer_ratio=1.0)
    d = Strategy(cfg).decide(v)
    assert d.action == Action.WALK_AWAY, f"expected WALK_AWAY, got {d}"


def test_r10_below_floor_offers_floor_when_est_high():
    """Round 10, bid below floor, est >= floor*walk_slack -> COUNTER at F, ratio=None."""
    cfg = _cfg(walk_slack=0.97)
    L, F = 1000, 800
    # floor_ratio = 0.80; walk_slack threshold = 0.776
    # Two bids rising steeply so est >= threshold
    # bids[-1]=0.75, bids[-2]=0.60 -> inc=0.15, est = 0.75 + 0.15*0.5*2 = 0.75+0.15=0.90
    # 0.90 >= 0.776 -> floor offer
    v = _view(round=10, bids=[0.60, 0.75], L=L, F=F, last_offer_ratio=1.0)
    d = Strategy(cfg).decide(v)
    assert d.action == Action.COUNTER
    assert d.total == F
    assert d.ratio is None, f"ratio should be None for r10_floor, got {d.ratio}"


def test_r10_below_floor_no_rising_bids_walks():
    """Round 10, bid below floor, flat bids (no rise) -> est too low -> WALK_AWAY."""
    cfg = _cfg(walk_slack=0.97)
    L, F = 1000, 800
    # floor_ratio=0.80, walk_slack threshold=0.776
    # bids=[0.70, 0.70] -> inc=0, est=0.70 < 0.776 -> walk
    v = _view(round=10, bids=[0.70, 0.70], L=L, F=F, last_offer_ratio=1.0)
    d = Strategy(cfg).decide(v)
    assert d.action == Action.WALK_AWAY


# ---------------------------------------------------------------------------
# accept_require_complete: when True, incomplete bid must not be accepted
# ---------------------------------------------------------------------------

def test_accept_require_complete_blocks_incomplete_bid():
    """accept_require_complete=True: take but bid_complete=False -> COUNTER, not ACCEPT."""
    cfg = _cfg(accept_require_complete=True)
    # bid=1.0 -> take is True; bid_valid_as_made=True; bid_complete=False
    v = _view(round=1, bids=[1.0], L=1000, F=700,
              bid_complete=False, bid_valid_as_made=True, last_offer_ratio=None)
    d = Strategy(cfg).decide(v)
    assert d.action != Action.ACCEPT


def test_accept_require_complete_false_allows_incomplete():
    """accept_require_complete=False (default): incomplete bid can still be accepted."""
    cfg = _cfg(accept_require_complete=False)
    v = _view(round=1, bids=[1.0], L=1000, F=700,
              bid_complete=False, bid_valid_as_made=True, last_offer_ratio=None)
    d = Strategy(cfg).decide(v)
    assert d.action == Action.ACCEPT


# ---------------------------------------------------------------------------
# allocator: only "proportional" is wired into Strategy so far
# ---------------------------------------------------------------------------

def test_allocator_proportional_constructs():
    """The default allocator constructs without complaint."""
    strategy = Strategy(Config())
    assert strategy._cfg.allocator == "proportional"


def test_allocator_greedy_raises_until_wired():
    """allocator="greedy" would be a silent no-op, so construction raises."""
    with pytest.raises(NotImplementedError, match="allocator=greedy is not wired"):
        Strategy(Config(allocator="greedy"))
