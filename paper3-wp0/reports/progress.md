# Progress

- T0 done: package `src/p3`, 8 tests pass (`python -m pytest -q`).
- T2 done: 2000 LHS samples, all 2000 benign, 16 radial topologies; taps fixed (model has no tap changer). `envelope_smoke.md`.
- T3 done: R1 tau 0.94281, R2 x 74.904 % and y 2.9481 MW, R3 m 0.40258 MW; DSL unit tests pass. `rules.md`.
- T4 done: R1 counterexample (Stage A); R2 and R3 none at budget 2000. At budget 32000, R2 and R3 also have counterexamples. Stop condition 2 diagnosed: R3 margin miscalibrated by sampling. `oracle_search.md`, `oracle_search_budget32000.md`, `r3_diagnostic.md`.
- T5 done: LinDistFlow max error 0.00993 pu on samples, 0.01425 pu worst case found by search. Z3: R1 SAT, R2 SAT, R3 UNSAT (vacuous, lossless model); 18 of 18 SAT models confirmed on AC. `lindistflow_error.md`, `oracle_exact.md`.
- T6 done: R1 refined in 3 iterations to tau 0.89990, firing band left 0.0000 (refined into uselessness). `cegis_demo.md`.
- T1 done: download md5 verified. G1 no (no model file), G2 fail (arp-spoof-dos has 2 instances). `dataset_inventory.md`.
- T7 done: reconstructed model matches the recorded physics after fitting transformer parameters; voltage max error 1.06e-03 pu. `sherlock_model_check.md`.
- T8 done: `feasibility_report.md`. Recommendation: go with changes.

## Round 2 (owner decisions 1 to 6)

- D1 done: arp-spoof-dos excluded from G2; 3 process-level types remain (G2 fails with "at least 4 types", passes with "at least 3"). `dataset_inventory.md`.
- D2 done: public Wattson (fkie-cad/wattson) has only a generic CIGRE MV example; Sherlock's scenario is not public.
- D3 done: tap changer identified from data: HV side, 1.500 % per step; validation error at the noise floor. `sherlock_taps.md`, `rules/sherlock_grid_params.json`.
- D4 done: R3 margin calibrated by search (m 0.86726 MW); no counterexample at 2000 or 32000 flows. `rules.md`, `oracle_search*.md`.
- D5 done: robust exact layer with validated error bounds (`rules/model_error_bounds.json`); verdicts R1 refuted, R2 refuted, R3 inconclusive in the exact layer. `oracle_exact.md`, `lindistflow_error.md`.
- D6 done: transformer loading limit added (1929 of 2000 benign); N-1 reconfigurations kept, all 4 Sherlock reconfigurations inside the envelope. `envelope_smoke.md`.
- WP1-a done: physics residual detector on Sherlock telemetry, 0.00059 false alarms per benign record; control-and-freeze 5/5, drift-off 3/4, industroyer 2/7. `physics_residual.md`.

## WP1-b

- G2 relaxed to 3 types (owner): pass. Venue: IEEE TSG primary, IJEPES backup.
- 02-Semiurban downloaded (md5 verified), extracted without pcaps and logs; SimBench 1-MV-semiurb--2-sw identified as base, 56 extra DER transformers noted.
- Grid abstraction; reference grid results reproduce exactly.
- Sherlock envelope from train: 336 configurations (170 radial); coverage train 100 %, benign test topology 99.86 %, continuous 100 %.
- Sherlock oracle: R1 refuted and refined into uselessness (tau 0.89998); R2 certified (robust, radial part); R3 no counterexample by search, exact inconclusive. `wp1b_summary.md`.
