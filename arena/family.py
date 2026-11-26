"""arena/family.py — Parametric buyer family for VERITY-CART (Dev3).

ParamBuyer subclasses kit's Buyer.  Every config is a plain dict; given the same
(config, seed) it produces the same transcript.  Private limit is never sent in
any message.

Python 3.9, stdlib only.  Never imports verity.

Usage:
    from arena.family import build_family, ParamBuyer
    configs = build_family()          # list of 20 config dicts
    # configs are passed to make_scenarios() via the BUYERS dict mechanism, or
    # used directly by run_arena.py
"""

# ruff: noqa: I001
import os
import sys
from pathlib import Path

# Resolve kit/ so we can import Buyer without hardcoding cwd.
_KIT = Path(__file__).resolve().parent.parent / "kit"
sys.path.insert(0, str(_KIT))

from buyers import Buyer  # noqa: E402  (kit import after path fixup)


# ---------------------------------------------------------------------------
# ParamBuyer
# ---------------------------------------------------------------------------

class ParamBuyer(Buyer):
    """Parametric buyer driven by a config dict (scenario["_cfg"]).

    Invariants: deterministic given (config, scenario seed); the private reservation is
    never put in a message; bids never exceed the reservation, except the deliberate
    above_list edge case (first bids at 1.05 x list).  ratio is drawn ONCE per round.
    cfg keys: anchor_share, concession_exp, deadline (int 4-10 or None = never leaves),
    stubbornness, bid_noise, non_monotone, subset_lines, qty_change, above_list, attack_style.
    """

    feasible = 0.85
    zone = (0.15, 0.85)
    anchor = (0.50, 0.75)
    deadline = 8
    exponent = 1.0
    stubborn = 0.0

    def __init__(self, scenario, store, rng):
        super().__init__(scenario, store, rng)
        cfg = scenario.get("_cfg", {})
        self._anchor_share = cfg.get("anchor_share", 0.65)
        self._exp = cfg.get("concession_exp", 1.0)
        self._deadline = cfg["deadline"] if "deadline" in cfg else 8   # None = never walks
        self._stubbornness = cfg.get("stubbornness", 0.0)
        self._noise = cfg.get("bid_noise", 0.0)
        self._non_monotone = cfg.get("non_monotone", False)
        self._subset_lines = cfg.get("subset_lines", False)
        self._qty_change = cfg.get("qty_change", False)
        self._above_list = cfg.get("above_list", False)
        self._attack = cfg.get("attack_style", False)
        self._sent = None            # ratio of the last bid we sent
        self._cache = {}             # round -> ratio (one draw per round)
        res = self.s["reservation"]
        self._anchor = min(self._anchor_share, res)          # never open above own limit
        if self._subset_lines and len(self.basket) > 1:
            k = self.rng.randint(1, len(self.basket) - 1)
            self.basket = self.rng.sample(self.basket, k)

    # ------------------------------------------------------------------ numbers

    def _ratio_for(self, r):
        if r in self._cache:
            return self._cache[r]
        res = self.s["reservation"]
        horizon = max(1, self._deadline if self._deadline else 10)
        x = min(1.0, r / horizon) ** self._exp
        base = self._anchor + (res - self._anchor) * x
        if self._noise > 0:
            base += self.rng.uniform(-self._noise, self._noise)
        if self._non_monotone and self._sent is not None and self.rng.random() < 0.20:
            base = self._sent - self.rng.uniform(0.01, 0.03)
        base = max(0.01, min(base, res))
        if self._above_list and r == 1:
            base = 1.05                                       # deliberate edge case
        self._cache[r] = base
        return base

    def ratio(self, r):          # kept for base-class compatibility
        return self._ratio_for(r)

    # ------------------------------------------------------------------ protocol

    def open(self):
        ratio = 1.05 if self._above_list else self._anchor
        self._sent = ratio
        bid = self.priced(self.basket, ratio)
        return {"type": "request", "items": bid, "text": self.say_open(bid)}

    def respond(self, msg):
        r = msg.get("round", 1)
        ratio = self._ratio_for(r)
        offered = self.usable(msg.get("items")) if msg.get("type") == "offer" else None
        if offered:
            self.basket = [{"sku": i["sku"], "qty": i["qty"]} for i in offered]
            if self.total(offered) <= min(ratio, self.s["reservation"]) * self.listed(offered) + 1:
                return {"type": "accept", "text": self.say_accept()}
        if self._deadline is not None and r >= self._deadline:
            return {"type": "walk_away", "text": self.say_walk()}
        if self._stubbornness > 0 and self._sent is not None and self.rng.random() < self._stubbornness:
            ratio = self._sent                                # repeat last bid
        if self._qty_change and self.rng.random() < 0.25:
            for line in self.basket:
                if self.store[line["sku"]]["stock"] > 1:
                    line["qty"] = max(1, line["qty"] + self.rng.choice([-1, 1]))
        self._sent = ratio
        bid = self.priced(self.basket, ratio)
        text = self.say_counter(bid, msg, offered)
        if self._attack and self.rng.random() < 0.35:
            bid, note = self._trick(bid)
            text += " " + note
        return {"type": "counter", "items": bid, "text": text}

    # ------------------------------------------------------------------ attack

    def _trick(self, items):
        """Slip a junk line (out-of-stock, over-stock, or Rs 1) into the counter."""
        items = [dict(i) for i in items]
        gone = [r for r in self.store.values() if r["stock"] == 0]
        cheap = sorted((r for r in self.store.values() if r["stock"] > 0), key=lambda r: r["price"])[:10]
        kind = self.rng.choice(["out_of_stock", "over_stock", "one_rupee"])
        if kind == "out_of_stock" and gone:
            r = self.rng.choice(gone)
            items.append({"sku": r["sku"], "qty": 1, "unit_price": r["price"]})
            return items, "Add one %s too." % r["name"]
        if kind == "over_stock" and items:
            line = items[0]
            line["qty"] = self.store[line["sku"]]["stock"] + 5
            return items, "Make it %d of %s." % (line["qty"], line["sku"])
        r = self.rng.choice(cheap)
        items.append({"sku": r["sku"], "qty": 1, "unit_price": 1})
        return items, "Throw in a %s for Rs 1." % r["name"]

    # ------------------------------------------------------------------ text (never contains the limit)

    def say_open(self, bid):
        return "Hi, I would like these items. My offer: Rs %d." % self.total(bid)

    def say_counter(self, bid, msg, offered):
        return "How about Rs %d?" % self.total(bid)

    def say_accept(self):
        return "Deal."

    def say_walk(self):
        return "No deal, thanks."


# ---------------------------------------------------------------------------
# build_family()  — 20 named configs
# ---------------------------------------------------------------------------
#
# Design rationale (covers guide §3.1 corners):
#
#   Cluster A — "fast conceder"       configs 00-04  (TRAIN)
#   Cluster B — "stubborn/non-mono"   configs 05-09  (TRAIN)
#   Cluster C — "attacker"            configs 10-14  (TEST, held-out; C11 = late concession + never leaves + attack)
#   Cluster D — "edge cases"          configs 15-19  (TRAIN)
#
# Cluster C is the held-out cluster (TEST) so a whole behavioural pattern
# is invisible to Dev2 during tuning.

def build_family():
    """Return 20 ParamBuyer config dicts.  Each has a unique 'name' key."""
    configs = [
        # --- Cluster A: fast conceeders (TRAIN) ---
        {"name": "A00_fast_low",         "anchor_share": 0.45, "concession_exp": 0.4,
         "deadline": 5, "stubbornness": 0.0, "bid_noise": 0.00,
         "non_monotone": False, "subset_lines": False, "qty_change": False,
         "above_list": False, "attack_style": False},

        {"name": "A01_fast_mid",         "anchor_share": 0.60, "concession_exp": 0.5,
         "deadline": 5, "stubbornness": 0.0, "bid_noise": 0.01,
         "non_monotone": False, "subset_lines": False, "qty_change": False,
         "above_list": False, "attack_style": False},

        {"name": "A02_fast_high",        "anchor_share": 0.75, "concession_exp": 0.6,
         "deadline": 6, "stubbornness": 0.0, "bid_noise": 0.00,
         "non_monotone": False, "subset_lines": False, "qty_change": False,
         "above_list": False, "attack_style": False},

        {"name": "A03_fast_subset",      "anchor_share": 0.55, "concession_exp": 0.5,
         "deadline": 5, "stubbornness": 0.0, "bid_noise": 0.02,
         "non_monotone": False, "subset_lines": True,  "qty_change": False,
         "above_list": False, "attack_style": False},

        {"name": "A04_fast_qty",         "anchor_share": 0.65, "concession_exp": 0.4,
         "deadline": 6, "stubbornness": 0.0, "bid_noise": 0.01,
         "non_monotone": False, "subset_lines": False, "qty_change": True,
         "above_list": False, "attack_style": False},

        # --- Cluster B: stubborn / non-monotone (TRAIN) ---
        {"name": "B05_stubborn_low",     "anchor_share": 0.35, "concession_exp": 2.5,
         "deadline": 10, "stubbornness": 0.4, "bid_noise": 0.00,
         "non_monotone": False, "subset_lines": False, "qty_change": False,
         "above_list": False, "attack_style": False},

        {"name": "B06_stubborn_mid",     "anchor_share": 0.50, "concession_exp": 2.0,
         "deadline": 10, "stubbornness": 0.3, "bid_noise": 0.00,
         "non_monotone": False, "subset_lines": False, "qty_change": False,
         "above_list": False, "attack_style": False},

        {"name": "B07_nonmono_noisy",    "anchor_share": 0.55, "concession_exp": 1.5,
         "deadline": 9,  "stubbornness": 0.1, "bid_noise": 0.05,
         "non_monotone": True,  "subset_lines": False, "qty_change": False,
         "above_list": False, "attack_style": False},

        {"name": "B08_stubborn_subset",  "anchor_share": 0.40, "concession_exp": 2.5,
         "deadline": 10, "stubbornness": 0.5, "bid_noise": 0.00,
         "non_monotone": False, "subset_lines": True,  "qty_change": False,
         "above_list": False, "attack_style": False},

        {"name": "B09_nonmono_qty",      "anchor_share": 0.60, "concession_exp": 1.8,
         "deadline": 8,  "stubbornness": 0.2, "bid_noise": 0.03,
         "non_monotone": True,  "subset_lines": False, "qty_change": True,
         "above_list": False, "attack_style": False},

        # --- Cluster C: attacker configs — ENTIRE CLUSTER HELD OUT (TEST) ---
        {"name": "C10_attack_fast",      "anchor_share": 0.40, "concession_exp": 0.5,
         "deadline": 6,  "stubbornness": 0.0, "bid_noise": 0.02,
         "non_monotone": False, "subset_lines": False, "qty_change": False,
         "above_list": False, "attack_style": True},

        {"name": "C11_attack_stubborn",  "anchor_share": 0.35, "concession_exp": 2.5,
         "deadline": None, "stubbornness": 0.4, "bid_noise": 0.00,
         "non_monotone": False, "subset_lines": False, "qty_change": False,
         "above_list": False, "attack_style": True},

        {"name": "C12_attack_nonmono",   "anchor_share": 0.50, "concession_exp": 1.5,
         "deadline": 9,  "stubbornness": 0.1, "bid_noise": 0.04,
         "non_monotone": True,  "subset_lines": False, "qty_change": False,
         "above_list": False, "attack_style": True},

        {"name": "C13_attack_subset",    "anchor_share": 0.45, "concession_exp": 1.0,
         "deadline": 7,  "stubbornness": 0.0, "bid_noise": 0.01,
         "non_monotone": False, "subset_lines": True,  "qty_change": False,
         "above_list": False, "attack_style": True},

        {"name": "C14_attack_qty",       "anchor_share": 0.55, "concession_exp": 2.0,
         "deadline": 8,  "stubbornness": 0.3, "bid_noise": 0.00,
         "non_monotone": False, "subset_lines": False, "qty_change": True,
         "above_list": False, "attack_style": True},

        # --- Cluster D: edge-case configs (TRAIN) ---
        {"name": "D15_above_list",       "anchor_share": 0.90, "concession_exp": 0.3,
         "deadline": 4,  "stubbornness": 0.0, "bid_noise": 0.00,
         "non_monotone": False, "subset_lines": False, "qty_change": False,
         "above_list": True,  "attack_style": False},

        {"name": "D16_very_low_anchor",  "anchor_share": 0.30, "concession_exp": 3.0,
         "deadline": 10, "stubbornness": 0.0, "bid_noise": 0.00,
         "non_monotone": False, "subset_lines": False, "qty_change": False,
         "above_list": False, "attack_style": False},

        {"name": "D17_max_noise",        "anchor_share": 0.65, "concession_exp": 1.0,
         "deadline": 7,  "stubbornness": 0.0, "bid_noise": 0.05,
         "non_monotone": False, "subset_lines": False, "qty_change": False,
         "above_list": False, "attack_style": False},

        {"name": "D18_all_flags",        "anchor_share": 0.55, "concession_exp": 1.5,
         "deadline": 8,  "stubbornness": 0.2, "bid_noise": 0.03,
         "non_monotone": True,  "subset_lines": True,  "qty_change": True,
         "above_list": False, "attack_style": False},

        {"name": "D19_late_long",        "anchor_share": 0.50, "concession_exp": 2.8,
         "deadline": 10, "stubbornness": 0.0, "bid_noise": 0.00,
         "non_monotone": False, "subset_lines": False, "qty_change": False,
         "above_list": False, "attack_style": False},
    ]
    assert len(configs) == 20, "build_family() must return exactly 20 configs"
    names = {c["name"] for c in configs}
    assert len(names) == 20, "all config names must be unique"
    return configs


def with_attack(cfg, on):
    """Copy of cfg with attack_style forced to `on`; name gets +atk / -atk suffix."""
    c = dict(cfg, attack_style=on)
    base = cfg["name"].split("+")[0].split("-atk")[0]
    c["name"] = base + ("+atk" if on else "")
    return c


def family_variants():
    """All 40 variants: every config with attack off and with attack on."""
    return [with_attack(c, a) for c in build_family() for a in (False, True)]


def make_buyers(configs):
    """{name: ParamBuyer subclass} for the given configs (kit BUYERS format)."""
    out = {}
    for cfg in configs:
        def _make(c=cfg):
            class _B(ParamBuyer):
                feasible = 0.85
                zone = (0.15, 0.85)
                anchor = (min(c["anchor_share"], 0.95) * 0.9, min(c["anchor_share"], 0.95))
                deadline = c["deadline"] or 10
                exponent = c["concession_exp"]
                stubborn = c["stubbornness"]

                def __init__(self, scenario, store, rng):
                    super().__init__(dict(scenario, _cfg=c), store, rng)
            _B.__name__ = _B.__qualname__ = c["name"]
            return _B
        out[cfg["name"]] = _make()
    return out


# FAMILY_ONLY=<name> restricts BUYERS to one config (used by the per-config table).
# FAMILY_ATTACK=on forces attack style on for all 20; =both runs all 40 variants. FAMILY_SPLIT=TRAIN|TEST filters.
_only = os.environ.get("FAMILY_ONLY")
_cfgs = family_variants() if os.environ.get("FAMILY_ATTACK") == "both" else build_family()
if os.environ.get("FAMILY_ATTACK") == "on":
    _cfgs = [with_attack(c, True) for c in build_family()]
_split = os.environ.get("FAMILY_SPLIT")           # TRAIN | TEST (arena/family_split.json)
if _split:
    import json
    _names = set(json.loads((Path(__file__).resolve().parent / "family_split.json").read_text())["split"][_split])
    _cfgs = [c for c in _cfgs if c["name"].split("+")[0] in _names]
if _only:
    _cfgs = [c for c in _cfgs if c["name"] == _only]
BUYERS = make_buyers(_cfgs)
