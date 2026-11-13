# WP0 feasibility report

Paper 3: "From Alerts to Certified Rules: Self-Consolidating Intrusion Detection for Power Grids".
Every number below is copied from a generated report in `reports/`; the source file is named in each row.
Timings were measured on a 4-core cloud container CPU, not on a laptop.

## 1. Results

| ID | Result | Number behind it | Pass/fail |
| --- | --- | --- | --- |
| G1 | No grid model in the download. A reconstruction (pandapower CIGRE MV with all DER, plus Sherlock's 32 recorded switch states, plus transformer parameters fitted from recorded losses) reproduces the recorded physics | 100 train snapshots: bus voltage mean abs error 2.60e-04 pu, max 1.06e-03 pu (noise floor 5.00e-04 pu); line P max 1.98e-04 MW (`sherlock_model_check.md`) | **Fail** as worded (no model file); a usable model can be reconstructed |
| G2 | 4 attack types in test, but arp-spoof-dos has only 2 instances | industroyer 7, control-and-freeze 5, drift-off 4, arp-spoof-dos 2; train has no attacks (`dataset_inventory.md`) | **Fail** (by 1 instance) |
| G5-pre | Oracle finds counterexamples for the naive rule R1 in both layers. For the "sound" rule R3, none at the planned budget, but a 16x budget finds some: R3's margin was set from samples that miss the high-loss corner. After recalibrating the margin by search (R3_recal), no counterexample at either budget | R1: 358 of 9,999 benign LHS samples fire; Z3 SAT in 16 of 16 topologies, 16 of 16 confirmed on AC. R3 at 32,000 power flows: 2,341 firing evaluations. Max benign loss found 0.57288 MW against the calibration maximum of 0.26838 MW (`oracle_search*.md`, `r3_diagnostic.md`) | **Pass, qualified** |
| G6 | LinDistFlow error under 0.01 pu on random benign samples; above 0.01 pu in the worst case found by search | 1,000 samples: mean 0.00210, p95 0.00561, max 0.00993 pu. Worst case found by search: 0.01425 pu (`lindistflow_error.md`) | **Pass on samples, fail on worst case** |
| T | One certification takes seconds | Search layer 3.4 to 3.9 s per rule at the planned budget; exact layer 1.2 to 15.1 s per rule; worst case R2, about 19 s for both layers (`oracle_search.md`, `oracle_exact.md`) | **Pass** |

## 2. What worked and what did not

What worked:
- The AC search oracle separates the naive and the context rules from a sound rule. It found the R1 false alarm in Stage A, in under 4 s.
- The exact layer (Z3 on LinDistFlow) found R2 counterexamples that the planned 2,000-flow search missed. They occur where tie S1 is closed with line 12-13 or 13-14 out, which puts feeder-2 load on line 1-2 outside the rule's fixed "downstream" set. Both SAT models are benign and fire the rule on the full AC model and on pandapower `runpp`.
- Every Z3 counterexample (18 of 18) was confirmed on the AC model.
- CEGIS on R1 converged in 3 iterations. It also made visible that the rule was refined into uselessness: tau went from 0.94281 to 0.89990, below the 0.90 pu benign limit, and the share of the original firing band left is 0.0000.
- A fast AC solver built on pandapower's own admittance matrices matches `runpp` to 5.02e-07 and is about 16 times faster (2.11 ms against 33.54 ms per flow, `envelope_smoke.md`). Without it, the budgets would not fit the 10-minute limit.

What did not work, or is weaker than planned:
- The planned search budget (2,000 flows) is too small. It missed the counterexamples for R2 and R3 that a 32,000-flow run (about 18 s) finds.
- Calibrating a margin from random samples is unsafe. A 2,000-sample maximum underestimated the envelope maximum by a factor of at least 2.135. Stop condition 2 applies in spirit: the rule's calibration is at fault, not the physics or the envelope.
- The exact layer cannot certify R3. LinDistFlow is lossless, so the balance residual is 0 by construction and the UNSAT result is vacuous.
- Z3 UNSAT certifies the linear model only. The linear model's worst error found so far (0.01425 pu) is larger than the planned 0.01 pu bound.
- The CIGRE MV operating limits barely constrain the envelope: 2,000 of 2,000 LHS samples are benign. Limits bind only at states found by optimization.
- The pandapower CIGRE MV model has no tap changer, so taps are fixed in the reference envelope. Sherlock does step taps; 6 of 106 scanned train snapshots had a nonzero tap.

## 3. Recommendation

**Go, with changes:**
1. Set rule margins by search (falsification), never by sample percentiles alone. Report the search budget with every "no counterexample" claim.
2. Make the exact layer the default for linear rules. Raise the search budget for the rest; 32,000 flows cost about 18 s.
3. Either add an error margin to the linear model that is at least the worst LinDistFlow error found (0.01425 pu) and then claim "certified relative to the linear model plus margin", or claim "physics-validated" rather than "certified".
4. Add a loss-aware exact layer (loss bounds or a convex relaxation) before using balance rules such as R3.
5. For Sherlock, use the reconstructed model in `scripts/07_sherlock_model_check.py`, and add transformer tap parameters once a source is approved.

## 4. Open items for the owner

1. G2: accept 2 arp-spoof-dos instances, or drop the type? It is a network-level attack, and protocol rules are out of scope for WP0.
2. G1: may I fetch the original Wattson `cigre-mv` scenario definition, which is not in the Zenodo record? It is a separate source, not a mirror of the blocked file.
3. Transformer tap parameters (step size, side, range) for both the reference envelope and Sherlock: their values are ⟨·⟩.
4. R3: approve recalibrating the margin by search (`rules/rules_variants.json`), or define it differently.
5. Envelope: transformer loading reached 108.25 % in benign samples, and the plan sets no transformer limit. Add one? Also, should reconfigurations such as "S1 closed, line 1-2 out" count as benign?
6. G6: choose "certified with error margin" or "physics-validated".
7. Timings come from a cloud container, not a laptop.

## 5. Reproduction

```
cd paper3-wp0
pip install -e .            # or the dependencies in pyproject.toml
bash scripts/00_download_sherlock.sh   # 01-Basic.zip, md5 checked
SEED=7 bash scripts/run_all.sh         # all reports, about 5 min on 4 cores
```

Seeds: base `--seed 7`. Derived streams: narrow envelope 1007, Stage A 2007, LinDistFlow error 3007, DE runs seed plus topology index. Python 3.13.18, pandapower 3.5.6, numpy 2.4.6, scipy 1.18.1, z3-solver 5.4.1.0, pandas 2.3.3, networkx 3.7, numba 0.68.1. The full list is in `reports/env.txt`.
