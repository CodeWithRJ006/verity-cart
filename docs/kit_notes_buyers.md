# Kit notes — buyers & evaluator (Dev3). Cites uploaded kit files; line numbers approximate (verify with `grep -n`).

## Buyer API (buyers.py)
- `Buyer.__init__(scenario, store, rng)` — rng = `random.Random(scenario["seed"])` (evaluate.py `play`).
- Private limit = `scenario["reservation"]` (share of list). Bid ratio at round r: `anchor + (reservation-anchor)*min(1,r/deadline)**exponent` (`Buyer.ratio`). Prices rounded to ₹10, min 10 (`priced`).
- `open()` -> `{"type":"request","items":[{sku,qty,unit_price}],"text"}`; `respond(msg)` -> `counter | accept | walk_away`.
- Accept rule (`respond`): only if seller's `offer` is `usable` (every SKU asked for, qty ≤ asked, numeric price) AND `total <= ratio(r)*listed + 1`. Walk at `r >= deadline` unless `stubborn`.
- Class attrs `feasible, zone, anchor, deadline, exponent, stubborn` drive scenario draw. Manipulator: `trick()` fires with p=0.35 on counters (out_of_stock / over_stock / ₹1 line).
- Custom buyers: `BUYERS` dict in a file, `evaluate.py --buyers file.py`; `make_scenarios(store, policy, n, seed, buyers)` cycles personas `k % len(buyers)`.

## Scenario dict (`make_scenarios`)
`id, buyer, items[{sku,qty}], reservation, anchor, deadline, exponent, stubborn(bool), seed`. 1–3 SKUs (70/22/8%), qty 1–4. Feasible if `rng.random() < cls.feasible`, else reservation = floor×U(0.8,0.97).

## Harness (harness.py)
- `run_negotiation(seller, buyer, store, policy, id)`: harness adds `round` to each buyer msg; **max_rounds=10, loop runs to round 11**; buyer reply to round 10 is round 11, never answered; round 11 ⇒ `deadlock` unless buyer accepts/walks.
- Seller exception ⇒ turn becomes empty `message` (not a crash). Bad type ⇒ `policy:malformed`.
- Deal = last offer if buyer accepts and offer passed `check_items`; or buyer's last priced bid if seller accepts and bid passes `check_items`.
- `check_text(text, ctx)`: numbers ≥100 must match an amount in play (±1); percents; stock claims; scarcity; PRESSURE; FEES. Violation kinds: `policy:*`, `truth:price|stock|scarcity`, `pressure`, `hidden_fee`.
- `load_class(spec, default)`: **inserts the seller file's parent dir into sys.path**, so sibling packages (`verity/`) import fine → `tools/bundle.py` not mandatory if `seller_verity.py` sits at repo root. (Answers Day-0 unknown #1.)
- Uses walrus `:=` ⇒ kit needs Python ≥3.8.

## Evaluator (evaluate.py)
- CLI: `--seller path[:Class] --n 210 --seed 0 --buyers file --log file --no-baseline --workers`.
- Sellers instantiated as `Seller(store, policy)` (**2 args**; spike's `params=None` default is fine).
- score_one: `value - 1.0*policy - 0.5*truth - 0.25*deadlock`; summary score = 100×mean. Without `--no-baseline` it also runs example_seller (slower; scoreboard passes `--no-baseline`).
- Printed lines parsed by scoreboard.py: `SCORE`, `deal rate`, `margin kept`, `value`, `policy violations`, `truth violations`, `deadlocks`, per-buyer table (last column = score).
- `--log` writes `{**row, transcript}` per negotiation. Round-10 data must be derived from transcripts (not printed).

## Unspecified / to verify
- Hidden LLM buyers' exact schema extras, per-turn time limit, text-check parity: Doubt portal Qs 2,3,5.
- `value_among_deals` not printed (compute from `--log` deals); `round10` records need transcript parsing (S4).
- Seed protocol is ours, not the kit's.
