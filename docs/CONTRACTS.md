# VERITY-CART Contracts Specification

This document defines the frozen contract types declared in `verity/contracts.py`.

Any change to `verity/contracts.py` or this document requires the **contract-change protocol** (Handbook §3.2: PR labelled `contract-change` with approvals from all 3 developers).

---

## 1. Type Aliases

- `Basket = Dict[str, int]`: Map of SKU string to sellable integer quantity ($q \ge 1$). Fixed on turn 1 from the requested items that are in-stock and capped at stock.
- `Prices = Dict[str, int]`: Map of SKU string to integer-rupee unit price ($p \in [\text{floor}, \text{list\_price}]$).

---

## 2. Enums

### `RepairStatus(str, Enum)`
Status returned by `repair.allocate_exact` or `repair.allocate_at_most`:
- `EXACT`: The line prices sum exactly to the requested total: $\sum q_i \cdot p_i = \text{total}$.
- `AT_MOST`: The line prices sum to $\le \text{target}$, as close as possible without exceeding the target.
- `AGGREGATE_INFEASIBLE`: The requested total is strictly outside the aggregate feasible range $[F, L]$.
- `INTEGER_INFEASIBLE`: The total is within $[F, L]$, but no integer rupee assignment satisfying floor/list bounds can achieve the exact sum.
- `INVALID_INPUT`: Baskets or envelopes are malformed or invalid.

### `Action(str, Enum)`
High-level decision action emitted by `strategy.decide(view)`:
- `ACCEPT`: Accept the buyer's items exactly as made. The orchestrator must re-verify validity with `gate.bid_valid_as_made` before issuing an acceptance.
- `COUNTER`: Propose a counter-offer with aggregate rupee amount `total`, to be converted to line items by the repair module using `mode`.
- `WALK_AWAY`: Terminate the negotiation cleanly.

### `Mode(str, Enum)`
Allocation mode instructed by `Decision`:
- `EXACT`: Echo a specific aggregate price (used by `repair.allocate_exact`).
- `AT_MOST`: Target an upper bound on aggregate price (used by `repair.allocate_at_most`).

---

## 3. Dataclasses

### `RepairResult` (Frozen)
Output of repair line allocation:
- `status: RepairStatus`: Outcome status.
- `prices: Optional[Prices]`: Map of `sku -> unit_price` (integer rupees), or `None` if infeasible.
- `total: Optional[int]`: Actual sum $\sum q_i \cdot p_i$ (integer rupees), or `None` if infeasible.

### `Decision` (Frozen)
The pure economic decision emitted by `strategy.Strategy.decide(view)`:
- `action: Action`: `ACCEPT`, `COUNTER`, or `WALK_AWAY`.
- `total: Optional[int]`: Target aggregate price in integer rupees. Must be within $[F, L]$ for `Action.COUNTER`.
- `mode: Mode`: `Mode.AT_MOST` (default) or `Mode.EXACT`.
- `reason: str`: Diagnostic machine code for internal logging (never transmitted to buyer).
- `ratio: Optional[float]`: Share-of-list ratio intended by the strategy; stored by state as `last_offer_ratio`.

### `View` (Mutable Dataclass)
The sanitized state representation passed to `strategy.decide(view)`. **Free text is completely excluded.**
- `round: int`: Current negotiation turn ($1 \dots 10$).
- `msg_type: str`: The buyer message type (`"request"`, `"counter"`, `"accept"`, `"walk_away"`, etc.).
- `L: int`: Total basket list price in integer rupees: $\sum q_i \cdot \text{list\_price}_i$.
- `F: int`: Total basket floor price in integer rupees: $\sum q_i \cdot \text{floor}_i$.
- `bids: List[float]`: History of complete, usable buyer bid ratios ($\frac{\sum q_i \cdot p_i}{L}$).
- `bid_complete: bool`: `True` iff current buyer message has priced lines matching the basket SKUs and quantities exactly.
- `bid_valid_as_made: bool`: `True` iff all buyer lines are within policy ($p_i \in [\text{floor}_i, \text{list}_i]$) and stock limits.
- `last_offer_ratio: Optional[float]`: Seller's previously offered ratio $\frac{\text{total}}{L}$, or `None` on turn 1.

---

## 4. Module Boundary Signatures

| Module | Signature | Owner |
|---|---|---|
| `parser` | `parse(msg: dict) -> ParsedMsg` | Dev1 |
| `envelope` | `Envelope(store, policy): .floor(sku), .list_price(sku), .stock(sku)` | Dev1 |
| `state` | `NegotiationState: .begin(msg), .view(parsed) -> View, .remember(offer)` | Dev1 |
| `strategy` | `Strategy(cfg).decide(view: View) -> Decision` | Dev2 (Dev1 uses `strategy_stub`) |
| `repair` | `allocate_exact(basket, env, total) -> RepairResult`, `allocate_at_most(basket, env, target) -> RepairResult` | Dev2 (Dev1 uses `repair_stub`) |
| `gate` | `check_outgoing(msg: dict, basket, env) -> (bool, List[str])`, `bid_valid_as_made(items, basket, env) -> bool` | Dev1 |
| `truth` | `check(text: str, ctx_dict: dict) -> List[str]` | Dev1 |
| `renderer` | `render(kind: str, items: list, total: int, dropped: list) -> str` | Dev1 |
