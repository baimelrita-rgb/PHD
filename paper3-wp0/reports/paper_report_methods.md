# Methods (draft for the paper)

Working title: *From Alerts to Certified Rules: Self-Consolidating Intrusion Detection for Power Grids*.
Every number cited in the results comes from a generated report in `reports/`. This file holds the method text.

## 1. Problem and idea

An anomaly detector (physics-based or ML) watches the control center's telemetry and raises alerts. Each alert is turned into deterministic detection rules. A rule enters the library only after a **physics oracle** has searched for a benign, physically feasible operating state that would trigger it (a false alarm) and found none. Counterexamples go back to the synthesizer (counterexample-guided refinement). The library grows with every incident, and later attacks can be caught by certified rules, sometimes when the detector misses them.

## 2. Grids and data

- **Sherlock 01-Basic** (Zenodo 18467070): CIGRE MV, 15 buses, fully monitored, one train day without attacks, one test day with control-and-freeze (5), drift-off (4), industroyer (7) and arp-spoof-dos (2; excluded from the process-attack evaluation).
- **Sherlock 02-Semiurban**: SimBench 1-MV-semiurb--2-sw extended to 178 buses, 58 transformers and 360 switches; about 40 % of elements have no telemetry; test day with industroyer (9), drift-off (9), control-and-freeze (5) and arp-spoof-dos (6).
- Neither download contains a grid model. Both models were **reconstructed from data**:
  - switch mapping;
  - transformer impedances and iron losses fitted to recorded losses;
  - the tap changer identified on held-out snapshots;
  - for Semiurban, 56 DER-plus-storage transformer groups found from the IEC 104 point map and bus power balances.

  Both reconstructions reproduce recorded voltages at the measurement noise floor (mean error about 2.7e-4 pu).

## 3. Benign envelope

The benign envelope is the set of operating states the oracle may use as counterexamples:

- load profiles within their train range plus a margin;
- controllable DER and storage over their physical range;
- load reactive power on its own range where the data show it varies;
- topologies: enumerated radial and one-loop configurations (01-Basic, 336), or structurally defined and certified on demand (Semiurban);
- operating limits: bus voltage in [0.90, 1.10] pu; line and transformer loading at most 100 %.

## 4. The physics oracle

**Search layer.** Latin hypercube sampling and differential evolution maximise the rule margin over benign AC states. It uses a fast Newton-Raphson solver on pandapower's own admittance matrices, dense for small grids and sparse for large ones, identical to pandapower to 1e-10.

**Exact layer.** Z3 in linear real arithmetic, with the envelope, a linear power flow model and the rule:
- LinDistFlow, radial only; or
- a linearised AC model (first-order expansion at the envelope centre), which covers meshes.

The robust encoding replaces each AC condition by the weakest linear condition it implies under validated model-error bounds delta. Delta is found by adversarial search with a 1.25 safety factor; rule-specific bounds are used for linear rule expressions. UNSAT in the robust encoding means "no benign counterexample, provided the linear-to-AC error stays within delta". Constraints implied by the parameter box are pruned exactly.

**Refinement.** On a counterexample, a threshold rule is tightened, and an invariant rule's margin follows the synthesis rule (1.5 x max(noise, updated bound)).

## 5. Detectors (alert sources)

- **D1, full observability:** the AC power flow from metered injections versus reported voltages and flows.
- **SE-BDD, partial observability:**
  - WLS state estimation per topology (linearised AC), with monitored measurements, pseudo-measurements for unmonitored loads from same-profile loads, and a weak prior;
  - one Gauss-Newton correction against the full AC model;
  - the normalised residual is the bad-data detection statistic;
  - de-energised buses are excluded.
- **ML:** an autoencoder (MLP 64-12-64) and an Isolation Forest, each on raw telemetry or on physics-informed features (residual vectors plus rates of change). Fit on the first 75 % of train, calibrated on the last 25 %.
- **Calibration:** all thresholds come from train only (no attacks), with a persistence filter.

## 6. Rule synthesis from alerts

- **Physical invariant:** reported quantity minus the linearised AC prediction from metered injections, for the alert's topology. The margin is the larger of the oracle bound on benign AC residuals and the train noise. The grid-wide variant has one clause per bus voltage and line flow.
- **State rule:** a discrete change seen during the alert (a line out, a load or DER to zero). The oracle decides whether that state exists in the benign envelope.
- **Semiurban:** a per-topology state-estimation residual rule, certified on demand when the topology first appears (search layer only).

## 7. Self-consolidation loop

- The test day is replayed in time order, with alerts from detectors only (no labels).
- Episodes already covered by the library skip synthesis; others synthesize, certify and add rules.
- A rule acts only after the time it was learned.
- Labels are used only afterwards, for evaluation.
