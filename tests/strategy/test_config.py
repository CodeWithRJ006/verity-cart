"""Tests for verity/config.py.

Verifies:
- from_switches raises ValueError on unknown key
- __post_init__ raises ValueError on bad enum values
- Default values match legacy_spike.P (legacy_spike.py:5)
"""
from __future__ import annotations

import pytest

from verity.config import Config

# ---------------------------------------------------------------------------
# Unknown key raises
# ---------------------------------------------------------------------------

def test_unknown_key_raises():
    with pytest.raises(ValueError, match="Unknown config switch"):
        Config.from_switches("does_not_exist=1")


# ---------------------------------------------------------------------------
# Bad enum raises
# ---------------------------------------------------------------------------

def test_bad_partial_bid_policy_raises():
    with pytest.raises(ValueError, match="partial_bid_policy"):
        Config(partial_bid_policy="skip")


def test_bad_allocator_raises():
    with pytest.raises(ValueError, match="allocator"):
        Config(allocator="random")


def test_bad_enum_via_from_switches():
    with pytest.raises(ValueError, match="partial_bid_policy"):
        Config.from_switches("partial_bid_policy=skip")


# ---------------------------------------------------------------------------
# Defaults equal legacy_spike.P values (legacy_spike.py:5)
#   P = dict(T=6.0, e=0.5, slack=0.0, m=0.0, g=0.5, walk_slack=0.97)
# ---------------------------------------------------------------------------

def test_defaults_match_spike():
    cfg = Config()
    # legacy_spike.py:5  P["T"] = 6.0
    assert cfg.T == 6.0,         f"T: expected 6.0, got {cfg.T}"
    # legacy_spike.py:5  P["e"] = 0.5
    assert cfg.e == 0.5,         f"e: expected 0.5, got {cfg.e}"
    # legacy_spike.py:5  P["slack"] = 0.0
    assert cfg.slack == 0.0,     f"slack: expected 0.0, got {cfg.slack}"
    # legacy_spike.py:5  P["m"] = 0.0
    assert cfg.m == 0.0,         f"m: expected 0.0, got {cfg.m}"
    # legacy_spike.py:5  P["g"] = 0.5
    assert cfg.g == 0.5,         f"g: expected 0.5, got {cfg.g}"
    # legacy_spike.py:5  P["walk_slack"] = 0.97
    assert cfg.walk_slack == 0.97, f"walk_slack: expected 0.97, got {cfg.walk_slack}"


def test_accept_require_complete_default_false():
    assert Config().accept_require_complete is False


# ---------------------------------------------------------------------------
# Round-10 margin: walk_slack and r10_close_margin are one quantity.
# walk_slack is the stored field; r10_close_margin = 1 - walk_slack is derived.
# ---------------------------------------------------------------------------

def test_r10_close_margin_is_derived_from_walk_slack():
    assert Config().r10_close_margin == pytest.approx(0.03)
    assert Config(walk_slack=0.92).r10_close_margin == pytest.approx(0.08)
    assert Config(walk_slack=1.0).r10_close_margin == pytest.approx(0.0)


def test_from_switches_accepts_r10_close_margin_spelling():
    cfg = Config.from_switches("r10_close_margin=0.08")
    assert cfg.walk_slack == pytest.approx(0.92)
    assert cfg.r10_close_margin == pytest.approx(0.08)


def test_from_switches_accepts_walk_slack_spelling():
    cfg = Config.from_switches("walk_slack=0.92")
    assert cfg.walk_slack == pytest.approx(0.92)
    assert cfg.r10_close_margin == pytest.approx(0.08)


def test_from_switches_accepts_consistent_pair():
    cfg = Config.from_switches("walk_slack=0.92,r10_close_margin=0.08")
    assert cfg.walk_slack == pytest.approx(0.92)


def test_from_switches_rejects_inconsistent_pair():
    with pytest.raises(ValueError, match="disagree"):
        Config.from_switches("walk_slack=0.97,r10_close_margin=0.08")


def test_from_switches_r10_close_margin_bad_float_raises():
    with pytest.raises(ValueError, match="Invalid float value for r10_close_margin"):
        Config.from_switches("r10_close_margin=soon")
