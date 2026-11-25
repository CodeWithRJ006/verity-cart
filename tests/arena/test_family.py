"""Tests for arena/family.py (Dev3). Never imports verity."""
# ruff: noqa: I001
import os
import random
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "kit"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(KIT))

import buyers as kb  # noqa: E402
from harness import load_policy, load_store  # noqa: E402
from arena import family as fam  # noqa: E402

STORE, POLICY = load_store(), load_policy()
ALL = fam.make_buyers(fam.family_variants())


def scenarios(name, n=40, seed=1):
    return kb.make_scenarios(STORE, POLICY, n, seed, {name: ALL[name]})


def play(name, scenario, seed=5):
    """Drive one buyer against a scripted seller that offers 90% of list, then decays."""
    b = ALL[name](scenario, STORE, random.Random(scenario["seed"]))
    out = [b.open()]
    for r in range(1, 11):
        items = [{"sku": i["sku"], "qty": i["qty"],
                  "unit_price": max(1, int(STORE[i["sku"]]["price"] * (0.95 - 0.07 * r)))} for i in scenario["items"]]
        msg = b.respond({"type": "offer", "items": items, "round": r, "text": ""})
        out.append(msg)
        if msg["type"] != "counter":
            break
    return out


def test_family_has_20_unique_configs_and_40_variants():
    cfgs = fam.build_family()
    assert len(cfgs) == 20 and len({c["name"] for c in cfgs}) == 20
    assert len(fam.family_variants()) == 40


@pytest.mark.parametrize("name", sorted(ALL))
def test_deterministic(name):
    for sc in scenarios(name, 6):
        assert play(name, sc) == play(name, sc)


@pytest.mark.parametrize("name", sorted(ALL))
def test_no_negative_bid_no_limit_leak_no_overbid(name):
    cfg = next(c for c in fam.family_variants() if c["name"] == name)
    for sc in scenarios(name):
        res = sc["reservation"]
        for m in play(name, sc):
            text = m.get("text", "")
            assert str(res) not in text and "reservation" not in text.lower()
            for it in m.get("items") or []:
                assert it["unit_price"] >= 1
                if it["unit_price"] == 1 or it["sku"] not in {i["sku"] for i in sc["items"]}:
                    continue                                   # junk line, not a price bid
                if m is not None and not cfg["above_list"]:
                    # 10-rupee rounding / 10-rupee minimum price can exceed the share slightly
                    assert it["unit_price"] <= STORE[it["sku"]]["price"] * res + 10 + 1e-6


def test_above_list_edge_case_really_above_list():
    sc = scenarios("D15_above_list", 5)[0]
    msgs = play("D15_above_list", sc)
    assert any(i["unit_price"] > STORE[i["sku"]]["price"] for m in msgs for i in m.get("items") or [])


def test_attack_style_produces_junk_lines():
    junk = 0
    for sc in scenarios("C10_attack_fast", 60):
        wanted = {i["sku"]: i["qty"] for i in sc["items"]}
        for m in play("C10_attack_fast", sc)[1:]:
            for it in m.get("items") or []:
                if it["sku"] not in wanted or it["unit_price"] == 1 or it["qty"] > STORE[it["sku"]]["stock"]:
                    junk += 1
    assert junk > 0


def test_non_attack_configs_send_no_junk():
    for sc in scenarios("A00_fast_low", 40):
        wanted = {i["sku"] for i in sc["items"]}
        for m in play("A00_fast_low", sc):
            for it in m.get("items") or []:
                assert it["sku"] in wanted and it["unit_price"] > 1


def test_never_leaves_config_does_not_walk():
    for sc in scenarios("C11_attack_stubborn", 20):
        assert all(m["type"] != "walk_away" for m in play("C11_attack_stubborn", sc))


def test_split_matches_family():
    import json
    split = json.loads((ROOT / "arena" / "family_split.json").read_text())["split"]
    names = {c["name"] for c in fam.build_family()}
    assert set(split["TRAIN"]) | set(split["TEST"]) == names
    assert not set(split["TRAIN"]) & set(split["TEST"])
    assert len(split["TRAIN"]) == 12 and len(split["TEST"]) == 8
    assert {n for n in names if n.startswith("C")} <= set(split["TEST"])


def _evaluate(seller_rel, attack=None):
    env = dict(os.environ)
    if attack:
        env["FAMILY_ATTACK"] = attack
    p = subprocess.run([sys.executable, "evaluate.py", "--seller", seller_rel, "--buyers", "../arena/family.py",
                        "--seed", "0", "--n", "100", "--no-baseline"],
                       cwd=str(KIT), env=env, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-500:]
    assert re.search(r"^policy violations\s+0$", p.stdout, re.M), p.stdout
    assert re.search(r"^truth violations\s+0$", p.stdout, re.M), p.stdout
    return p.stdout


@pytest.mark.parametrize("attack", [None, "on", "both"])
def test_end_to_end_baseline(attack):
    _evaluate("example_seller.py", attack)


@pytest.mark.skipif(not (ROOT / "seller_spike.py").exists(), reason="seller_spike.py not at repo root")
@pytest.mark.parametrize("attack", [None, "on", "both"])
def test_end_to_end_spike(attack):
    _evaluate("../seller_spike.py", attack)
