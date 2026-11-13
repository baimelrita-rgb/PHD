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
