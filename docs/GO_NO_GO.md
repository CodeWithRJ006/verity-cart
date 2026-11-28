# GO / NO-GO decisions for P2 modules (Dev2)



Rule (guide 02, S6): a P2 module ships only if ALL hold: (a) paired improvement over the P0 spike-equivalent on held-out family configs and the SEALED seeds has a 95% CI above 0; (b) 0 violations; (c) no per-buyer-type regression worse than 1 point; (d) latency still ms-level; (e) at least one working day remains. Default: NO-GO for Bayesian/DP.



Submitted configuration: spike defaults in config.py (T=6, e=0.5, slack=0, g=0.5, walk_slack=0.97), frozen at v1.0-freeze (fbf77cc). Nothing below is part of it.



| Module | Decision | Evidence |

|---|---|---|

| Global re-tune of (T, e, slack, g, walk_slack) | NO-GO, not adopted | experiments/LOG.md (2026-11-26 and 2026-11-28 entries) and experiments/tuning/dev_eval/*.json. Family TEST: +0.630, CI [-0.308, +1.637] includes 0 (clause a fails). Public bots: -0.790, CI [-0.981, -0.557]. The cooperative buyer lost about 2 points on seeds 0, 8, 9 (clause c fails). The family TRAIN gain (+13.653) is in-sample: the tuner optimised those configs. |

| Adaptive hold (ablation row E) | NO-GO | Not built; verity/ contains no hold logic. Only an untested hypothesis in LOG.md. Clause (e) cannot be met. |

| Belief / DP (row F) | NO-GO | Not built; default NO-GO. |

| Greedy allocator (row D) | Not shipped | allocator="greedy" raises NotImplementedError (verity/repair.py:209-210 and a guard in verity/strategy.py); no row D result is reported. |

| Round-10 margin (r10_close_margin 0.03, i.e. walk_slack 0.97) | Unchanged | The round-10 EV table that would justify a change was not built. |



Caveats: every comparison uses the three public bots and a parametric buyer family, not the hidden LLM buyers; "no significant difference" is not "no difference" (family TEST is 8 configs). The abstract makes no claim about any module in this table.

