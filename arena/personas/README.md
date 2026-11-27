# LLM personas (stage S5)

Five personas (anchorer, competitor, injector, pressurer, terse) play the buyer through `llm_buyer.py` (stdlib `urllib`
only). Prompts: `prompts/*.txt` (base + one delta, schema from the kit README). Reported **separately** from the official run.

Dry run (no network, fake provider): `python arena/personas/run_personas.py --seller seller_spike.py --dry-run`

Real run (cmd):
```
set ARENA_PROVIDER=gemini
set GEMINI_API_KEY=<key from Google AI Studio>
set ARENA_DAILY_QUOTA=1000
python arena\personas\run_personas.py --seller seller_spike.py
```
Other providers: `openrouter` (`OPENROUTER_API_KEY`, `ARENA_MODEL=<free model>`), `ollama` (local, `ARENA_MODEL=llama3.1`).
Throttle: `ARENA_MIN_INTERVAL` seconds between calls (default 4). On a quota stop, re-run the same command later: every call is
cached in `results/personas_cache/`, so nothing is lost. Raw model output of every call: `results/personas_raw.jsonl`.
Budget: ~7 calls per negotiation, 150 negotiations per seller, so roughly 1000 calls per seller per run.
Guards: the buyer never accepts or bids above its private limit (adapter clamps, logged); malformed model output is sent to the
seller as a plain `message` (a robustness test) and counted. If a persona behaves outside the 20-config family, add a config.
