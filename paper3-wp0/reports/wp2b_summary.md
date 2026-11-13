# WP2-b summary: partial observability and on-demand certification on 02-Semiurban

Numbers are copied from `se_bdd_semiurban.md`, `semiurban_consolidation_semiurban.md` and `semiurban_envelope_semiurban.md`.

## What was built

1. **State estimation under partial observability** (`src/p3/state_est.py`).
   - Linear WLS for each topology, built on demand for any topology, including ones never seen in train.
   - Inputs: monitored voltages, flows, transformer powers and injections (load Q included); pseudo-measurements for unmonitored loads from monitored loads of the same SimBench profile; a weak prior.
   - Then Gauss-Newton corrections against the full AC model.
   - De-energised buses (planned-outage islands) and the lines touching them are excluded.
2. **SE-BDD detector** (`scripts/17_se_bdd.py`): the classic bad-data detection residual, normalised by measurement noise, with a threshold from train and a persistence filter.
3. **On-demand certification** (`scripts/18_semiurban_consolidation.py`).
   - Rule per topology: some monitored measurement's residual exceeds its own margin.
   - Margin = 1.5 x max(train noise with a per-kind floor, oracle bound).
   - When a topology first appears in the telemetry, the oracle certifies its rule before the rule acts; CEGIS raises margins on counterexamples.
   - The residual needs AC power flows, so only the search layer applies: the certificate is AC-validated, not formal.
4. **Infrastructure fixes** found on this grid:
   - a sparse Newton-Raphson solver (7.9 ms instead of 81 ms per power flow);
   - initial voltage on isolated buses (was NaN);
   - bus couplers in the topology graph;
   - load reactive power as its own envelope parameter (it follows its own profile, from -0.10 to 2.54 of nominal);
   - unmonitored telemetry read as NaN.

## Results (test day; every 5th record)

| Detector or library | control-and-freeze | drift-off | industroyer | false alarms per benign test record |
| --- | --- | --- | --- | --- |
| SE-BDD detector | 3/5 | 4/9 | 0/9 | 0.00000 |
| Certified library, single record | 5/5 | 7/9 | 7/9 | 0.01586 |
| Certified library, same persistence as the detector (L = 3) | 4/5 | 6/9 | 0/9 | 0.00401 |

- All 13 test topologies were certified on demand, 12 of them never seen in train. Latency per topology: median 5 s, max 11 s. This replaces the 16 % coverage of the train-only topology envelope.
- 2 % of test records (178 of 8,642) have a non-line switch open and are not covered.

## Findings, in the order they appeared

1. About 40 % of elements have no telemetry; that part of the grid needs state estimation.
2. A linear estimate is not enough: its linearisation error (normalised residual about 12 on benign states) hides small falsifications. One Gauss-Newton step against the AC model brings benign residuals to about 0.06 on synthetic states.
3. Real telemetry first gave residuals of 72 to 86 sigma. The cause was load reactive power, which varies on its own profile and had been modelled as fixed.
4. The first SE-BDD version had 22 % false alarms, all from one de-energised bus (voltage 0 in a maintenance island). Excluding de-energised buses brought them to 0.
5. Library margins first used per-measurement train maxima. A line that is idle in every train topology got margin 0 and caused false alarms once a new topology loaded it. A per-kind noise floor fixed this (from 7.9 % to 1.6 % single-record false alarms).

## Limits

- On Semiurban the certificate is search-based (AC-validated), not formal; the exact layer cannot express the iterated residual.
- Even with persistence, the library's false alarms (0.4 %) are above the detector's (0 %).
- Industroyer is caught only without persistence, from switching transients, so the claim needs care.
- Every 5th record was used, to stay within the 10-minute limit per script.
