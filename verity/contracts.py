# verity/contracts.py — FROZEN after Day 0. Python 3.9, stdlib only.
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

Basket = Dict[str, int]   # sku -> sellable qty, fixed on turn 1 (stock re-read at every decision)
Prices = Dict[str, int]   # sku -> integer-rupee unit price

class RepairStatus(str, Enum):
    EXACT = "EXACT"                          # sum(q*p) == requested total
    AT_MOST = "AT_MOST"                      # seller target: sum <= target, as close as possible
    AGGREGATE_INFEASIBLE = "AGGREGATE_INFEASIBLE"   # total outside [F, L]
    INTEGER_INFEASIBLE = "INTEGER_INFEASIBLE"       # inside [F, L] but no integer split
    INVALID_INPUT = "INVALID_INPUT"

@dataclass(frozen=True)
class RepairResult:
    status: RepairStatus
    prices: Optional[Prices] = None
    total: Optional[int] = None

class Action(str, Enum):
    ACCEPT = "ACCEPT"        # accept buyer's items exactly as made (orchestrator re-verifies with gate)
    COUNTER = "COUNTER"      # offer `total`, allocated per `mode`
    WALK_AWAY = "WALK_AWAY"

class Mode(str, Enum):
    EXACT = "EXACT"          # echo buyer's total (repair.allocate_exact)
    AT_MOST = "AT_MOST"      # seller target (repair.allocate_at_most)

@dataclass(frozen=True)
class Decision:
    action: Action
    total: Optional[int] = None
    mode: Mode = Mode.AT_MOST
    reason: str = ""         # machine code for logs; NEVER sent to the buyer
    ratio: Optional[float] = None   # offer share-of-list the strategy intends; state stores it as last_offer_ratio

@dataclass
class View:                  # everything strategy may see. NO free text. Built by state.py.
    round: int
    msg_type: str            # "request" | "counter" | "accept" | "walk_away" | ...
    L: int                   # basket list total (rupees)
    F: int                   # basket floor total (rupees)
    bids: List[float]        # history of usable complete bid ratios (share of list), incl. current if usable
    bid_complete: bool       # current message is a complete priced bid for exactly the basket
    bid_valid_as_made: bool  # gate says buyer's items can be accepted exactly as made
    last_offer_ratio: Optional[float]   # our previous offered ratio, None on turn 1
