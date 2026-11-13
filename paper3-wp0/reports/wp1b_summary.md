# WP1-b summary: the physics oracle on the reconstructed Sherlock grid

Numbers are copied from the generated reports named in each row (grid suffix `_sherlock`).

## What was built

- A grid abstraction (`envelope.GridSpec`). The WP0 reference grid is unchanged: its search results reproduce exactly (only wall times differ).
- The Sherlock grid: CIGRE MV with all DER, 13 sgen, 2 storage units, 32 switches, transformer parameters and tap changer identified from data.
- A data-driven envelope (`rules/sherlock_envelope.json`):
  - load profiles: train range plus 0.01;
  - controllable DER and storage: their physical range;
  - taps: the positions seen in train;
  - topologies: connected, at most one closed loop, up to two lines out.
- Affine injections shared by the AC, LinDistFlow and Z3 layers; LinDistFlow with off-nominal taps.
- Joint differential evolution over the configuration index, and parallel Z3 queries.

## Results

| Item | Result | Source |
| --- | --- | --- |
| Discrete configurations | 336 (170 radial, 166 with one closed loop) | `sherlock_envelope_sherlock.md` |
| Envelope coverage, train | topology 43,204 of 43,204 records | `sherlock_envelope_sherlock.md` |
| Envelope coverage, benign test | topology 33,929 of 33,976; continuous 33,976 of 33,976 (tolerance 1e-3 for noise) | `sherlock_envelope_sherlock.md` |
| Benign meshed operation | test runs meshed for hours after maintenance (tie S2 never reopened); a radial-only envelope would be wrong | `sherlock_envelope_sherlock.md` |
| LinDistFlow error (radial) | 1,000 samples max 0.00707 pu; worst found 0.01207 pu; delta_vm 0.01509 pu | `lindistflow_error_sherlock.md` |
| R1 (threshold mined from train history) | refuted: 204 of 9,999 benign envelope samples fire; Z3 SAT; CEGIS drives tau to 0.89998 (below the 0.90 limit) | `oracle_search_sherlock.md`, `oracle_exact_sherlock.md`, `cegis_demo_sherlock.md` |
| R2 (context rule mined from train) | **certified** by the robust exact layer on all 170 radial configurations; no counterexample by search (32,000 flows) on all 336 | `oracle_exact_sherlock.md`, `oracle_search_sherlock.md` |
| R3 (power balance, margin by search) | no counterexample by search; exact layer inconclusive (transformer P error bound exceeds the margin) | same |
| Rules on recorded telemetry | R1 fires on 1.00 % of train records and 0 benign test records; R2 and R3 on 0 benign test records | `sherlock_rules_sherlock.md` |
| Runtime | search layer about 27 s per rule; exact layer 11 to 91 s per rule and mode | same |

## Reading

- A threshold mined from history (R1) is not safe: the envelope contains benign states that history never showed. Making it safe makes it useless. This is the argument for synthesis with context, not thresholds.
- A context rule (R2) can be certified, including under the model-error bound. This is the first robust certificate in the project.
- The exact layer covers only the radial half of the configurations. Meshed configurations rely on the search layer. A linearised AC model for meshes is the next modelling step.
