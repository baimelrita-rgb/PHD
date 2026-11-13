# WP2-b status: 02-Semiurban pipeline, findings that change the design

Numbers are copied from `semiurban_envelope_semiurban.md`, `semiurban_identify.md` and the checks described below.

## Finding 1: partial observability

The control center's telemetry (IPAL state, vantage n406) has no data for 47 of 122 loads, 47 of 123 DER, 47 of 114 storage units, 50 of 178 bus voltages, 46 of 126 lines and 96 of 360 switches. All 58 transformers are monitored.

Checked against ground truth (200 snapshots per split):

- Loads with the same SimBench profile scale almost identically (train spread at most 0.0035 of nominal), so pseudo-measurements from monitored loads of the same profile are accurate.
- DER do not follow their profile strictly (spread up to 0.40) and storage is dispatched per unit (spread 1.0), so neither can be estimated from profiles.
- Unmonitored switches never change state in train or test; that part of the topology is known configuration.

Consequence: the physics residual (D1), the invariant rules and the oracle all assumed every injection is metered. That does not hold here.

Proposed design: state estimation. Each new 0.63 MVA transformer is monitored and carries exactly one DER and one storage unit, so their sum is measured. With the monitored voltages and flows, unmonitored DER and storage can be estimated by least squares, and the measurement residual of that estimate is the classic bad-data detection test. That test is also the baseline a TSG reviewer expects.

## Finding 2: topology envelope from train does not generalise on a large grid

| Item | Value |
| --- | --- |
| distinct line-outage topologies in train | 7 |
| benign test records whose topology is in the train set | 924 of 5,736 (0.161) |
| distinct benign test topologies not seen in train | 10 |
| benign test records with every monitored continuous parameter inside the bounds | 3,998 of 5,736 (0.697), to be diagnosed |

The test day runs benign reconfigurations (Close Ring, Open Ring, separator movement, maintenance) into topologies never seen in train.

Proposed design:

- Define the topology envelope structurally, as "connected, at most one closed loop", rather than enumerating it.
- Certify on demand: when a new topology appears, the oracle certifies the library's rules for it before they act.

Grid-wide invariant rules are already bound to one topology each, so they fit this naturally. State rules use the structural membership test.

## Done in this step

- The pipeline is generic across grids. The dataset follows the grid; interim and report files carry the grid name; the residual model builds either reconstructed grid; Semiurban topologies are given as lists of lines out; storage nominal handles SimBench's negative sign.
- The Semiurban envelope comes from train data, with unmonitored loads bounded by their profile group (`semiurban_envelope_semiurban.md`).
