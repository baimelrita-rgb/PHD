# WP0 feasibility report (round 2, after the owner's decisions)

Paper 3: "From Alerts to Certified Rules: Self-Consolidating Intrusion Detection for Power Grids".
Every number is copied from a generated report in `reports/`, named in each row. Timings were measured on a 4-core cloud container CPU.
Round 1 is in git history (commit "WP0 feasibility: physics oracle for rule certification").

## 0. Owner decisions applied

| # | Decision | What changed |
| --- | --- | --- |
| 1 | Drop arp-spoof-dos from G2 | `01_inventory.py --exclude-types`, default `arp-spoof:arp-spoof-dos` |
| 2 | Fetch the Wattson scenario | Public repo `fkie-cad/wattson` (commit 839d4e4) holds only a `powerowl-example` built from `create_cigre_network_mv(with_der="all")`, with taps undefined. Sherlock's `cigre-mv` scenario is not public |
| 3 | Tap parameters | Identified from data, nothing needed from the owner: HV side, 1.500 % per step, positions seen [-1, 0] (`sherlock_taps.md`) |
| 4 | R3 margin by search | `02b_build_rules.py` maximises the residual by DE: m = 1.5 x 0.57817 = 0.86726 MW (`rules.md`) |
| 5 | G6 claim | Robust exact layer with validated error bounds delta (`model_error_bounds.json`); claim: "certified relative to LinDistFlow with a validated error bound, AC-validated" |
| 6 | Envelope | Added transformer loading <= 100 %. Kept N-1 reconfigurations: all 4 Sherlock benign reconfigurations fall inside the 16 envelope topologies (`envelope_smoke.md`) |

## 1. Results

| ID | Result | Number behind it | Pass/fail |
| --- | --- | --- | --- |
| G1 | No model file in the download or in public Wattson. The reconstruction matches the recorded physics | 100 tap-0 snapshots: voltage mean 2.60e-04, max 1.06e-03 pu (noise floor 5.00e-04); tap -1 validation: mean 2.68e-04, max 9.24e-04 pu (`sherlock_model_check.md`, `sherlock_taps.md`) | Fail as worded; model reconstructed and validated |
| G2 | After dropping arp-spoof: 3 process-level types | industroyer 7, control-and-freeze 5, drift-off 4 (`dataset_inventory.md`) | Fail with "at least 4 types"; pass with "at least 3" |
| G5-pre | Naive R1 and context R2 refuted by both layers; search-calibrated R3 has no counterexample at 2,000 or 32,000 flows | R1: 253 of 9,671 benign samples fire; R2: DE finds it at 32,000 flows, Z3 finds it in 2 topologies, confirmed on AC; R3: best margin -3.03 (scaled) at 32,000 flows (`oracle_search*.md`, `oracle_exact.md`) | **Pass** (R3 evidence is search-based) |
| G6 | Sample max below 0.01 pu, worst case found above it | 1,000 samples: max 0.00802 pu; search worst case 0.01204 pu; delta_vm = 0.01505 pu (`lindistflow_error.md`) | Pass on samples, fail on worst case; handled by delta |
| T | Seconds per rule | Search 3.6 to 3.9 s at 2,000 flows, about 20 s at 32,000; Z3 1.6 to 19.9 s per mode (`oracle_search*.md`, `oracle_exact.md`) | **Pass** |

## 2. What worked and what did not

What worked:
- Both layers refute the naive rule and the context rule. CEGIS on R1 converged in 7 iterations to tau 0.89990: refined into uselessness (band left 0.0000), and this is visible in the report.
- Calibrating the margin by search fixed R3: no counterexample even at 16 times the planned budget.
- The Sherlock reconstruction reaches the noise floor once transformer losses and taps are identified from data.
- WP1-a (`physics_residual.md`): a physics-consistency detector on the control center's telemetry has 0.00059 false alarms per benign record and detects control-and-freeze 5 of 5, drift-off 3 of 4 and industroyer 2 of 7.

What did not work:
- The robust exact layer is inconclusive for R3: delta for transformer P (0.65 MW per transformer) exceeds the margin. Balance rules need a loss-aware exact layer.
- Robust SAT models are not AC counterexamples (0 of 34); refutation comes from the nominal layer or the search. The robust layer certifies; it does not refute.
- LinDistFlow's line loading error is large (delta 10.3 percentage points), so the exact layer can certify loading rules only with a wide margin.
- Physics consistency misses 5 of 7 industroyer attacks. Those send valid commands, so the telemetry stays physically consistent.

## 3. Recommendation

Go to WP1 (`wp1_plan.md`). Scope the paper's physics-certified rules to telemetry-integrity attacks, and add a second, context-based rule family for command attacks.

## 4. Open items for the owner

1. G2: relax to "at least 3 process-level types, at least 3 instances each"? (Recommended.)
2. The wording "certified relative to LinDistFlow with a validated error bound": does it fit the target venue?

## 5. Reproduction

```
cd paper3-wp0
pip install -e .
bash scripts/00_download_sherlock.sh
SEED=7 bash scripts/run_all.sh
```

Seeds as in round 1 (base 7). Python 3.13.18, pandapower 3.5.6, numpy 2.4.6, scipy 1.18.1, z3-solver 5.4.1.0; full list in `reports/env.txt`.
