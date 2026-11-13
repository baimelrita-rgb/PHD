# Paper 3, WP0: physics oracle feasibility

Final report for the paper: `reports/paper_report.md`. Comparison tables: `reports/comparison.md`. Decision log: `reports/decision_log.md`.

Plan: `WP0_FEASIBILITY_PLAN.md`. Results: `reports/feasibility_report.md`. Next stages, estimates, risks: `reports/wp1_plan.md`.

```
pip install -e .
bash scripts/00_download_sherlock.sh   # Sherlock 01-Basic, ~703 MB, md5 checked (data/ is not committed)
SEED=7 bash scripts/run_all.sh
```

| module | role |
| --- | --- |
| `src/p3/envelope.py` | benign envelope, radial topologies, LHS sampler |
| `src/p3/fastpf.py` | fast AC Newton-Raphson on pandapower's own Ybus (checked against `runpp`) |
| `src/p3/measure.py` | solved state -> measurement vector, benign limit check |
| `src/p3/rules.py` | rule DSL (JSON) and margin evaluator |
| `src/p3/oracle_search.py` | Stage A (LHS) and Stage B (differential evolution) falsification |
| `src/p3/lindistflow.py` | LinDistFlow per radial topology |
| `src/p3/oracle_exact.py` | Z3 encoding (envelope + LinDistFlow + rule) |
| `src/p3/cegis.py` | counterexample-guided threshold refinement |
| `src/p3/sherlock_io.py` | dataset inventory and loaders (data is parsed, never executed) |
| `src/p3/sherlock_model.py` | reconstructed Sherlock grid (switch mapping, identified transformer and tap parameters) |
| `src/p3/sherlock_residual.py` | physics residual of SCADA telemetry (WP1-a) |

Deviations from the plan, all documented in the reports: an extra fast AC solver; `load_p.*` and `sgen_p.*` added to the measurement vector (needed by R2 and R3); an `any_of` disjunction in the DSL for R3's absolute value; diagnostic scripts `02b_build_rules.py` and `03b_r3_diagnostic.py`; budget-sensitivity reports.
