# WP1-d summary: detectors, ML, and the self-consolidation loop

Numbers are copied from `ml_detectors_physics_sherlock.md`, `ml_detectors_raw_sherlock.md`, `physics_residual_sherlock.md` and `consolidation_sherlock.md` (Sherlock 01-Basic test day).

## How alerts are produced

| Detector | Type | Input | Calibration (train only, no attacks) |
| --- | --- | --- | --- |
| D1 | physics model, not ML | per-second residual between reported and recomputed voltages and flows (AC power flow on the reconstructed grid) | threshold 2 x train 99.9th percentile; alarm when above it for L consecutive seconds |
| AE | ML, MLP autoencoder (64-12-64, scikit-learn) | physics-informed features: per-element residuals plus rates of change | fit on the first 75 % of train; threshold = 99.95th percentile on the last 25 %; persistence L |
| IF | ML, Isolation Forest (200 trees) | same features | same |

All detectors are unsupervised because train contains no attacks. Labels are never used in the loop; they are used only to evaluate it afterwards.

## Detector results

| Detector | drift-off | control-and-freeze | industroyer | false alarms per benign test record |
| --- | --- | --- | --- | --- |
| AE, raw telemetry features | 4/4 | 5/5 | 7/7 | 0.99988 (alarms almost always) |
| IF, raw or physics features | 0/4 | 0/5 | 0/7 | 0 (never alarms) |
| AE, physics-informed features | 3/4 | 4/5 | 2/7 | 0.00100 |
| D1 | 3/4 | 5/5 | 2/7 | 0.00059 |

Findings:
- ML on raw telemetry fails under benign operating change. Load profiles move during the day, and the test day has topologies and DER setpoints never seen in train. The raw autoencoder flags almost every benign record. This is a strong argument for physics-based, certified rules.
- With physics-informed features the autoencoder works, at about the level of D1.
- Isolation Forest never alarms: its scores saturate (calibration threshold 0.594), so states far outside the training range score like states just outside it.

## Self-consolidation loop

- Alerts: D1 or AE. Alarm runs closer than 120 s form one episode, 22 episodes in total.
- For each episode, if the library already fires in its first 60 s, nothing is synthesized (9 episodes).
- Otherwise rules are synthesized:
  - family G: one grid-wide invariant rule for the alert topology, with one clause pair per bus voltage and per line flow, each with its own oracle margin;
  - family S: state change.
- The rules are certified (search on the rule's topology, robust exact layer) and enter the library. A rule acts only after it was learned.

Final library: 10 rules (8 G, 2 S). Every G rule was certified; all 6 "line out" state candidates were refuted, because those reconfigurations are benign.

| Type | Instances | Detectors | Library, from rules learned earlier | Detectors or library |
| --- | --- | --- | --- | --- |
| drift-off | 4 | 3 | **4** | 4 |
| control-and-freeze | 5 | 5 | 4 | 5 |
| industroyer | 7 | 2 | 2 | 3 |
| arp-spoof-dos (excluded) | 2 | 2 | 0 | 2 |

- The library caught drift-off #23 and industroyer #11 with rules learned from earlier alerts; the detectors missed both.
- The library fired earlier than the detectors on 3 of the 4 control-and-freeze instances it caught, by 5 to 7 s.
- False alarms per benign test record: library 0.00165, detectors 0.00109.
- Runtime: 9.5 min, within the 10-minute limit.

## A correction made during this stage

A first version searched for counterexamples over all 336 configurations jointly. A grid-wide rule's own topology then received only about 1/336 of the budget, and some rules were "certified" by a search that never looked hard at them. With the search restricted to the rule's topology, it did find benign counterexamples. A second bug then appeared: after a counterexample, CEGIS set the margin below the robust layer's error bound, so the rules could not certify. Both are fixed: the search is concentrated, and the margin after a counterexample follows the synthesis rule (1.5 x max(noise, updated bound)). The final numbers above come from the corrected, stricter procedure.

## Limits

- One test day; the library is evaluated on the same day it learns from, in time order.
- Industroyer stays weak (3/7 with detectors and library together): setpoint changes and redundant commands leave no snapshot trace.
- The library's false alarm rate is slightly above the detectors' (0.00165 against 0.00109). Telemetry noise beyond the train maximum occasionally exceeds an invariant margin.
