# Fixture Specification Questions for Dev2 and Dev3

During the expansion of `tests/contract/view_cases.json`, the following edge cases were identified where the specification across Handbook §3.1, Handbook §1.1 Amendment A, and `verity/contracts.py` allows multiple valid interpretations. Per project instructions, these cases are left out of `view_cases.json` pending alignment with Dev2 (@Asmi611) and Dev3 (@akshata-malik).

---

### Question 1: Mid-Negotiation Inventory Drop for a Basket SKU

* **Scenario**: On Turn 1, the buyer requests SKU `S001` with qty 2. Stock is 10, so basket is initialized to `{S001: 2}`.
  Between Turn 1 and Turn 2, stock in the physical store drops to 0 (or drops below 2).
* **Ambiguity**:
  1. Does `View.L` and `View.F` dynamically recompute based on currently available inventory (excluding depleted items), or do `L` and `F` remain fixed to the initial Turn 1 basket throughout the session?
     * Note in `contracts.py:7`: `Basket = Dict[str, int] # sku -> sellable qty, fixed on turn 1 (stock re-read at every decision)`.
  2. If the buyer subsequently submits a priced bid matching the Turn 1 basket `{S001: 2}`, should `bid_complete` be `True` (since it matches the Turn 1 basket) while `bid_valid_as_made` is `False` (since stock is 0), or should `bid_complete` also be `False`?
* **Recommendation**: Keep `basket`, `L`, and `F` fixed to Turn 1 sellable quantities for stable negotiation bounds; reflect the out-of-stock condition strictly through `bid_valid_as_made = False` (enforced by `gate.bid_valid_as_made` checking current stock).

---

### Question 2: Round Gaps and Missing Round Stamping

* **Scenario**:
  - The incoming message skips rounds (e.g. Turn 1 sends `round: 1`, then next message sends `round: 3`).
  - Or the incoming message omits `"round"` or passes `round: None`.
* **Ambiguity**:
  1. Handbook §3.1 states `View.round` uses `msg["round"]` when valid, else falls back to internal counter. If an incoming message specifies `round: 3` after `round: 1`, does `View.round` report `3`, and does the internal counter sync to `3` or increment by 1 (`2`)?
  2. If the round field is invalid (e.g. negative or a string), should the internal turn counter take precedence?
* **Recommendation**: If `msg.get("round")` is an `int >= 1`, use it for `View.round` and synchronize internal `turn = msg["round"]`. Otherwise, advance internal `turn += 1` and use internal `turn`.
