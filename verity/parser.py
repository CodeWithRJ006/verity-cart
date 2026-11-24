# verity/parser.py — Robust message parser for buyer inputs. Python 3.9 stdlib only.
from __future__ import annotations
from dataclasses import dataclass
import math
from typing import Any, Dict, List, Optional, Set


@dataclass
class ParsedMsg:
    type: str
    round: int
    lines: Optional[List[Dict[str, Any]]]
    flags: List[str]

    @property
    def items(self) -> Optional[List[Dict[str, Any]]]:
        """Backward-compatible alias for lines."""
        return self.lines


def parse(msg: Any, store: Optional[Dict[str, Any]] = None) -> ParsedMsg:
    """Parse incoming buyer message safely without raising exceptions.

    Invariants:
    - Never raises on any input (arbitrary types, garbage, missing keys).
    - Free text is completely ignored.
    - Duplicate SKUs flag 'dup_sku' and are never summed or merged.
    - Missing/invalid round defaults to 1 with 'missing_round' flag.
    - Valid line entries require:
        - sku: non-empty str (and present in store if store is provided)
        - qty: int, not bool, >= 1
        - unit_price (if present): int | float, not bool, finite, >= 0
    """
    flags: List[str] = []

    if not isinstance(msg, dict):
        return ParsedMsg(type="malformed", round=1, lines=None, flags=["not_a_dict"])

    # 1. Message Type
    raw_type = msg.get("type")
    if not isinstance(raw_type, str):
        flags.append("bad_type")
        msg_type = "unknown"
    else:
        msg_type = raw_type

    # 2. Round Number
    raw_round = msg.get("round")
    if not isinstance(raw_round, int) or isinstance(raw_round, bool) or raw_round < 1:
        flags.append("missing_round")
        round_num = 1
    else:
        round_num = raw_round

    # 3. Items / Lines
    raw_items = msg.get("items")
    if raw_items is None:
        lines: Optional[List[Dict[str, Any]]] = None
    elif not isinstance(raw_items, list):
        flags.append("bad_items")
        lines = None
    else:
        valid_lines: List[Dict[str, Any]] = []
        seen_skus: Set[str] = set()

        for it in raw_items:
            if not isinstance(it, dict):
                flags.append("item_not_dict")
                continue

            sku = it.get("sku")
            if not isinstance(sku, str) or not sku.strip():
                flags.append("bad_sku")
                continue

            if store is not None and sku not in store:
                flags.append(f"unknown_sku:{sku}")
                continue

            if sku in seen_skus:
                flags.append("dup_sku")
                continue
            seen_skus.add(sku)

            qty = it.get("qty")
            if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
                flags.append(f"bad_qty:{sku}")
                continue

            line_entry: Dict[str, Any] = {"sku": sku, "qty": qty}

            if "unit_price" in it:
                price = it.get("unit_price")
                if (
                    isinstance(price, bool)
                    or not isinstance(price, (int, float))
                    or not math.isfinite(price)
                    or price < 0
                ):
                    flags.append(f"bad_price:{sku}")
                    continue
                line_entry["unit_price"] = price

            valid_lines.append(line_entry)

        lines = valid_lines

    return ParsedMsg(type=msg_type, round=round_num, lines=lines, flags=flags)
