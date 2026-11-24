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
