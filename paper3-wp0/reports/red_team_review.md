# Red-team review: three simulated reviewers, each looking for the strongest reason to reject

Each reviewer was asked for the single argument most likely to sink the paper, and for what would neutralise it. Where the argument could be tested, it was tested; the numbers come from generated reports, named in brackets.

---

## Reviewer A: power systems

**Strongest argument for rejection.** "The telemetry is a synchronous snapshot of a steady-state, single-phase co-simulation. Real SCADA reports with latency, cyclic and spontaneous transmission, and deadbands. Physics-consistency rules calibrated on simulator telemetry will drown in false alarms on a real control-centre feed. The paper never tests this."

**Test.** The library learned on the recorded 01-Basic day was replayed, unchanged, on benign test telemetry with realistic reporting artifacts on every analog reading [red_team_sherlock.md]:

| Artifact | Library false alarms per benign record | Process attacks detected |
| --- | --- | --- |
| none (recorded telemetry) | 0.00056 | 11/16 |
| latency 0 to 1 s per measurement | 0.03464 | 14/16 |
| latency 0 to 2 s | 0.06699 | 14/16 |
| latency 0 to 5 s | 0.06787 | 14/16 |
| deadband 0.5 % of training range | 0.17824 | 14/16 |
| deadband 1 % | 0.26528 | 15/16 |
| deadband 2 % | 0.37909 | 15/16 |

**Verdict: the argument holds for a library calibrated on clean telemetry.** One second of latency multiplies false alarms by 60; a 1 % deadband makes the library unusable. The certificate is not at fault (it concerns physics); the noise margins are, because they never saw reporting artifacts.

**What neutralises it, and whether it does.** In deployment the training day is recorded through the same SCADA system, so noise calibration sees the same artifacts. Test: artifacts applied to the training day as well, then the whole loop rerun (calibration, synthesis, certification, evaluation) [consolidation_tc_lat2_sherlock.md, consolidation_tc_db1_sherlock.md]. Result:

| Artifact (in training and test) | Library false alarms, calibrated on clean telemetry | Library false alarms, calibrated with the artifact | Process attacks detected (detectors or library) |
| --- | --- | --- | --- |
| deadband 1 % | 0.26528 | **0.00056** (as on clean telemetry) | 12/16 (as on clean telemetry) |
| latency 0 to 2 s | 0.06699 | **0.01004** | 12/16 |

A deadband is fully absorbed by calibration. Latency is reduced by a factor of 6.7 but stays 18 times above the clean level: when readings lag by different amounts, they disagree during every ramp, and a consistency rule sees that. **Revised verdict: partly neutralised.** Deployment needs either time-aligned telemetry (synchronised timestamps, as IEC 104 provides with CP56Time2a time tags) or a latency-aware margin; the paper must say so.

**Also raised, not tested.** Three-phase unbalance and measurement asynchrony across RTUs beyond the 5 s tested; PMU-grade data would change the noise floor.

---

## Reviewer B: cybersecurity and formal methods

**Strongest argument for rejection.** "An attacker who knows the library falsifies every reading by slightly less than its margin and is never detected. And a physically consistent false-data injection (Liu, Ning and Reiter) that falsifies injections and network quantities together is invisible to any consistency rule. The certificate guarantees the absence of false alarms, not the presence of detections."

**Test (stealth budget).** The margin of every voltage and line-flow clause of every grid-wide rule was recovered from the stored library [red_team_sherlock.md]:

| Quantity | Clauses | Smallest margin | Median margin | Largest margin |
| --- | --- | --- | --- | --- |
| bus voltage | 112 | 0.0020 pu | 0.0073 pu | 0.0264 pu |
| line active power | 110 | 0.0000 MW | 0.33 MW | 0.93 MW |

**Verdict: the argument is correct and must be stated, not refuted.** A falsification of a single voltage reading below about 0.007 pu (median) evades the library. The real drift-off attacks on this grid moved a reading by 0.036 to 0.38 pu, or by about 0.0014 pu (the near-zero instances, which no method detected). The library therefore covers the attacks that matter physically while leaving a stealth band of the order of 1 % of nominal voltage; the near-zero margins on line power belong to lines out of service in the rule's topology, where the predicted flow is exactly zero. A coordinated, physically consistent injection is outside the reach of every consistency check, classic or certified; the paper says so in its scope paragraph.

**Also raised.** (1) Soundness of the SMT step: Z3 decides linear real arithmetic exactly over rationals, and floating-point model coefficients are converted exactly; the approximation is in the linearisation, covered by δ. (2) Poisoning of the online calibration: discussed in Section VII; the margin can only grow, so poisoning buys stealth, never false alarms.

---

## Reviewer C: machine learning

**Strongest argument for rejection.** "The machine-learning baselines are straw men: an autoencoder trained on one day of raw telemetry is bound to fail. Without strong learned baselines the advantage of certified rules is not shown."

**Response with evidence.** (1) The paper's ML baseline is the physics-informed autoencoder (residual features), not the raw one; on 01-Basic it reaches 0.00100 false alarms, comparable to the library [comparison.md]. (2) The comparison with five published process-aware IDSs on the same test day, including a sequence-to-sequence neural network, uses the dataset authors' own numbers [sherlock_metrics.md]: Seq2SeqNN 7/18 detected, SIMPLE 16/18 at 33 false alarms, GeCo 15/18 at 94, against 14/18 at 10 for the combined system. (3) The claim is not that rules beat learning, but that learning should feed a certification gate: the learned detectors are the alert sources of the loop.

**Also raised.** (1) Multiple comparisons: the primary paired test (combined against classic) was fixed in advance; with a Holm correction over the four reported paired tests (p = 0.062, 0.00012, 0.00012, 0.00049) the three pooled tests remain significant at 0.05. (2) Hyperparameters: margin factor 1.5, alert window 60 s, persistence 3, calibration window 300 s were fixed before results; the one post-hoc change (attack model v2) is reported with v1 and with a 0.5× and 2× sweep.

---

## Summary for the authors

| Reviewer | Strongest argument | Status |
| --- | --- | --- |
| A, power systems | SCADA artifacts drown clean-calibrated margins | confirmed for clean calibration; see the retraining test above |
| B, security | stealth band below the margins; consistent FDIA invisible | confirmed and quantified; stated as scope |
| C, machine learning | straw-man ML baselines | answered with published IDS comparison and the physics-informed baseline |

## Outcome of the improvement round

| Reviewer | Argument | Outcome |
| --- | --- | --- |
| A, power systems | SCADA artifacts drown clean-calibrated margins | resolved by reporting-robust margins (clean false-alarm level under every emulated artifact) [robust_margins_sherlock.md] |
| B, security | stealth band below the margins | CUSUM failed its criterion; the band is set by model fidelity, stated as a limitation [cusum_tc_sherlock.md] |
| B, formal methods | search-validated SE rules are not a certificate | confirmed: benign corner counterexamples in every topology; replaced by an affine worst-case proof [se_rule_proof_semiurban.md, semiurban_consolidation_semiurban.md] |
| C, machine learning | published IDSs not run on identical data | SIMPLE rerun on identical unfiltered data (alarms continuously); GeCo did not finish training in 6 h |
