# Improvement plan after two review rounds (pre-registered)

Goal: strengthen the paper where reviewers will push hardest, by changing the architecture where a weakness is structural and by adding experiments where the evidence is thin. Success criteria are fixed here, before any run, and every outcome (success or not) is reported.

## Where the paper is weakest (from both reviews and the red team)

| Weakness | Evidence | Reviewer impact |
| --- | --- | --- |
| W1. Margins break under reporting latency | calibrated on the same feed, 2 s latency still gives 1.0 % false alarms, 18× the clean level (`red_team.md`) | high: a power-systems reviewer will find it |
| W2. Partially observed grid: rules only search-validated | measured bound 0.46 % per rule (`se_rule_validation_semiurban.md`), not a proof | high: the review's "critical" point |
| W3. Comparison with published IDSs not under identical conditions | their numbers come from filtered data, ours from unfiltered | high |
| W4. Stealth band below the margins | voltage margin median 0.0073 pu; the six near-zero drifts on the additional days were missed by every method | medium |
| W5. Few attack instances, one injection seed | 42 injected instances from one seed | medium |
| W6. One simulator, no real control-centre data | all data from Wattson | high, but not fixable here |

## Feasibility checks already run

- W2: the state-estimation residual has an explicit affine form in the measurements (`state_est.SE.residual_affine`). On one 02-Semiurban topology (150 benign states), the gap between the full and the affine residual is a median 16 % of the rule margin, 88 % at the 95th percentile, and up to 5× the margin on a few measurements. A proof is likely for most measurements, not all.
- W3: the dataset group's IDS framework is public (github.com/fkie-cad/ipal_ids_framework, reachable); not on PyPI.
- W6: Docker and a TUN device are available, but the Sherlock scenario configuration is not public (see `decision_log.md`), so a new recorded day would need the scenario rebuilt; not planned.

## The plan

### A. Architecture

**A1. Reporting-robust margins (addresses W1). Priority 1.**
For an invariant $y - f(x)$ with $f$ affine, if every reading may lag by up to $\Delta$ seconds and is reported with deadband $b$, the extra residual is bounded:
$|e| \le \Delta(|\dot y| + \sum_k |a_k||\dot x_k|) + b_y + \sum_k |a_k| b_k$.
The control centre observes the rates (finite differences over the last $\Delta$ s), so each rule gets an online margin $m_t = m_{\text{static}} + \Delta \cdot \text{rate}_t$, plus the static deadband term. The physics certificate is untouched (it concerns $m_{\text{static}}$); the extra term covers reporting, by a derived bound, not a fitted one. $\Delta$ is a configuration value (the declared maximum reporting delay), not tuned on test. Applies to G and P rules on 01-Basic and to SE rules (through the affine form) on 02-Semiurban.
*Experiment:* rerun the Fig. 9 set (latency 1, 2, 5 s; deadband 0.5, 1, 2 %) and the clean day, with $\Delta$ = the latency of each scenario.
*Success (pre-registered):* with 2 s latency, library false alarms at most 0.2 % per benign record and process-attack detection (detectors or library) at least 11/16; on the clean day, detection unchanged (12/16) and false alarms at most 0.1 %.
*Risk:* sensitivity drops during fast ramps; attacks that ramp quickly could hide in them (measured and reported).

**A2. Proved rules under partial observability (addresses W2). Priority 2, with a gate.**
Replace the search-only certificate of SE rules by the same robust argument as on 01-Basic: the affine residual $R\,m_{\text{lin}}(x) + r_0$ is affine in the envelope parameters, so its maximum over the envelope box is closed-form; a validated bound $\delta_i$ on (full residual minus affine residual) is found by adversarial search (×1.25, as for the linearised AC model) and checked by the scenario argument. Measurement $i$ is *proved* when box maximum + $\delta_i \le m_i$.
*Gate:* run on all 13 topologies first; if fewer than 80 % of monitored measurements are provable at the current margins, report the fraction and keep search validation (no margin raising after seeing detections).
*Success:* at least 90 % of monitored measurements proved per topology; for the rest, either the margin is raised to the proof level or the measurement is left search-validated, and the detection change on the recorded and additional days is reported. Target: at most 1 instance lost.

**A3. Temporal accumulation on certified residuals (addresses W4). Priority 4.**
A CUSUM on each certified residual, normalised by its margin: $S_t = \max(0, S_{t-1} + |r_t|/m - \kappa)$, alarm when $S_t > h$, with $\kappa$ and $h$ calibrated on the training day only ($h$ = 1.5 × the largest training value). It detects sustained falsifications below the single-record margin. Its guarantee is calibrated, not certified, and is labelled so.
*Success:* at least 2 of the 6 near-zero drift-offs on the additional days detected, library false alarms increasing by at most 0.05 percentage points; the stealth budget for a sustained constant offset (smallest offset detected within 600 s) reported against the single-record margin.

### B. Experiments

**B1. Published IDSs on identical data (addresses W3). Priority 3. Needs the owner's approval** to download and run third-party code (the IPAL IDS framework).
Run the IDSs available in the framework that the dataset paper evaluated, on exactly our unfiltered 01-Basic test day and on the additional days, scored with the dataset paper's metrics; train each on the same training data we use.
*Success:* a like-for-like table. Whatever the ranking, it is reported.

**B2. Five injection seeds for the additional day (addresses W5). Priority 5.**
Regenerate the additional day with four more seeds per grid (210 injected instances in total), rerun all calibrations, and report the paired effect as a distribution over seeds.
*Success:* the sign of the paired effect is the same in every seed, and the pooled interval is reported.

### Not planned, and why

- Tuning the margin factor, persistence or calibration window on test results: would invalidate the evaluation.
- Detecting command attacks (industroyer) through command provenance: needs network-level data and is a different paper; stated as scope.
- More machine-learning architectures: the review's ML objection is answered by the published-IDS comparison (B1 makes it like-for-like).
- A new recorded day from the simulator: the scenario is not public. The realistic route is to ask the dataset authors for additional recorded days (owner's decision).

## Order, effort and expected effect

| Step | Effort (autonomous work) | Effect on the paper if it succeeds |
| --- | --- | --- |
| A1 reporting-robust margins | about half a day | turns the main negative red-team finding into a contribution with a derived bound |
| A2 proved SE rules | about half to one day, gated | removes the review's critical point for the partially observed grid |
| B1 published IDSs, same data | about half a day, after approval | fair comparison; removes "not identical conditions" |
| A3 temporal accumulation | about half a day | shrinks the stealth band; may recover the near-zero drifts |
| B2 five injection seeds | about half a day, mostly compute | statistical robustness of the injected-day result |

Then: update the paper (method, results, figures 7 and 9, abstract), rerun the statistics, render, and respond point by point.
