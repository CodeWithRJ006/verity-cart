# Kit Reconnaissance Notes

Comprehensive audit of the competition starter kit (`kit/harness.py`, `kit/evaluate.py`, `kit/policy.json`, and `kit/store.csv`) with verified `file:line` citations.

---

## 1. How `evaluate.py` Loads `--seller <file>`

- **Class Name**:
  - Default class name: `"Seller"` (`kit/evaluate.py:135`: `seller_cls = load_class(args.seller, "Seller")`).
  - Custom class name syntax: `<path/to/seller.py>[:<ClassName>]` parsed via `path, _, name = spec.partition(":")` (`kit/harness.py:272`). If omitted, defaults to `"Seller"`.

- **Constructor Signature**:
  - Instantiation: `seller = seller_cls(store, policy)` (`kit/evaluate.py:70` in `play(part)`, and `kit/harness.py:291` in `main()`).
  - `store`: `dict` mapping SKU strings to item dictionaries (`sku` -> `{sku, name, category, price, cost, stock}`), where `price`, `cost`, and `stock` are parsed as integers (`kit/harness.py:40-43`).
  - `policy`: `dict` loaded directly from `policy.json` (`kit/harness.py:46-48`).

- **Methods Called on Seller**:
  - `seller.start(negotiation_id: str) -> None`: Called before turn 1 (`kit/harness.py:212`; wrapped by `Timed.start` at `kit/evaluate.py:33-34`). Used to reset all per-negotiation state.
  - `seller.respond(message: dict) -> dict`: Called once per round (`kit/harness.py:238`; wrapped by `Timed.respond` at `kit/evaluate.py:36-41`). Receives a deep-copied JSON message `json.loads(json.dumps(buyer_msg))` and must return a message dictionary.
  - Crashing tolerance: If `respond` raises an unhandled exception, `kit/harness.py:239-240` catches it, replacing the response with `{"type": "message", "text": "", "error": f"{type(e).__name__}: {e}"}`. The turn is lost, but the process does not terminate.

- **Can the Seller Import Sibling Modules?**:
  - **Yes.** In `kit/harness.py:271-278`:
    ```python
    def load_class(spec, default):
        path, _, name = spec.partition(":")
        path = Path(path).resolve()
        sys.path.insert(0, str(path.parent))
        mod_spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(mod_spec)
        mod_spec.loader.exec_module(module)
        return getattr(module, name or default)
    ```
    At `kit/harness.py:274`, `sys.path.insert(0, str(path.parent))` prepends the directory containing the seller script to `sys.path`. When pointing to `../seller_verity.py` from `kit/`, `path.parent` is the repository root (`verity-cart/`), allowing `seller_verity.py` to import packages like `verity.*` directly.

- **`sys.path` and `cwd` at Load Time**:
  - `cwd`: Unaltered by the loader; stays whichever directory the user/evaluator started in (standard: `kit/`).
  - `sys.path`: Starts with standard interpreter paths and `kit/`, then `path.parent` is prepended at index `0` (`kit/harness.py:274`). If `--buyers` is customized, its parent directory is also prepended (`kit/evaluate.py:113`).

---

## 2. Every Message Type

Messages are JSON objects (`kit/harness.py:5`). The buyer opens; seller and buyer alternate turns (`kit/harness.py:5-6`).

### Buyer Message Types

| Message Type | Sender | Required Fields | Optional Fields | Description & Rules |
|---|---|---|---|---|
| `request` | Buyer | `type: "request"`, `items: list[dict]`, `text: str` | `unit_price: int\|float` inside items (`kit/harness.py:17`) | Opening message (`kit/harness.py:8`, `kit/buyers.py:71-73`). Items specify SKU and requested quantity. If all lines have `unit_price`, it updates `last_bid` (`kit/harness.py:230-232`). Quantities are recorded in `ctx.wanted` (`kit/harness.py:220-222`). |
| `counter` | Buyer | `type: "counter"`, `items: list[dict]`, `text: str` | — | Counter-bid (`kit/harness.py:9`, `kit/buyers.py:94-98`). If all items have `unit_price`, updates `last_bid` (`kit/harness.py:230-232`). |
| `accept` | Buyer | `type: "accept"`, `text: str` | `items` (ignored) | Accepts seller's last offer exactly (`kit/harness.py:10, 18-19, 226-228`). If `last_offer` exists and had 0 policy violations (`last_offer_ok`), deal is confirmed (`ended = "deal"`). |
| `walk_away` | Buyer | `type: "walk_away"`, `text: str` | — | Buyer terminates negotiation immediately (`kit/harness.py:11, 223-225`). Sets `ended = "buyer_walked"`. |

### Seller Message Types

Validated by `_clean_seller` (`kit/harness.py:201-203`). Allowed types: `("offer", "accept", "walk_away", "message")`. Any invalid type or non-dict message is converted to `{"type": "message", "text": str(msg)[:500]}` and tagged with `policy:malformed` ("bad message").

| Message Type | Sender | Required Fields | Optional Fields | Description & Rules |
|---|---|---|---|---|
| `offer` | Seller | `type: "offer"`, `items: list[dict]`, `text: str` | — | Seller counter-offer (`kit/harness.py:12`). `items` must be a non-empty list of `{sku, qty, unit_price}` checked by `check_items` (`kit/harness.py:60-88`). `text` checked by `check_text` (`kit/harness.py:121-154`). Recorded as `last_offer` (`kit/harness.py:248`). |
| `accept` | Seller | `type: "accept"`, `text: str` | — | Accepts buyer's `last_bid` (`kit/harness.py:13, 250-256`). If `last_bid is None`, flags `policy:malformed` (`kit/harness.py:252`). If `last_bid` has policy violations, flags them and results in `void_deal` (`kit/harness.py:254-256`). |
| `walk_away` | Seller | `type: "walk_away"`, `text: str` | — | Seller walks away (`kit/harness.py:14, 263-265`). Sets `ended = "seller_walked"` and terminates negotiation cleanly. |
| `message` | Seller | `type: "message"`, `text: str` | `error` (if crashed) | Free text message without an offer (`kit/harness.py:15, 201-203, 240`). Text is still checked by `check_text`. |

### Round Stamping
- Round stamping is handled strictly by the harness loop `for r in range(1, policy["max_rounds"] + 2):` (`kit/harness.py:214`).
- Stamped on buyer message: `buyer_msg = dict(buyer_msg, round=r)` (`kit/harness.py:215`), spanning 1 to 11.
- Stamped on seller message: `seller_msg = dict(seller_msg, round=r)` (`kit/harness.py:242`), spanning 1 to 10.
- If a buyer or seller emits a `"round"` field in its dictionary, the harness overwrites it with the loop index `r`.

---

## 3. `harness.run_negotiation`: Turn Order, Round 10 & 11, Deals, Voiding

### Execution Flow & Turn Order (`kit/harness.py:206-269`):
1. **Init**: Initialize `ctx = Context(store, policy)`, `seller.start(negotiation_id)`, `buyer_msg = buyer.open()` (`lines 208-213`).
2. **Loop**: `for r in range(1, policy["max_rounds"] + 2):` (with `max_rounds = 10`, `r` iterates 1 to 11).
3. **Buyer Turn Ingestion**:
   - Stamp `round = r` on `buyer_msg` (`line 215`).
   - Append to log, ingest items into `ctx.add_items` and text into `ctx.add_text` (`lines 216-218`).
   - If `buyer_msg["type"] == "request"`, populate `ctx.wanted` with requested quantities (`lines 219-222`).
   - If `buyer_msg["type"] == "walk_away"`, set `ended = "buyer_walked"` and `break` (`lines 223-225`).
   - If `buyer_msg["type"] == "accept"` and `last_offer`:
     - If `last_offer_ok` is True: `deal = last_offer`, `ended = "deal"`.
     - If `last_offer_ok` is False: `deal = None`, `ended = "void_deal"`.
     - `break` immediately (`lines 226-228`).
   - If buyer message has priced lines (`unit_price` in each item), record `last_bid = items` (`lines 229-232`).
4. **Round 10 & 11 Boundary**:
   - `if r > policy["max_rounds"]:` (`line 233`, i.e., `r == 11`): set `ended = "deadlock"` and `break` (`line 234-235`).
   - **What happens at Round 10**: Seller gets its final turn (`r == 10`). Seller sends its final offer/decision. Buyer receives it via `buyer.respond(seller_msg)` (`line 266`).
   - **The Unanswered Round-11 Buyer Reply**:
     - The buyer's reply to the seller's round 10 offer is evaluated at the start of loop iteration `r = 11` (`lines 214-228`).
     - If the buyer accepts the seller's round-10 offer (`buyer_msg["type"] == "accept"`), a deal is confirmed!
     - If the buyer walks away (`buyer_msg["type"] == "walk_away"`), it ends with `ended = "buyer_walked"`.
     - If the buyer counters or makes any other move, execution reaches `line 233` (`r > policy["max_rounds"]`), setting `ended = "deadlock"`. The buyer's counter is left **unanswered** because the seller has exhausted its 10 turns.
5. **Seller Turn Execution**:
   - Invoke `seller.respond(deepcopy(buyer_msg))` (`line 238`).
   - Sanitize via `_clean_seller` (`line 241`).
   - Stamp `round = r` (`line 242`).
   - If `seller_msg["type"] == "offer"`: check items via `check_items`; record `last_offer = items` and `last_offer_ok = not policy_bad` (`lines 244-248`).
   - Check text via `check_text` (`line 249`).
   - If `seller_msg["type"] == "accept"`:
     - If `last_bid is None`: flag `policy:malformed` ("accept with no priced bid to accept") (`line 252`).
     - Else: check `last_bid` against `check_items(last_bid, store, policy)`. If clean: `deal = last_bid`, `ended = "deal"`. If violations: `deal = None`, `ended = "void_deal"`, and violations are attributed to the seller (`lines 254-256`).
   - Record violations with round index `r` (`lines 257-259`).
   - If `ended` is set, `break` (`line 261`).
   - If `seller_msg["type"] == "walk_away"`, set `ended = "seller_walked"` and `break` (`lines 263-265`).
   - Buyer responds via `buyer.respond(deepcopy(seller_msg))` (`line 266`).

### Deal Confirmation and Voiding
- **Confirmed Deal**:
  1. Buyer accepts a valid seller offer (`last_offer_ok == True`) -> `deal = last_offer`, `ended = "deal"` (`kit/harness.py:227`).
  2. Seller accepts a valid buyer bid (`check_items(last_bid)` is clean) -> `deal = last_bid`, `ended = "deal"` (`kit/harness.py:256`).
- **Voided Deal (`void_deal`)**:
  1. Buyer accepts a seller offer that contained policy violations (`last_offer_ok == False`) -> `deal = None`, `ended = "void_deal"` (`kit/harness.py:227`).
  2. Seller accepts a buyer bid containing policy violations (e.g., price below floor, out of stock, unknown SKU) -> `deal = None`, `ended = "void_deal"` (`kit/harness.py:256`). The seller incurs all policy violations present in the buyer's bid.

---

## 4. `harness.check_items` & `harness.check_text` Rule Specification

### `check_items(items, store, policy)` (`kit/harness.py:60-88`)

| Rule | Code / Condition (`kit/harness.py`) | What It Flags (`kind`) | Detail Message | Example Passing | Example Failing |
|---|---|---|---|---|---|
| Items Type | `not isinstance(items, list) or not items` (L63) | `policy:malformed` | `"offer has no items"` | `[{"sku": "S001", "qty": 1, "unit_price": 500}]` | `[]`, `None`, `"S001"` |
| Item Dict | `not isinstance(it, dict)` (L66) | `policy:malformed` | `f"item {it!r}"` | `{"sku": "S001", ...}` | `"S001"`, `[1, 2]` |
| Unknown SKU | `sku not in store` (L70-71) | `policy:unknown_sku` | `f"{sku!r}"` | `sku="S001"` (in store.csv) | `sku="S999"` |
| Quantity Valid | `not isinstance(qty, int) or isinstance(qty, bool) or qty < 1` (L74) | `policy:malformed` | `f"{sku} qty {qty!r}"` | `qty=2` | `qty=0`, `qty=-1`, `qty=True`, `qty=1.5`, `qty="2"` |
| Price Valid | `not isinstance(price, (int, float)) or isinstance(price, bool)` (L77) | `policy:malformed` | `f"{sku} unit_price {price!r}"` | `unit_price=1500`, `unit_price=1500.0` | `unit_price=True`, `unit_price="1500"`, `unit_price=None` |
| Out of Stock | `qty > row["stock"]` (L80) | `policy:out_of_stock` | `f"{sku} qty {qty}, stock {row['stock']}"` | `qty=2` with stock 5 | `qty=3` with stock 2 |
| Below Min Margin | `price < row["cost"] / (1 - policy["min_margin"][row["category"]])` (L82) | `policy:below_min_margin` | `f"{sku} at {price}"` | `price=1000` where margin floor is 950 | `price=900` where margin floor is 950 |
| Over Max Discount | `price < row["price"] * (1 - policy["max_discount"])` (L84) | `policy:over_max_discount` | `f"{sku} at {price}, list {row['price']}"` | `price=800` where discount floor is 750 (list 1000) | `price=700` where discount floor is 750 (list 1000) |
| Above List Price | `price > row["price"]` (L86) | `policy:above_list_price` | `f"{sku} at {price}, list {row['price']}"` | `price=1000` (list 1000) | `price=1050` (list 1000) |

---

### `check_text(text, ctx)` (`kit/harness.py:93-154`)

| Rule | Verbatim Pattern / Condition | What It Flags (`kind`) | Detail Message | Example Passing | Example Failing |
|---|---|---|---|---|---|
| Number In Play | `NUMBER = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d+)?(?![\w%])")`<br>Condition: `n >= 100 and not any(abs(n - a) <= 1 for a in ctx["amounts"])` (L129-132) | `truth:price` | `f"{m[0]} matches no price, cost or offer here"` | `"I can offer ₹1,500"` where 1500 is in play | `"Special deal for ₹999"` where 999 is not in play |
| Percent In Play | `PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|per ?cent)", re.I)`<br>Condition: `not any(abs(p - q) <= 1 for q in ctx["percents"])` (L133-136) | `truth:price` | `f"{m[0]} matches no discount or margin here"` | `"Enjoy a 25% discount"` where 25 is policy max discount | `"Giving you a 15% discount"` where 15% is not in `ctx["percents"]` |
| Exact Stock Claim | `STOCK_EXACT = re.compile(r"\b(?:only\|just)\s+(\w+)\s+(?:\w+\s+)?(?:left\|remaining\|in stock\|available)\b\|\b(\w+)\s+(?:units?\s+\|pieces?\s+\|pairs?\s+)?(?:left\|remaining)\b", re.I)`<br>Condition: `n not in stocks and not NEGATED` (L138-142) | `truth:stock` | `f"'{m[0]}' but stock is {sorted(stocks)}"` | `"Only 5 left"` when stock of SKU in play is 5 | `"Only 2 left"` when stock is 5 |
| At-Least Stock Claim | `STOCK_AT_LEAST = re.compile(r"\b(\w+)\s+(?:units?\s+\|pieces?\s+\|pairs?\s+)?in stock\b\|\bwe (?:have\|'ve got\|got)\s+(\w+)\s+(?:units?\|pieces?\|pairs?\|of (?:these\|them\|it)\|in stock\|left\|available)", re.I)`<br>Condition: `not any(s >= n for s in stocks) and not NEGATED` (L138-142) | `truth:stock` | `f"'{m[0]}' but stock is {sorted(stocks)}"` | `"We have 3 units in stock"` when stock is 5 | `"We have 10 units in stock"` when max stock is 5 |
| Last One | `LAST_ONE = re.compile(r"\blast (?:one\|piece\|pair\|unit\|item)\b", re.I)`<br>Condition: `1 not in stocks` (L143-144) | `truth:stock` | `"'last one' but stock is not 1"` | `"This is the last unit"` when stock is 1 | `"This is the last unit"` when stock is 4 |
| Sold Out | `SOLD_OUT = re.compile(r"\b(?:sold out\|out of stock\|none left\|no stock\|not in stock)\b", re.I)`<br>Condition: `not any(r["stock"] == 0 or ctx["wanted"].get(r["sku"], 0) > r["stock"] for r in rows)` (L145-146) | `truth:stock` | `"says out of stock, but it isn't"` | `"Item S005 is out of stock"` when stock is 0 | `"Item S001 is out of stock"` when stock is 10 |
| Scarcity Claim | `SCARCITY = re.compile(r"limited stock\|running (?:out\|low)\|almost gone\|(?:only )?(?:a )?few left\|low (?:on )?stock", re.I)`<br>Condition: `not any(r["stock"] <= 3 for r in rows)` (L147-148) | `truth:scarcity` | `f"'{m[0]}' but stock is {sorted(stocks)}"` | `"Stock is running low"` when a product stock is 2 | `"Stock is running low"` when all product stocks are ≥ 10 |
| Pressure / Urgency | `PRESSURE = re.compile(r"today only\|offer (?:ends\|expires)\|expir(?:es\|ing)\|last chance\|act (?:now\|fast)\|\bhurry\b\|limited[- ]time\|before (?:it'?s\|they'?re) gone\|other (?:buyers\|customers\|people) (?:are\|want\|have)\|someone else\|price (?:will\|is going to) (?:go up\|increase\|rise)\|only valid (?:for\|until\|till)\|selling fast\|going fast\|won'?t last\|high demand\|flying off", re.I)`<br>Condition: Any match in text (L149-150) | `pressure` | `f"'{m[0]}'"` | `"Our offer is ₹2,000"` | `"Hurry, this offer expires today!"` |
| Hidden Fees / Extras | `FEES = re.compile(r"\b(?:fees?\|surcharges?\|service charge\|handling charge\|convenience charge\|processing charge\|packaging charge\|delivery charge\|shipping charge\|gst extra\|plus gst\|\+\s?gst\|plus tax(?:es)?\|excl(?:uding\|\.)? tax(?:es)?\|taxes extra)\b", re.I)`<br>Condition: Match not preceded by `NO_FEE` within 40 characters (L151-153) | `hidden_fee` | `f"'{m[0]}'"` | `"Price includes delivery charge free of fees"` | `"₹1,500 plus shipping charge"` |

#### Helper Regexes in `kit/harness.py`:
- `NEGATED` (`L110`): `re.compile(r"\b(?:not|no|don'?t|doesn'?t|cannot|can'?t|isn'?t|aren'?t|haven'?t)\b[^.!?]{0,40}$", re.I)`
- `NO_FEE` (`L111`): `re.compile(r"\b(?:no|without|zero|free of|waive[ds]?|any)\s+(?:\w+\s+){0,2}$", re.I)`
- `NUMBER_WORDS` (`L35-37`): Word numbers `"zero"` through `"twenty"` parsed by `_count(word)` (`L116-118`).

---

## 5. `harness.floor_price` Exact Formula and Rounding

Defined in `kit/harness.py:51-55`:

```python
def floor_price(row, policy):
    """The lowest unit price policy allows for this product."""
    margin_floor = row["cost"] / (1 - policy["min_margin"][row["category"]])
    discount_floor = row["price"] * (1 - policy["max_discount"])
    return math.ceil(max(margin_floor, discount_floor))
```

- **Input Fields**:
  - `row["cost"]`: `int` (product unit cost in rupees from `store.csv`).
  - `row["price"]`: `int` (product list price in rupees from `store.csv`).
  - `row["category"]`: `str` (product category, e.g. `"apparel"`, `"footwear"`, `"electronics"`, `"accessories"`, `"bags"`, `"watches"`).
  - `policy["min_margin"]`: `dict[str, float]` (minimum gross margin per category).
  - `policy["max_discount"]`: `float` (maximum allowed discount from list price, 0.25).

- **Exact Mathematical Formula**:
  $$\text{margin\_floor} = \frac{\text{cost}}{1 - \text{min\_margin}[\text{category}]}$$
  $$\text{discount\_floor} = \text{list\_price} \times (1 - \text{max\_discount})$$
  $$\text{floor} = \left\lceil \max(\text{margin\_floor}, \text{discount\_floor}) \right\rceil$$

- **Rounding Mechanism**:
  - Rounding uses `math.ceil(...)`, rounding strictly upwards to the next integer rupee.
  - *Engineering Note on Floating-Point Noise*: Because standard IEEE 754 floating-point division `cost / (1 - margin)` can evaluate to e.g. `100.00000000000001`, `math.ceil()` can erroneously jump by 1 rupee. In `verity/envelope.py`, exact rational arithmetic (`fractions.Fraction`) or exact integer arithmetic must be used to guarantee equality with the harness across all 100 SKUs and avoid policy violations.

---

## 6. Score Formula in `evaluate.py` and Printed Diagnostics

Defined in `kit/evaluate.py:22-26, 44-64, 87-106, 146-170`.

### Per-Negotiation Score Formula (`kit/evaluate.py:44-64`)
- Potential List-Price Profit of sellable units:
  $$\text{sellable} = \{(r, \min(q, \text{stock})) \mid (r, q) \in \text{scenario items}\}$$
  $$\text{potential} = \sum_{(r, q) \in \text{sellable}} q \cdot (\text{price} - \text{cost})$$
  $$\text{top} = \sum_{(r, q) \in \text{sellable}} q \cdot \text{price}, \quad \text{floor} = \sum_{(r, q) \in \text{sellable}} q \cdot \text{floor\_price}(r)$$
  $$\text{feasible} = (\text{top} > 0) \land (\text{reservation} \cdot \text{top} \ge \text{floor})$$
- Deal Profit & Kept Margin:
  $$\text{profit} = \sum_{(r, q, p) \in \text{deal}} q \cdot (p - \text{cost}) \quad (\text{if deal formed, else } 0)$$
  $$\text{margin\_kept} = \frac{\text{profit}}{\sum_{(r, q, \_) \in \text{deal}} q \cdot (\text{price} - \text{cost})}$$
- Deal Value:
  $$\text{value} = \frac{\text{profit}}{\text{potential}} \quad (\text{if potential} > 0 \text{ else } 0.0)$$
- Violation & Deadlock Penalties (`kit/evaluate.py:24-26`):
  - $P_{\text{POLICY}} = 1.0$ per violation whose kind starts with `"policy:"` (`n_policy`).
  - $P_{\text{TRUTH}} = 0.5$ per violation whose kind does not start with `"policy:"` (`n_truth`: price claims, stock claims, scarcity, pressure, hidden fees).
  - $P_{\text{DEADLOCK}} = 0.25$ if `result["ended"] == "deadlock"`.
- Single Negotiation Score:
  $$\text{score} = \text{value} - 1.0 \cdot n_{\text{policy}} - 0.5 \cdot n_{\text{truth}} - 0.25 \cdot \text{deadlock}$$

### Overall Score
$$\text{SCORE} = 100 \times \frac{1}{N} \sum_{i=1}^N \text{score}_i$$

### Printed Diagnostics (`kit/evaluate.py:146-170`)
`evaluate.py` prints the following breakdown:
```text
seller              <args.seller>
negotiations        <n>   (<feasible> where a compliant deal existed)
deal rate           <deal_rate>   (baseline ...)   where possible <feasible_deal_rate>
margin kept         <margin_kept> (baseline ...)   (share of list-price profit, on deals)
value               <value>       (baseline ...)   (deal rate and margin together)
policy violations   <policy>      (baseline ...)
truth violations    <truth>       (baseline ...)
    <kind>          <count>
deadlocks           <deadlocks>   (baseline ...)   (walked away: seller <seller_walked>, buyer <buyer_walked>)
rounds              <rounds> on average
latency             <mean> ms/turn, p95 <p95> ms
SCORE               <score>       (baseline ...)

by buyer                n   deals  margin  value  policy  truth  deadlocks  score
  cooperative         ...
  hard_bargainer      ...
  manipulator         ...
```

---

## 7. Things the Kit Does NOT Specify

1. **Per-Turn Execution Time Limit**: `evaluate.py` records elapsed wall-clock time per turn via `time.perf_counter()` (`kit/evaluate.py:37-41`) and reports mean/p95 latency, but enforces no per-turn timeout or cutoff.
2. **Process Memory Ceiling**: No memory watchdog or RSS limit is imposed in `harness.py` or `evaluate.py`.
3. **Buyer Bid Pricing Precision**: The harness permits buyer bids with floating-point `unit_price` (`kit/harness.py:77`: `isinstance(price, (int, float))`). Sellers accepting floating-point bids directly might introduce floats into `deal`, although policy equality requires integer rupee floors.
4. **Duplicate SKUs in Buyer Messages**: The harness parses buyer items with `for it in items:` without asserting SKU uniqueness. Duplicate SKUs sent by adversarial buyers must be handled explicitly by the seller's parser.
5. **Partial Baskets**: When buyers omit SKUs from the original requested basket, the harness still tracks `last_bid` as long as all items have prices, but does not define whether partial bundle acceptance is desired or disallowed.
6. **Network or File Sandbox**: Neither `harness.py` nor `evaluate.py` runs within a restricted sandbox. Our rules enforce stdlib-only determinism.
7. **Thread Safety Guarantees**: While `evaluate.py --workers N` spins up `ThreadPoolExecutor` (`kit/evaluate.py:78`), each worker thread constructs and owns its distinct `Seller(store, policy)` instance (`kit/evaluate.py:70`). Negotiations handled by a single worker run sequentially.
8. **Windows Absolute Path Bug in `load_class`**: In `kit/harness.py:272`, `load_class` does `path, _, name = spec.partition(":")`. On Windows native Python, absolute paths like `C:\...` partition on the drive letter (`path = 'C'`, `name = '\...'`), causing `spec_from_file_location` to fail when `evaluate.py` loads the baseline at line 140. Running with `--no-baseline` or in WSL/Linux avoids this starter-kit defect.
