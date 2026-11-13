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
