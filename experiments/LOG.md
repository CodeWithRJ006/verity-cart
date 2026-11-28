# Experiment log (Dev2)

Entries are append-only. Each records hypothesis, switches, seeds, result files, decision.

## 2026-11-26 - Global re-tune of (T, e, slack, g, walk_slack): NOT ADOPTED

**Hypothesis.** The spike curve (T=6, e=0.5) is mis-tuned for the buyer family; a re-tune improves the family without hurting the public bots.

**Method.** Random search (300) + Gaussian refinement (100) on TUNE seeds {1,2,3}, n=210. Objective J = 0.5*mean(public) + 0.5*mean(family TRAIN), J=-inf on any violation. Plateau pick = max J_smooth (k=8). Code sha 8dcaf24, rng seed 0.
Files: experiments/tuning/2026-11-26_8dcaf24_tune_default.csv and .json.

**Frozen candidate (plateau pick).**
T=3.9912916647685157,e=0.9204433964469012,slack=0.019942957669350385,g=0.49694092992236427,walk_slack=0.9578396415072554 (other switches at spike defaults).

**Pre-fixed adoption rule (set before DEV-EVAL was run).** Adopt only if (1) family TEST paired CI lower bound > 0, (2) public not worse than 1.0 point (CI), (3) no public per-buyer regression worse than 1 point. Otherwise keep spike defaults.

**DEV-EVAL result** (seeds 0,7,8,9, n=210, paired bootstrap 10000 resamples; pick minus spike; run files in %TEMP%\verity_dev, not committed):

| Source | Spike | Pick | Diff | 95% CI |
|---|---|---|---|---|
| public | 50.7 | 49.9 | -0.79 | [-0.98, -0.56] |
| family TRAIN | 29.8 | 43.5 | +13.65 | [+11.69, +15.66] |
| family TEST | 38.3 | 39.0 | +0.63 | [-0.31, +1.64] |

0 policy and 0 truth violations in all runs.

**Decision.** NOT ADOPTED, spike defaults kept. TEST CI includes 0 (clause 1 fails). Public cooperative score drops about 2 points on seeds 0, 8, 9 (clause 3 fails). TRAIN gain is not independent evidence: those are the configs the tuner optimised.

**Interpretation (hypothesis, untested).** The TRAIN gain comes from fast-conceding buyers that stall under T=6 (deal rate where possible 0.63 -> 0.92 for TRAIN). On TEST the gain on C10_attack_fast is offset by losses on D17_max_noise and C13_attack_subset. A single global curve trades buyer types against each other. A rule reacting to observed bid speed (adaptive hold, row E) is a candidate, subject to GO/NO-GO.

**Open question.** Under spike defaults, family TRAIN deal rate "where possible" is only 0.57-0.66: about a third of feasible negotiations end with no deal and are not counted as deadlocks. Ceiling unknown.

**Caveat.** TEST is 8 configs, about 26 negotiations each per seed: the CI is wide; "no significant difference" is not "no difference". Public bots are not the hidden LLM buyers.

## 2026-11-28 - Reproduction of the DEV-EVAL comparison (no new decision)



Run on main fbf77cc (= tag v1.0-freeze), seeds 0,7,8,9, n=210. The frozen plateau-pick switches are the ones in the 2026-11-26 entry above.

Commands (repo root): `python experiments\\local_runner.py --seeds 0,7,8,9 --buyers public --out experiments\\tuning\\dev_eval --label spike_public`, then the same with `--switches <pick>` and `--label pick_public`; the same pairs for `--buyers family --split TRAIN` (spike_train, pick_train) and `--split TEST` (spike_test, pick_test). Compare each pair with `python experiments\\stats.py --a <pick file> --b <spike file>`.

Files: `experiments/tuning/dev_eval/2026-11-28_fbf77cc_local_{spike,pick}_{public,train,test}.json` (per-seed scores, per-negotiation lists, scenario hashes). They replace the %TEMP% files mentioned above.



Pick minus spike, 840 paired negotiations, 10000 resamples:



| Source | Spike | Pick | Diff | 95% CI | stats.py verdict |

|---|---|---|---|---|---|

| public | 50.7 | 49.9 | -0.790 | [-0.981, -0.557] | spike better |

| family TRAIN | 29.8 | 43.5 | +13.653 | [+11.693, +15.655] | pick better (in-sample) |

| family TEST | 38.3 | 39.0 | +0.630 | [-0.308, +1.637] | no significant difference |



Per-seed differences (0,7,8,9): public -0.838, -0.522, -0.855, -0.944; TRAIN +12.626, +15.378, +13.472, +13.136; TEST -0.178, +0.102, +1.645, +0.948 (seed 8 contributes most).

These reproduce the table of the 2026-11-26 entry exactly. Decision unchanged: NOT ADOPTED, spike defaults kept.

