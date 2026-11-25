# Ablation ladder (tune seeds 1,2,3, buyers public)

Score = mean over seeds. Δ vs A = paired difference with bootstrap 95% CI over negotiations pooled across seeds (5000 resamples, fixed RNG seed).

| row | variant | score | Δ vs A [95% CI] | deal rate | value/neg | value/deal | margin | policy | truth | deadlocks |
|---|---|---|---|---|---|---|---|---|---|---|
| A | Kit example seller (baseline) | 45.2 | — | 0.711 | 0.478 | 0.673 | 0.673 | 0 | 0 | 67 |
| S | Feasibility spike (reference) | 48.7 | +3.54 [+2.66, +4.47] | 0.721 | 0.487 | 0.676 | 0.676 | 0 | 0 | 0 |
| B0 | Gate+templates, baseline acceptance rule | unavailable: ImportError: cannot import name 'repair' from 'verity' (unknown location) |||||||||
| B | P0 tuned, echo_buyer_total=false | unavailable: ImportError: cannot import name 'repair' from 'verity' (unknown location) |||||||||
| C | P0 with re-slice (echo_buyer_total=true) | unavailable: ImportError: cannot import name 'repair' from 'verity' (unknown location) |||||||||
| D1 | C + allocator=proportional | unavailable: ImportError: cannot import name 'repair' from 'verity' (unknown location) |||||||||
| D2 | C + allocator=greedy | unavailable: ImportError: cannot import name 'repair' from 'verity' (unknown location) |||||||||

## Per-buyer score (mean over seeds)

| row | cooperative | hard_bargainer | manipulator |
|---|---|---|---|
| A | 64.0 | 36.4 | 35.2 |
| S | 69.5 | 38.6 | 38.1 |
