"""EnvDouble: Dev2's own policy envelope for tests (no import of verity.envelope).

Invariant: floor(sku) reproduces kit/harness.floor_price's float expression
and operation order exactly (including the final math.ceil).
"""
import copy
import math


class EnvDouble:
    def __init__(self, store, policy):
        self._store = copy.deepcopy(store)
        self._policy = copy.deepcopy(policy)

    def floor(self, sku):
        row = self._store[sku]
        margin_floor = row["cost"] / (1 - self._policy["min_margin"][row["category"]])
        discount_floor = row["price"] * (1 - self._policy["max_discount"])
        return math.ceil(max(margin_floor, discount_floor))

    def list_price(self, sku):
        return self._store[sku]["price"]

    def stock(self, sku):
        return self._store[sku]["stock"]
