# Paper report: From Alerts to Certified Rules

**Self-consolidating intrusion detection for power grids**

Status: experiments complete. Every number below is copied from a generated report in `reports/` (named in brackets). The method text is in `paper_report_methods.md`; the full chronology of attempts and decisions is in `decision_log.md` and `progress.md`.

---

## Abstract (draft)

Anomaly detectors for grid telemetry raise alerts but leave no durable, inspectable knowledge, while hand-written detection rules are brittle and cause false alarms under benign operating changes. We present a self-consolidating intrusion detection system:

- Each detector alert is turned into deterministic detection rules.
- A rule enters a rule library only after a **physics oracle** certifies that no benign, physically feasible operating state triggers it.
- The oracle combines an AC search layer (sampling and differential evolution) with an exact layer: Z3 over a linearised AC power flow, made robust by adversarially validated model-error bounds. Counterexamples refine rules.

On the Sherlock dataset, three grid models were reconstructed from data and validated at the measurement noise floor: CIGRE MV with 15 buses, SimBench semi-urban with 178 buses and about 40 % of elements without telemetry, and SimBench rural with 99 buses.

- The oracle refutes rules mined from history, which become useless when made safe, and certifies physically grounded ones.
- Replayed without labels, the certified library catches attacks the detectors miss and sometimes fires earlier, at a false alarm rate of about 0.1 % per record.
- On the partially observable grid, state estimation and on-demand certification of every new topology (5 to 11 s each) extend the approach.
- On a third grid without any training day, a zero-training transfer shows what carries over: the detector's global threshold and the physics certificate transfer; per-measurement rule margins need the grid's own noise data.
- ML detectors on raw telemetry fail under benign operating change (43 % to 99.99 % false alarms on three grids), which motivates certified rules.

## Contributions

1. A certification oracle for detection rules: search layer plus robust exact layer, with model-error bounds validated by adversarial search, rule-specific bounds, and exact pruning of box-implied constraints. G5-pre separation holds in both layers.
2. A linearised AC exact layer that covers meshed configurations. Worst error found: 0.00708 pu on the reference grid and 0.00834 pu on Sherlock, against 0.01204 and 0.01207 for LinDistFlow. It makes power-balance rules certifiable.
3. Rule synthesis from alerts: physical-invariant rules, grid-wide invariant rules and state rules, with counterexample-guided refinement of margins.
4. A self-consolidating loop driven only by detector alerts, evaluated without labels in the loop.
5. Partial observability and unseen topologies: iterated WLS state estimation with pseudo-measurements, and on-demand certification per topology.
6. A zero-training transfer experiment on a third grid (03-Rural, no train day), separating what transfers between grids from what needs local calibration.
7. Data-driven reconstruction of three Sherlock grid models (switch mapping, transformer and tap identification, DER-and-storage transformer groups), validated against ground truth.
8. Negative results that matter for practice:
   - raw-feature ML fails under benign change;
   - thresholds mined from history are refined into uselessness;
   - a certificate covers physical variation, not telemetry noise;
   - the margin factor has a lower bound.

---

## 1. Experimental setup

| Item | 01-Basic | 02-Semiurban |
| --- | --- | --- |
| Grid | CIGRE MV (all DER), 15 buses, 2 transformers, 32 switches | SimBench 1-MV-semiurb--2-sw plus 56 DER-and-storage transformer groups: 178 buses, 58 transformers, 360 switches |
| Telemetry | fully monitored, 1 Hz | about 40 % of elements unmonitored; every 5th record used |
| Test attacks (process) | control-and-freeze 5, drift-off 4, industroyer 7 | control-and-freeze 5, drift-off 9, industroyer 9 |
| Excluded | arp-spoof-dos 2 (owner decision; reported separately) | arp-spoof-dos 6 |
| Envelope topologies | 336 enumerated (170 radial, 166 with one loop) | structural; certified on demand (13 test topologies) |

The third grid, **03-Rural**, is exactly SimBench 1-MV-rural--2-sw: 99 buses, 101 lines, 2 transformers, 204 switches. It has no train day; the test day has control-and-freeze 5, drift-off 9, industroyer 8 and arp-spoof-dos 6, and the first attack comes 0.65 h in. It is run as a zero-training transfer: envelope from SimBench planning profiles (P) and Q bounds transferred from Semiurban; SE-BDD threshold and persistence transferred from Semiurban; ML trained on the first 30 minutes only. Labels are used only for evaluation.

Train days contain no attacks. All thresholds and calibrations use train only. Benign test records are those more than 60 s from any attack window.

## 2. Grid reconstruction (no model in the download)

| Grid | Validation against ground truth | Report |
| --- | --- | --- |
| 01-Basic, published CIGRE parameters | voltage mean 1.23e-03, max 3.25e-03 pu | `sherlock_model_check.md` |
| 01-Basic, transformer losses fitted on disjoint snapshots | voltage mean 2.60e-04, max 1.06e-03 pu (noise floor 5.00e-04) | `sherlock_model_check.md` |
| 01-Basic, tap changer (HV side, 1.5 % per step), validation set | mean 2.68e-04, max 9.24e-04 pu (tap ignored: 1.23e-02) | `sherlock_taps.md` |
| 02-Semiurban, 56 groups identified (power balance error at most 5.7e-05 MW) | train: mean 2.80e-04, max 9.96e-04 pu; test: mean 2.75e-04, max 1.03e-03 pu | `semiurban_identify.md`, `semiurban_model_check_*.md` |
| 03-Rural, SimBench base without additions (fitted transformers match SimBench) | test: mean 2.86e-04, max 1.01e-03 pu | `rural_identify.md`, `rural_model_check_test.md` |

## 3. Oracle results

Linear-model accuracy, worst case found by adversarial search (`lindistflow_error*.md`, `linac_error*.md`):

| Grid | LinDistFlow (radial only) | Linearised AC (all configurations) |
| --- | --- | --- |
| Reference CIGRE MV | 0.01204 pu | 0.00708 pu |
| Sherlock 01-Basic | 0.01207 pu | 0.00834 pu |

Verdicts, robust mode, linearised AC, rule-specific bounds (`oracle_exact_linac.md`, `oracle_exact_linac_sherlock.md`). All agree with the AC search layer.

| Rule | Reference grid | Sherlock grid (336 configurations) |
| --- | --- | --- |
| R1, threshold mined from data | refuted | refuted |
| R2, context rule | refuted | certified |
| R3, power balance (margin calibrated by search) | certified | certified |

CEGIS on R1: tau falls to 0.89990 on the reference grid and 0.89998 on Sherlock, below the 0.90 pu limit; the firing band left is 0.0000 (`cegis_demo*.md`). A safe threshold mined from history is a useless one.

## 4. Main comparison (`comparison.md`)

### 4.1 01-Basic (fully observed)

| Method | CFC | Drift-off | Industroyer | Mean delay s | False alarms per benign record |
| --- | --- | --- | --- | --- | --- |
| Classic residual test (D1, full power flow) | 5/5 | 3/4 | 2/7 | 78 | 0.00059 |
| ML: autoencoder, raw telemetry | 5/5 | 4/4 | 7/7 | 1 | 0.99988 |
| ML: Isolation Forest, physics-informed | 0/5 | 0/4 | 0/7 | n/a | 0.00000 |
| ML: autoencoder, physics-informed | 4/5 | 3/4 | 2/7 | 92 | 0.00100 |
| Detectors D1 or AE (alert source) | 5/5 | 3/4 | 2/7 | 77 | 0.00109 |
| Certified library, strict (rules learned before the attack) | 4/5 | 4/4 | 2/7 | 102 | 0.00124 |
| Certified library, rules active at the time | 4/5 | 4/4 | 3/7 | 70 | 0.00124 |
| **Combined: detectors or certified library** | **5/5** | **4/4** | **3/7** | **68** | **0.00171** |

### 4.2 02-Semiurban (partially observed)

| Method | CFC | Drift-off | Industroyer | Mean delay s | False alarms per benign record |
| --- | --- | --- | --- | --- | --- |
| Classic bad-data detection (SE-BDD) | 3/5 | 4/9 | 0/9 | 261 | 0.00000 |
| ML: autoencoder, raw telemetry | 5/5 | 9/9 | 9/9 | 19 | 0.85948 |
| ML: Isolation Forest, SE-residual features | 1/5 | 4/9 | 0/9 | 242 | 0.00296 |
| ML: autoencoder, SE-residual features | 4/5 | 6/9 | 7/9 | 121 | 0.14888 |
| Certified library, single record | 5/5 | 7/9 | 7/9 | 123 | 0.01586 |
| **Certified library, persistence L = 3** | **4/5** | **6/9** | **0/9** | **124** | **0.00401** |
| Combined: SE-BDD or certified library (L = 3) | 4/5 | 6/9 | 0/9 | 124 | 0.00401 |
| Combined: SE-BDD or AE or certified library (L = 3) | 4/5 | 7/9 | 7/9 | 93 | 0.14923 |

### 4.3 03-Rural (zero-training transfer)

| Method | CFC | Drift-off | Industroyer | Mean delay s | False alarms per benign record |
| --- | --- | --- | --- | --- | --- |
| Classic bad-data detection (SE-BDD), threshold transferred from Semiurban | 0/5 | 5/9 | 0/8 | 275 | 0.00017 |
| ML: autoencoder, raw telemetry (30 min training) | 4/5 | 8/9 | 5/8 | 117 | 0.43249 |
| ML: Isolation Forest, SE-residual features (30 min) | 3/5 | 5/9 | 1/8 | 187 | 0.00087 |
| ML: autoencoder, SE-residual features (30 min) | 5/5 | 8/9 | 4/8 | 81 | 0.14358 |
| Certified library, attempt 1: per-kind noise transferred, L = 3 | 5/5 | 8/9 | 7/8 | 15 | 0.72315 |
| Certified library, attempt 2: global threshold as minimum margin, single record | 1/5 | 5/9 | 3/8 | 207 | 0.00087 |
| Certified library, attempt 2, persistence L = 3 | 0/5 | 5/9 | 0/8 | 275 | 0.00017 |

Sources: `comparison.md` (03-Rural section) and `semiurban_consolidation_perkind_rural.md` for attempt 1.

Envelope coverage without Rural data: load P 100 % of benign records; load Q 10 % from SimBench profiles and 90.4 % after transferring Q bounds from Semiurban (`rural_envelope.md`).

### 4.4 Reading

- **01-Basic.** Adding the certified library to the detectors adds one drift-off and one industroyer instance and cuts the mean delay from 77 to 68 s, at +0.0006 false alarms per record. Under strict accounting (rules learned before the attack only) the library alone still catches every drift-off, including one that the detectors miss.
- **Semiurban.** The certified library with persistence detects more than the classic SE-BDD (control-and-freeze 4/5 against 3/5, drift-off 6/9 against 4/9) at 0.004 false alarms against 0. Industroyer is caught only in single-record mode (7/9), from switching transients, at 0.016 false alarms.
- **ML.** Raw-feature ML is unusable on all three grids, and physics-informed features fix it on 01-Basic. On Semiurban the SE-feature autoencoder still has 0.149 false alarms: the test day has topologies not seen in train.
- **Transfer (03-Rural).**
  - The SE-BDD threshold transfers: 0.00017 false alarms on a grid it never saw, drift-off 5/9.
  - Per-measurement noise floors do not transfer: Rural's transformer flow residuals reach 19 sigma against a transferred floor of 0.47, giving library attempt 1 its 0.72 false alarms.
  - Using the transferred global threshold as the minimum margin (attempt 2, chosen after attempt 1 failed and reported as such) removes the flood, but then the library adds nothing over the detector with persistence.
  - Conclusion: on-demand physics certification needs no local data, but the library's noise term needs a short benign calibration on each grid.

## 5. Synthesis and consolidation

- **Synthesis from alerts** (`synthesis_sherlock.md`, 01-Basic): certified rules for control-and-freeze 3/5, drift-off 3/4 and industroyer 3/7. False alarms of the certified rules are at most 0.0003 per benign record. Two plausible rules ("DER to zero") were correctly refuted.
- **Consolidation loop** (`consolidation_sherlock.md`, 01-Basic): 22 alert episodes, 9 already covered by the library, 10 certified rules (8 grid-wide invariant, 2 state). All six "line out" state candidates were refuted, because those reconfigurations are benign.
- **On-demand certification** (`semiurban_consolidation_semiurban.md`, 02-Semiurban): all 13 test topologies certified, 12 of them unseen in train. Latency per topology: median 5 s, max 11 s. The certificate is search-based only, because the iterated state-estimation residual is not linear.

## 6. Robustness and ablations (`comparison.md`)

- **Seeds 7, 8, 9** (oracle search and ML training): per-type detection identical on both grids. False alarms of the 01-Basic library vary from 0.00115 to 0.00124. Semiurban is identical across seeds, because its margins are dominated by train noise.
- **Persistence** (library): L = 1, 3, 5 gives false alarms 0.00124, 0.00091, 0.00065 on 01-Basic with unchanged detection. On Semiurban L = 3 removes the industroyer transients (7/9 to 0/9) and cuts false alarms from 0.01586 to 0.00401.
- **Margin factor**:

  | Margin factor | 01-Basic | 02-Semiurban (L = 3) |
  | --- | --- | --- |
  | 1.25 | grid-wide invariant rules cannot certify (robust bound 1.25 x oracle bound is not below the margin); library left with 3 state rules | same detection, false alarms 0.00662 |
  | 1.5 (default) | as in 4.1 | false alarms 0.00401 |
  | 2.0 | same detection, false alarms 0.00109 | same detection, false alarms 0.00174 |

  The margin factor must exceed the bound safety factor. Above that it trades false alarms for delay. The default was fixed before these runs and is not re-tuned on test.

## 7. Findings for the discussion

1. **ML on raw telemetry fails under benign operating change** (0.99988 and 0.85948 false alarms). Physics-informed features help, but do not fully generalise to unseen topologies (0.149 on Semiurban).
2. **A safe threshold mined from history is a useless one.** CEGIS drives it below the operating limit on both grids. Synthesis must produce context and invariant rules, not thresholds.
3. **The certificate and telemetry noise are separate guarantees.** One rule certified against physics fired on 31 % of benign records when its noise level was estimated from about 100 records. Noise calibration needs enough data and a per-kind floor.
4. **Sherlock operates meshed and with planned de-energised islands.** A radial-only or train-only topology envelope is wrong: train topologies cover only 16 % of benign Semiurban test time. On-demand certification solves this.
5. **Partial observability needs state estimation with load reactive power and Gauss-Newton correction.** Linear estimation alone hides small falsifications. Fixed load Q produced 72 to 86 sigma residuals on real telemetry.
6. **What transfers between grids.** A detector's global threshold and the physics certificate transfer to a grid without training data; per-measurement noise margins do not (03-Rural).
7. **Search must be concentrated where a rule can fire.** A joint search over all configurations under-tested topology-specific rules. The first consolidation results were optimistic and were corrected.

## 8. Threats to validity

- One test day per grid (three grids), and few attack instances per type (4 to 9). Results are per instance, without confidence intervals.
- 03-Rural has no train day; its ML baselines were trained on 30 minutes and are weak by construction. Library attempt 2 was chosen after attempt 1's failure on the same test day; both are reported.
- Error bounds in the robust exact layer are empirical (adversarial search, safety factor 1.25), not proven. On Semiurban the certificates are search-based only.
- Both grid models are reconstructions, validated at the noise floor, not the original Wattson scenarios.
- The library learns and is evaluated on the same test day, in time order. Strict accounting is reported to bound the optimism.
- Semiurban uses every 5th record; detection delays there have 5 s resolution.
- arp-spoof-dos is excluded from the process-attack evaluation (owner decision), but reported.

## 9. Reproducibility

```
cd paper3-wp0
pip install -e .            # plus simbench, scikit-learn
bash scripts/00_download_sherlock.sh
bash scripts/00b_download_semiurban.sh
bash scripts/00c_download_rural.sh
SEED=7 bash scripts/run_all.sh       # main results
bash scripts/night_runs.sh           # seeds and ablations
bash scripts/rural_runs2.sh          # 03-Rural transfer (after 15a/15b/16b/17 with --grid rural, see decision_log.md)
python scripts/19_comparison.py      # comparison tables
```

Seeds: base 7; robustness 8 and 9. Package versions: `reports/env.txt`. Each script finishes in under 10 minutes on the 4-core container used (the oracle exact layer runs Z3 in parallel).

## 10. Assessment (author's judgement, not a measurement)

| Venue | Estimate |
| --- | --- |
| IEEE Transactions on Smart Grid | about 62 % |
| International Journal of Electrical Power & Energy Systems | about 76 % |

The method is complete and evaluated on three grids, including a zero-training transfer, with honest negative results. The third grid adds generalisation evidence (reconstruction, physics certificate and detector threshold all transfer), and it also shows a limit: the library needs per-grid noise calibration. Gains over the classic detector remain modest.

What would raise the estimate most:
- a second test day per grid, or a short benign calibration day for 03-Rural;
- a formal error bound for the linearised model;
- confidence intervals over more attack instances.
