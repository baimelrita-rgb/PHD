# Decision log (autonomous work)

From this point the owner asked for autonomous work without approvals. Every attempt, decision and its reason is
recorded here, in time order. Earlier decisions are in `progress.md`, `feasibility_report.md` and the stage
summaries (`wp1b_summary.md` to `wp2b_summary.md`).

## Plan for the autonomous phase

| Step | Goal | Why (risk it addresses) |
| --- | --- | --- |
| A | ML detectors on 02-Semiurban (autoencoder, Isolation Forest; raw and state-estimation residual features) | TSG reviewers expect ML; Semiurban had only the SE-BDD detector |
| B | One comparison table for both grids: classic bad-data detection, ML alone, certified library alone, combined | the paper's central table was missing |
| C | Seed robustness: ML training and oracle search seeds 7, 8, 9 | single-seed results; risk of luck |
| D | Ablations: margin factor 1.25 / 1.5 / 2.0, persistence 1 / 3 / 5 | margin and persistence were fixed by judgement |
| E | Final reports: plain-language report with diagrams, professional report for the paper | owner's request |

Rules kept: every number from code; each script under 10 minutes; no tuning on test; negative results reported.

## Step A and B: decisions

1. **ML on Semiurban, physics-informed features = state-estimation residuals.** The D1 power-flow residual needs every injection, which Semiurban does not have. The SE residual is the equivalent for partial observability. Raw features include load Q (it varies on its own profile here); unmonitored values become 0 after standardisation.
2. **Same calibration as on 01-Basic:** fit on the first 75 % of train, threshold on the last 25 %, persistence. No tuning on test.
3. **Records:** Semiurban uses every 5th record, aligned with the SE timeline, to keep each script under 10 minutes.
4. **Robustness and ablation runs write tagged files** (`_s8`, `_s9`, `_m125`, `_m20`), so the main results are never overwritten.
5. **Persistence ablation (L = 1, 3, 5)** is computed from saved single-record firings, without rerunning the oracle.
6. **The comparison table** (`scripts/19_comparison.py`) is computed only from saved per-record alarms, so every number in it can be traced.
7. **Run order** (`scripts/night_runs.sh`): Semiurban ML; both main loops again (to save firings); seeds 8 and 9; margin factor 1.25 and 2.0. Sequential, because parallel runs slowed each other in earlier steps.

## Results as they arrive

- **Semiurban ML, SE-residual features** (`ml_detectors_physics_semiurban.md`):
  - autoencoder: 14.9 % false alarms per benign record (61 episodes); detects drift-off 6/9, control-and-freeze 4/5, industroyer 7/9;
  - Isolation Forest: 0.3 % false alarms, drift-off 4/9;
  - SE-BDD: 0 false alarms.

  Interpretation: even physics-informed ML, calibrated on one train day, degrades under the test day's unseen topologies. Decision: keep the autoencoder as an alert source in the comparison table, but report its false alarms plainly. Its threshold is not tuned on test.
- **Semiurban ML, raw features** (`ml_detectors_raw_semiurban.md`): the autoencoder alarms on 86 % of benign records. This replicates the 01-Basic finding (99.99 %) on the second grid: ML on raw telemetry flags benign operating change.
- **01-Basic consolidation rerun** (now saving per-record firings): identical to the earlier run (library drift-off 4/4, control-and-freeze 4/5, industroyer 2/7, false alarms 0.00165), so the loop is reproducible.
- **Comparison table, first build:** 01-Basic, detectors or library: control-and-freeze 5/5, drift-off 4/4, industroyer 3/7, mean delay 68 s, false alarms 0.00171. Semiurban, library with persistence: control-and-freeze 4/5, drift-off 6/9 at 0.00401.
- **Methodological correction:** the first table credited the library with detections from rules learned during the same attack, from that attack's own alert. A strict variant now counts only rules learned before the attack starts. Script 14 saves per-rule firings; the seed and ablation runs pick this up; the main 01-Basic run is repeated after the chain. Both variants are reported.
- **Semiurban combinations:** the autoencoder's 14.9 % false alarms dominate any union that includes it, so the table reports "SE-BDD or library" and "SE-BDD or AE or library" side by side. Which alert sources are acceptable is a deployment choice; the table shows its cost.
- **Seed 8, 01-Basic physics-informed autoencoder:** identical to seed 7 (control-and-freeze 4/5, drift-off 3/4, industroyer 2/7, false alarms 0.00100).
- **Seed 8, 01-Basic consolidation:** identical per-type library detection (drift-off 4/4, control-and-freeze 4/5, industroyer 2/7) and false alarms 0.00165.
- **Seed 8, Semiurban on-demand library:** identical to seed 7 (with persistence: control-and-freeze 4/5, drift-off 6/9; false alarms 0.00401). The margins are dominated by train noise, not by the search seed.
- **Seed 9, 01-Basic autoencoder:** {'arp-spoof:arp-spoof-dos': '0/2', 'control-and-freeze:control-and-freeze': '4/5', 'drift-off:drift-off': '3/4', 'industroyer:industroyer': '2/7'} FA 0.00100 episodes 9
- **Seed 9, 01-Basic consolidation:** {'industroyer:industroyer': [7, 2, 2, 3], 'drift-off:drift-off': [4, 3, 4, 4], 'control-and-freeze:control-and-freeze': [5, 5, 4, 5], 'arp-spoof:arp-spoof-dos': [2, 2, 0, 2]} library FA 0.00156 354s
- **Seed 9, Semiurban library:** {'arp-spoof:arp-spoof-dos': [6, 1, 2, 2, 2], 'control-and-freeze:control-and-freeze': [5, 3, 5, 4, 4], 'drift-off:drift-off': [9, 4, 7, 6, 6], 'industroyer:industroyer': [9, 0, 7, 0, 0]} library FA 0.01621 with persistence 0.00401 detector FA 0.00000 141s
- **Margin factor 1.25, 01-Basic:** {'industroyer:industroyer': [7, 2, 0, 2], 'drift-off:drift-off': [4, 3, 0, 3], 'control-and-freeze:control-and-freeze': [5, 5, 0, 5], 'arp-spoof:arp-spoof-dos': [2, 2, 0, 2]} library FA 0.00000 372s
  - **Finding: margin factor 1.25 makes the grid-wide invariant rules uncertifiable.** Their robust exact-layer bound is the safety factor (1.25) times the oracle bound, so a margin of 1.25 times the same bound never exceeds it. Every G rule ends "inconclusive"; only the 3 state rules certify (their atoms carry no model error). The margin factor must exceed the bound safety factor. The default 1.5 keeps a 20 % gap. Documented as a design constraint, not tuned.
- **Margin factor 1.25, Semiurban** (search-only certificates, so no bound-safety conflict): {'arp-spoof:arp-spoof-dos': [6, 1, 6, 3, 3], 'control-and-freeze:control-and-freeze': [5, 3, 5, 4, 4], 'drift-off:drift-off': [9, 4, 7, 6, 6], 'industroyer:industroyer': [9, 0, 7, 0, 0]} library FA 0.03016 with persistence 0.00662 detector FA 0.00000 175s
- **Margin factor 2.0, 01-Basic:** {'industroyer:industroyer': [7, 2, 2, 3], 'drift-off:drift-off': [4, 3, 4, 4], 'control-and-freeze:control-and-freeze': [5, 5, 4, 5], 'arp-spoof:arp-spoof-dos': [2, 2, 0, 2]} library FA 0.00150 327s
- **Margin factor 2.0, Semiurban:** {'arp-spoof:arp-spoof-dos': [6, 1, 2, 2, 2], 'control-and-freeze:control-and-freeze': [5, 3, 5, 4, 4], 'drift-off:drift-off': [9, 4, 7, 6, 6], 'industroyer:industroyer': [9, 0, 7, 0, 0]} library FA 0.00837 with persistence 0.00174 detector FA 0.00000 142s
- Chain finished: all 14 steps returned 0. Next: rerun the main 01-Basic loop to save per-rule firings (strict library evaluation), then the final comparison.
- **Decision on the margin factor:** 2.0 lowers Semiurban false alarms (0.00174 against 0.00401 with persistence) with the same detection, and on 01-Basic gives the same detection with 0.00150 against 0.00165. The default stays 1.5: it was fixed before these runs, and switching after seeing test results would be tuning on test. The paper reports the sensitivity and the lower bound (the margin factor must exceed the 1.25 bound safety factor).
- **Strict library evaluation after the main rerun** (`comparison.md`, 01-Basic): the library alone, counting only rules learned before each attack, catches control-and-freeze 4/5, drift-off 4/4, industroyer 2/7, mean delay 102 s. Counting rules active at the time, industroyer is 3/7 and the delay 70 s. Both are reported.

## Step E: final reports

- Professional report for the paper: `paper_report.md` (methods in `paper_report_methods.md`).
- Plain-language process report with diagrams (Hebrew): https://claude.ai/artifact/UuRGHk2nuWXgwp7g9D1HE5 ; beginner explainer: https://claude.ai/artifact/G1HnjmCZb98W2pX8fnp5gE
- Final assessment (judgement): IEEE TSG about 61 %, IJEPES about 75 %. Main remaining weaknesses: one test day, empirical error bounds, modest gains over the classic detector.

## WP3: 03-Rural (owner approved the download)

- Download 03-Rural.zip (1.87 GB) with md5 check; extract without pcaps, control-center notifications and host logs (same as 02-Semiurban).
- Disk: deleted the already extracted and md5-verified 02-Semiurban.zip (6.4 GB); it can be downloaded again with `scripts/00b_download_semiurban.sh`.
- Plan: apply the 02-Semiurban pipeline unchanged where possible (identify additions to the SimBench base from data, validate the reconstruction, envelope, SE-BDD, ML, on-demand certified library, comparison). Every deviation is logged here.
- **Code generalised for SimBench-based grids** (`semiurban_model.SPECS`, `envelope` grid `rural`, `sherlock_io.root(name)`, `--grid` in scripts 15a, 15b and 16a). Index offsets (new buses, switches, transformers) are now derived from the SimBench base, not hard-coded. Regression check: the Semiurban model check reproduces exactly (voltage mean 2.80e-04, max 9.96e-04 pu).
- Expected Rural base: SimBench 1-MV-rural--2-sw (99 buses, 101 lines, 96 loads, 102 sgen, 90 storage, 204 switches), to be confirmed from the data.
- **03-Rural has no train day** (only test) and its first attack comes 0.65 h into the day. Its grid is exactly SimBench 1-MV-rural--2-sw (99 buses, 101 lines, 2 transformers, 96 loads, 102 sgen, 90 storage, 204 switches); no additions.
- **Decision: run 03-Rural as a zero-training transfer experiment.** Nothing is calibrated on Rural data; labels are used only for evaluation.
  - Envelope from public SimBench planning profiles: per-load P and Q ranges of its profile, widened by 0.05. The margin is justified on Semiurban, where monitored train loads exceed their SimBench profile range by at most 0.046 (29 of 75 loads exceed it; Sherlock scales profiles slightly).
  - SE-BDD threshold and persistence, and the library's per-kind noise floors, transferred from 02-Semiurban (same dataset family and noise process).
  - Topologies certified on demand.
  - ML has nothing to train on. It is trained on the first 30 minutes of the test day only (attack-free; first attack at 39 min), evaluated after that prefix, and reported as a weak baseline with this caveat. 30 minutes was fixed before results.
- **Rural reconstruction** (`rural_identify.md`, `rural_model_check_test.md`): no additions; fitted transformers match SimBench (25 MVA, vk 11.99 against 12.00 %). Validation on test ground truth: voltage mean 2.86e-04, max 1.01e-03 pu (noise floor 5.0e-04).
- **Rural envelope** (`rural_envelope.md`): SimBench profile P ranges widened by 0.05 cover 100 % of monitored benign load P. SimBench qload profiles cover only 10 % of benign Q (worst excursion 1.37). Decision: transfer Q bounds from the Semiurban train recording (Q / nominal over all loads, widened by 0.05). Coverage is then 90.4 % (worst excursion 0.13). Not widened further: that would be tuning on Rural.
- **Rural SE-BDD, calibration transferred from Semiurban** (`se_bdd_rural.md`): drift-off 5/9, control-and-freeze 0/5, industroyer 0/8; false alarms 0.00017 per benign record, all 13 test topologies handled on demand.
- **Rural certified library, attempt 1** (per-kind noise floors transferred from Semiurban; kept as `semiurban_consolidation_perkind_rural.md`): detects nearly everything but has 0.723 false alarms per benign record with persistence. Diagnosis: Rural's transformer flow residuals reach 19 sigma (99th percentile) against a transferred floor of 0.47; the overall residual stays below the transferred SE-BDD threshold (99th percentile 25.5 against 170).
- **Attempt 2, decided after attempt 1 failed:** without own noise data, every margin is at least the transferred global SE-BDD threshold (`--noise-mode global`). The global threshold transferred well; per-measurement noise did not. Both attempts are reported.
- **ML on Rural:** the first run crashed (script 13 treated only Semiurban as a SimBench grid). Fixed and rerun.
- **Rural results, attempt 2** (`comparison.md`, 03-Rural section):
  - Library with persistence L = 3: identical to SE-BDD (control-and-freeze 0/5, drift-off 5/9, industroyer 0/8; false alarms 0.00017). Margins at the transferred global threshold make the library no more sensitive than the detector.
  - Library, single record: control-and-freeze 1/5, drift-off 5/9, industroyer 3/8 at 0.00087.
  - ML trained on the first 30 minutes: autoencoder with SE features 5/5, 8/9, 4/8 at 0.144; Isolation Forest 3/5, 5/9, 1/8 at 0.00087; raw autoencoder 0.432 false alarms.
- **Lesson from the transfer experiment:** a detector's global threshold transfers between grids of the same dataset. Per-measurement certified margins need the grid's own noise calibration; without it the library either floods with false alarms (attempt 1) or adds nothing over the detector (attempt 2). For the paper: a deployment needs a short benign calibration period on each grid for the library's noise term. The physics certificate itself transfers (on-demand certification needs no data).
- **Final reports updated with 03-Rural:** `paper_report.md` (professional) and the Hebrew process report (same link). Assessment (judgement): IEEE TSG about 62 %, IJEPES about 76 %.

## WP4: the remaining recommendations (owner: "continue with an additional test day and all other recommendations")

| Step | What | Why / decision |
| --- | --- | --- |
| 4a | Wilson confidence intervals for detection rates; exact McNemar tests (paired, per attack instance) between methods | few instances per type; the tables had no uncertainty |
| 4b | Probabilistic error bound for the linearised model (scenario approach): with confidence 1 - beta, the probability that a uniformly drawn benign envelope state has error above the sample maximum is below epsilon = ln(1/beta) / N | a fully formal worst-case bound is out of reach for an AC remainder over a 51 to 481 dimensional box; a scenario bound is provable and standard; it complements the adversarial search (empirical worst case) |
| 4c | 03-Rural with a short benign calibration period: the first 30 minutes of its test day (attack free) calibrate the library's per-measurement noise | the transfer experiment showed this is what the library lacks |
| 4d | Additional, independent test day: Sherlock has only one test day per scenario. A semi-synthetic test day is built from the second half of each train day (01-Basic, 02-Semiurban), with attacks injected into the recorded telemetry, and every calibration (detectors, ML, noise, envelope) redone on the first half only | gives a second evaluation day with known ground truth and no overlap with calibration data; injection follows the attack anatomy measured on the real test day |
- **4a result** (`statistics.md`):
  - Pooled over 61 process-attack instances: classic 22/61 = 0.36 [0.25, 0.49]; certified library 25/61; combined 27/61 = 0.44 [0.33, 0.57].
  - Exact McNemar test, combined against classic: 5 instances detected only by the combined system, 0 only by the classic; p = 0.062. Per grid, no difference is significant (p from 0.25 to 1.0).
  - Reported as a consistent but not statistically established advantage. No change to methods because of this.
- **4b result** (`scenario_bound.md`): 20,000 independent benign states per grid. Every delta used by the robust exact layer is at least the sample maximum (voltage: 0.00367 and 0.00436 pu against delta 0.00885 and 0.01042). With confidence 0.999, a new benign state exceeds delta with probability at most 3.45e-04. Stated in the paper as a probabilistic guarantee relative to the uniform envelope distribution, not a worst-case proof.
- **4c result** (`semiurban_consolidation_cal30_rural.md`): calibrating the Rural library's per-measurement noise on the first 30 minutes of the test day (attack free; not evaluated) cuts false alarms from 0.723 (attempt 1) to 0.184 with persistence. Detection: control-and-freeze 5/5, drift-off 8/9, industroyer 4/8. Still unusable: 30 minutes covers too little operating variety (later topologies and load levels). Conclusion: the library's noise term needs a representative benign period (a day, as on 01-Basic and 02-Semiurban). Longer calibration is not possible on Rural without using labels (the first attack comes at 39 minutes).
- **4d design** (`scripts/22_split_day.py`, `split_day.md`): each recorded train day (01-Basic, 02-Semiurban; 12 h, attack free) is split at its midpoint. The first half is the new train split, and every calibration is redone on it: envelope, D1, SE-BDD, ML, library noise. The second half is the new test split. Attacks are injected into its recorded telemetry:
  - drift-off: ramp on bus-voltage readings;
  - control-and-freeze: freeze of an area's telemetry, optionally with a line opened behind it;
  - industroyer: a line opened or generators disconnected.
  Physical changes are injected as an AC power-flow delta (with change minus without) on the nearest ground-truth snapshot, so recorded noise and model mismatch are kept. Scripts run unchanged under `P3_VARIANT=split`: data root `data/split/<grid>`, suffix `_split` on interim files, reports and libraries. The linac error bounds are reused: a first-half envelope is a subset of the full one (min and max over a subset of the same records), so bounds certified over the full envelope remain valid.
- **4d, attack model v1** (guessed parameters; `*_split_v1` files): drift 0.005 to 0.05 pu (log-uniform); 3-bus frozen area.
  - 01-Basic: D1 drift-off 7/7, control-and-freeze 6/8, industroyer 0/8 (false alarms 0.00057). Library (learned earlier) 4/7, 5/8, 1/8 at 0.0103.
  - 02-Semiurban: SE-BDD 0/7, 0/7, 0/7. Library with persistence 3: 7/7, 7/7, 0/7 at 0.00000. McNemar 14 against 0, p < 0.001.
  - Finding 1, envelope coverage. At 14,017 s into the 01-Basic test half, a benign operator command ("Manual Commands") moves transformer 0 to tap -1, a position never seen in the first half. From then on every alert is "outside envelope" and nothing is synthesised. Kept as the primary result.
  - Sensitivity variant `split_tappad`: tap range padded by one step beyond the positions seen. Envelope not a subset of the full one, so the linac bounds were re-validated for it (`linac_error_sherlock_split_v1_tappad.md`: delta vm 0.0111 against 0.0104 full). Result: the tap -1 topology is certified at 14,017 s; library 6/7 drift-off, 8/8 control-and-freeze at 0.0112.
- **4d, attack model v2**, decided after v1 because v1's magnitudes were a guess:
  - SE-BDD peaks on the real Semiurban drift-offs reach 4.2 x theta; in v1 at most 0.57.
  - `scripts/22a_drift_magnitude.py` measured the real drift-offs (reported minus ground-truth voltage, `drift_magnitude.md`). They are bimodal: either 0.036 to 0.39 pu on 1 to 6 buses, or about 0.0015 pu (no visible drift).
  - v2 draws each instance's magnitude (+-20 %) and bus count from a measured real instance of the same grid.
  - The control-and-freeze area grows to 10 buses on 02-Semiurban: in v1 a 1-bus freeze was typical, while a real RTU freeze covers many points.
  - v2 is the main split-day result. v1 is reported as a weak-attack sensitivity case. This choice follows the anatomy of the real attacks, not the v1 detection numbers. The v1 numbers favoured the library (14 against 0).
