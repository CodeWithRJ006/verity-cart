# verity/envelope.py — Price and stock bounds per SKU. Python 3.9 stdlib only.
from __future__ import annotations

import copy
import math
from typing import Any, Dict, Optional


class Envelope:
    """Computes price and inventory envelopes for catalog SKUs.

    Invariants:
    - Never mutates caller's store or policy dicts (deep-copies at init).
    - floor(sku) == kit/harness.floor_price(store[sku], policy) for all 100 SKUs.
    - All money values returned are integer rupees.
    """

    def __init__(self, store: Dict[str, Any], policy: Dict[str, Any]):
        self._live_store = store
        self._store = copy.deepcopy(store)
        self._policy = copy.deepcopy(policy)
        self._floors: Dict[str, int] = {}
        self._list_prices: Dict[str, int] = {}
        for sku, r in self._store.items():
            cost = r["cost"]
            price = r["price"]
            cat = r["category"]
            margin = self._policy["min_margin"][cat]
            discount = self._policy["max_discount"]
            mf = cost / (1 - margin)
            df = price * (1 - discount)
            self._floors[sku] = math.ceil(max(mf, df))
            self._list_prices[sku] = int(price)

    def floor(self, sku: str) -> int:
        """Lowest unit price policy allows for this product in integer rupees."""
        if sku not in self._floors:
            raise KeyError(f"Unknown SKU: {sku!r}")
        return self._floors[sku]

    def list_price(self, sku: str) -> int:
        """Catalog list price in integer rupees."""
        if sku not in self._list_prices:
            raise KeyError(f"Unknown SKU: {sku!r}")
        return self._list_prices[sku]

    def stock(self, sku: str, current_store: Optional[Dict[str, Any]] = None) -> int:
        """Available stock units. Re-reads from current_store or live store."""
        source = current_store if current_store is not None else getattr(self, "_live_store", self._store)
        if sku not in source:
            raise KeyError(f"Unknown SKU: {sku!r}")
        return int(source[sku]["stock"])
