# WP1 plan, success estimates and risks

Success estimates in this file are the author's judgment, not measured quantities. They are updated after each stage
so the owner can see the trend. "Success" means acceptance at a good venue (Q1 journal in smart grid security, or a
CPS-security conference) with the paper's main claim intact.

## Where we stand

| Stage | Status | Key evidence |
| --- | --- | --- |
| WP0 feasibility | done | `feasibility_report.md` |
| WP1-a physics visibility of Sherlock attacks | done | `physics_residual.md`: 0.00059 false alarms per benign record; control-and-freeze 5/5, drift-off 3/4, industroyer 2/7 |
| WP1-c rule synthesis from alerts | done | `wp1c_summary.md`: certified rules for drift-off 3/4, control-and-freeze 3/5, industroyer 3/7; false alarms at most 0.0003 per benign test record; 2 plausible rules correctly refuted |
| WP1-b2 exact layer for meshed configurations | done | `wp1b2_summary.md`: linearised AC, worst error 0.00708 / 0.00834 pu (G6 passes on the worst case); R1 refuted, R2 and R3 certified on all 336 Sherlock configurations |
| WP1-b oracle on the Sherlock grid | done | `wp1b_summary.md`: envelope covers all train and 99.86 % of benign test topologies; mined threshold refuted; context rule R2 certified (radial part, robust) |

## Target venue (owner decision: Q1, power field)

Primary: **IEEE Transactions on Smart Grid** (Q1). It publishes grid cyber-physical security, false data injection
and intrusion detection, and fits a physics-certified rule library. What its reviewers will expect: a system larger
than 15 buses (02-Semiurban, 178 buses, addresses this), comparison with baselines (bad-data detection residual test,
an ML detector), and precise claims. Backup: **International Journal of Electrical Power & Energy Systems** (Q1,
broader scope, more accepting). Alternative: IEEE Transactions on Industrial Informatics (Q1, more CPS/IT oriented).
Estimates below are for the primary target; for the backup add roughly 15 to 20 points.

Estimate after WP1-c, for IEEE TSG: **about 52 %** (about 65 to 70 % for IJEPES). The paper's core now exists:
alerts become certified rules with near-zero false alarms, for all three process attack types. Not higher yet: rules
generalise poorly across instances, there is one test day, and no ML detector or baseline comparison.

Estimate after WP1-b2, for IEEE TSG: **about 45 %** (about 60 to 65 % for IJEPES). Higher than planned (43 %): the
linearised AC model passes G6 on the worst case and certifies the power balance rule, which removes two weaknesses.

Estimate after WP1-b, for IEEE TSG: **about 40 %** (about 55 to 60 % for IJEPES). Before WP1-b: about 35 % for
TSG. Earlier lines in this file used "a good venue" in general; from here on the estimate is venue-specific.

Earlier estimate (general, before WP1-b): about 45 %. Up from about 35 % before WP0. The oracle works and is fast, refutes bad rules, and the
grid model matches the dataset's physics. It is not higher because the paper's core, turning alerts into rules
automatically, is not built yet, and the "certified" claim rests on an empirical error bound.

## Next stages

| Stage | Goal | Done when | Estimate after success |
| --- | --- | --- | --- |
| WP1-b | Oracle on the Sherlock grid | done (`wp1b_summary.md`) | TSG about 40 % |
| WP1-b2 | Exact layer for meshed configurations | done (`wp1b2_summary.md`) | TSG about 45 % |
| WP1-c | Rule synthesis from alerts | done (`wp1c_summary.md`) | TSG about 52 % |
| WP1-d | Self-consolidation loop: replay the test timeline; the anomaly signal (here the D1 residual detector as stand-in, later an ML detector) triggers synthesis; certified rules enter the library | Detection and false alarms of the rule library over time against the detector alone | TSG about 55 % |
| WP2 | 02-Semiurban (approved, downloaded and md5-verified) and an ML detector. First look: SimBench `1-MV-semiurb--2-sw` matches loads 122, sgen 123, storage 114, lines 126; Sherlock adds 56 DER step-up transformers (178 buses, 58 transformers, 360 switches) to be identified from data as for 01-Basic | Results hold on the 178-bus grid; baselines compared | TSG about 60 to 65 % |

## Risks

| Risk | Effect | Likelihood | Mitigation |
| --- | --- | --- | --- |
| Physics rules miss command attacks (industroyer 5 of 7 missed) | partly resolved in WP1-c: certified state rules catch 3 of 7; 3 leave no snapshot trace | medium | Temporal or command-level context atoms (out of WP0 DSL scope) |
| Synthesized rules generalise poorly across instances (0 or 1 other instance of the same type) | Library grows per incident, little reuse | high (measured) | WP1-d: topology-independent invariants (one rule per quantity with clauses per topology), merging rules of the same element |
| Certificate does not cover telemetry noise | False alarms if noise is under-sampled (seen: 31 % with 100 records) | medium | Global train noise floor (now at most 0.0003 false alarms); report both guarantees separately |
| "Certified" is challenged by reviewers | Main claim weakened | medium | Use the claim "certified relative to LinDistFlow with a validated error bound, AC-validated"; report delta and how it was found; offer a tighter linearization as future work |
| One small grid (15 buses) and one scenario | Generalization questioned | high for TSG | WP2 on 02-Semiurban (178 buses), data already downloaded |
| Exact layer radial only | resolved in WP1-b2 (linearised AC covers meshed configurations) | was medium | done |
| Threshold rules mined from history are not certifiable (refined into uselessness on both grids) | Synthesis must produce context rules, harder to build | medium | Make this a stated finding and design WP1-c around context atoms |
| Sherlock grid reconstructed, not given | Model doubts | low | Validation at the noise floor is documented (`sherlock_model_check.md`, `sherlock_taps.md`) |
| Balance rules not certifiable in the exact layer | resolved in WP1-b2 (R3 certified with the linearised AC model and a rule-specific bound) | was medium | done |
| Error bounds are empirical (adversarial search), not proven | "certified" questioned | medium | State it plainly; report search budget and safety factor; optional future work: Lipschitz or interval bounds on the linearisation remainder |
| Detector stand-in (residual) instead of ML | Reviewers expect ML alerts | medium | WP2 adds an ML detector; the pipeline only needs an alert time and asset list |
| Few attack instances (3 types, 4 to 7 each) | Weak statistics | medium | Report per instance; 02-Semiurban adds industroyer 9, drift-off 9, control-and-freeze 5 |
| Benign procedures cause short residual transients | False alarms | low (0.00059 per record) | Persistence filter calibrated on train; procedure-aware suppression in WP1-c |

## Decisions the owner will be asked for later

None open right now. G2 relaxed to 3 types, venue chosen (IEEE TSG), 02-Semiurban approved and downloaded.
