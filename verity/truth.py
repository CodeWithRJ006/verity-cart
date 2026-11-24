# verity/truth.py — TEMPORARY I0 placeholder. Replaced by Dev1 in S4.
import re
from typing import Any, Dict, List

# Basic checks to avoid forbidden terms
PRESSURE = re.compile(r"today only|offer (?:ends|expires)|hurry|last chance|act fast", re.I)
FEES = re.compile(r"fee|charge|tax|gst", re.I)


def check(text: str, ctx: Dict[str, Any] = None) -> List[str]:
    violations = []
    if not isinstance(text, str) or not text:
        return violations
    if PRESSURE.search(text):
        violations.append("pressure")
    if FEES.search(text):
        violations.append("hidden_fee")
    return violations
