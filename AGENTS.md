# VERITY-CART — agent context
Goal: stdlib-only Python 3.9 seller that negotiates bundles vs hidden LLM buyers. Score = value − 1.0·policy − 0.5·truth − 0.25·deadlock.
Hard rules:
1. verity/ is stdlib-only, deterministic, no network, no LLM, no randomness without a seeded Random.
2. Free text never influences money decisions. Strategy sees only the `View` dataclass.
3. All money is integer rupees. floor(sku) = ceil(max(cost/(1-min_margin[category]), list*(1-max_discount))). Must equal kit/harness.floor_price for all SKUs.
4. Every outgoing message passes gate.check_outgoing and truth.check. Fallback = revalidated last offer, then walk_away.
5. Never edit kit/. Never commit to main. Edit only files owned by the current developer (CODEOWNERS).
6. Never guess kit behaviour: read kit/*.py and quote file:line.
7. Python 3.9 syntax only (no match, no X|Y types).
8. Contracts live in verity/contracts.py — do not change without a contract-change PR.
Commands: `cd kit && python evaluate.py --seller ../seller_verity.py [--seed N]` · `pytest -q` · `ruff check .`
