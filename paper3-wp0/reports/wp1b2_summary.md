# WP1-b2 summary: an exact layer for meshed and radial configurations

Numbers are copied from the generated reports named in each row.

## What was built

- `src/p3/linac.py`: a linearised AC power flow, the first-order expansion at the envelope centre, built from the Newton-Raphson Jacobian of the fast solver. It works for radial and meshed configurations. It keeps line charging, losses and the meshes at the operating point, and works in voltage magnitude.
- The exact layer takes `--model lindistflow | linac | auto`.
- Constraints implied by the parameter box are dropped. This is checked with interval arithmetic and is exact: verdicts are identical before and after, and solve time falls 10 to 25 times. For example, R2 on the reference grid went from 46 s to 4.3 s.
- Rule-specific error bounds (`scripts/04b_atom_bounds.py`): the error of each linear rule expression is bounded directly, instead of summing per-quantity bounds. The term errors are correlated, so the bound is about half: 0.24376 against 0.42309 MW on the reference grid, 0.28664 against 0.53803 MW on Sherlock.

## Accuracy against the full AC model (worst case found by adversarial search)

| Grid | LinDistFlow (radial only) | Linearised AC | Source |
| --- | --- | --- | --- |
| Reference CIGRE MV | 0.01204 pu | **0.00708 pu** | `lindistflow_error.md`, `linac_error.md` |
| Sherlock (336 configurations, 166 meshed) | 0.01207 pu (radial only) | **0.00834 pu** (all) | `lindistflow_error_sherlock.md`, `linac_error_sherlock.md` |

G6 (max error below 0.01 pu) now **passes on the worst case**, not only on samples, with the linearised AC model.

## Verdicts (robust mode, linearised AC, rule-specific bounds)

| Rule | Reference grid (16 configurations) | Sherlock grid (336 configurations) |
| --- | --- | --- |
| R1 naive threshold | refuted (16 of 16 nominal SAT models confirmed on AC) | refuted (183 of 212 confirmed) |
| R2 context rule | refuted | **certified**, all 336 configurations |
| R3 power balance | **certified** | **certified**, all 336 configurations |

Sources: `oracle_exact_linac.md`, `oracle_exact_linac_sherlock.md`. Exact-layer time on Sherlock: 4 to 104 s per rule and mode; the whole script takes 4.7 min.

All verdicts agree with the AC search layer: R1 and R2 have search counterexamples on the reference grid; on Sherlock, R2 and R3 have none at 32,000 flows.

CEGIS with the linearised model: the reference grid reaches tau 0.90066 after the 10-iteration cap (1.55 % of the firing band left); Sherlock converges to 0.89998 (`cegis_demo_linac.md`, `cegis_demo_linac_sherlock.md`).

## What this means for the paper

- The G5-pre separation (naive refuted, sound certified) now holds in the exact layer, not only in the search layer.
- The claim can be: "certified relative to a linearised AC model with validated error bounds (worst error below 0.01 pu), on all radial and meshed operating configurations, and AC-validated".
- Remaining weakness: the error bounds are empirical (adversarial search), not proven. Line loading bounds stay wide (9.5 to 11.8 percentage points).
