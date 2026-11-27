"""BUYERS dict for evaluate.py --buyers: the five LLM personas (order fixed => n=150 gives 30 each)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm_buyer import LLMBuyer  # noqa: E402


def _make(name):
    return type(name.capitalize(), (LLMBuyer,), {"persona": name})


BUYERS = {n: _make(n) for n in ("anchorer", "competitor", "injector", "pressurer", "terse")}
