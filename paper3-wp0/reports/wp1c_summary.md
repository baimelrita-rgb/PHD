# WP1-c summary: rules synthesized from alerts, certified by the oracle

Numbers are copied from `synthesis_sherlock.md` and `attack_anatomy.md` (Sherlock 01-Basic test, reconstructed grid).

## Attack anatomy (what each attack does to the telemetry)

Telemetry compared with ground truth, against a benign control baseline (`attack_anatomy.md`):

- drift-off: falsifies bus voltages (16 to 32 times the benign deviation rate); no real state change.
- control-and-freeze: falsifies switch states, voltages, flows and powers; the real grid does change.
- industroyer: changes the real grid (switches opened, a load or DER disconnected); telemetry stays consistent.

## Method

- **Alert.** 60 s of telemetry from the first D1 physics-residual alarm in the window, or from the attack start when D1 does not fire (stand-in for another detector). The synthesizer sees only the alert, the 30 s before it, train telemetry and the oracle.
- **Family P, physical invariant.** For the topology at the alert: reported voltage or flow minus the linearised AC prediction from the metered injections.
  - Margin = 1.5 x max(oracle bound on the benign AC residual, train noise level).
  - The quantity whose alert residuals best exceed the margin is chosen.
- **Family S, state rule.** The discrete change from before the alert: a line out, or a load or DER at zero.
- **Certification.** Joint DE search and the robust exact layer (linearised AC, rule-specific bound); CEGIS on the margin.

## Results (19 test attacks)

| Type | Instances | At least one certified rule | Certified rule fires on the rest of the window |
| --- | --- | --- | --- |
| drift-off | 4 | 3 | 3 |
| control-and-freeze | 5 | 3 | 3 |
| industroyer | 7 | 3 | 3 |
| arp-spoof-dos (excluded from G2) | 2 | 0 | 0 |

- Candidates: 12 certified, 2 refuted (both industroyer state rules "DER to zero": a DER at zero output is a benign state), 7 attacks without a candidate.
- False alarms of the certified rules: at most 0.0003 per benign test record, 0 on train.
- Generalisation to other instances of the same type is low (0 or 1 of 3 to 6). Rules are bound to the topology and the falsified element of their alert. This is what WP1-d's growing library has to address.

## Findings

1. **Industroyer is reachable after all.** Physics consistency misses it, but a state rule ("this state is outside the benign envelope") can be certified for 3 of 7 instances, for example an islanded bus or a disconnected load. The 3 instances without a candidate (setpoint change, closing switches that are already closed) leave no trace in a snapshot. They would need temporal or command-level context.
2. **The certificate and noise are different things.** A first run, with noise estimated from about 100 train records, certified a rule that fired on 31 % of benign test records. The certificate covers benign *physical* variation; telemetry noise and asynchrony need their own, adequately sampled calibration. With a global train noise floor the false alarms fall to at most 0.0003.
3. **Alert timing matters.** With alerts at the attack start, drift-off gave no candidate (the drift is still small). Alerts at the detector alarm give 3 of 4.
4. **The oracle refutes plausible-looking rules.** "DER to zero" looks like an attack signature but is benign-feasible, and the oracle rejects it.

## Limits

- Physical-invariant certificates hold by construction once the margin exceeds the validated residual bound. The oracle's role there is to compute that bound and to check it with an independent search.
- A single test day; few instances per type.
