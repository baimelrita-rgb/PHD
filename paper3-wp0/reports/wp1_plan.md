# WP1 plan, success estimates and risks

Success estimates in this file are the author's judgment, not measured quantities. They are updated after each stage
so the owner can see the trend. "Success" means acceptance at a good venue (Q1 journal in smart grid security, or a
CPS-security conference) with the paper's main claim intact.

## Where we stand

| Stage | Status | Key evidence |
| --- | --- | --- |
| WP0 feasibility | done | `feasibility_report.md` |
| WP1-a physics visibility of Sherlock attacks | done | `physics_residual.md`: 0.00059 false alarms per benign record; control-and-freeze 5/5, drift-off 3/4, industroyer 2/7 |

Estimate now: **about 45 %**. Up from about 35 % before WP0. The oracle works and is fast, refutes bad rules, and the
grid model matches the dataset's physics. It is not higher because the paper's core, turning alerts into rules
automatically, is not built yet, and the "certified" claim rests on an empirical error bound.

## Next stages

| Stage | Goal | Done when | Estimate after success |
| --- | --- | --- | --- |
| WP1-b | Oracle on the Sherlock grid: envelope from train data (profiles, DER, storage, taps, reconfigurations), search and exact layers on the reconstructed model | R1 to R3 analogues certified or refuted on the Sherlock grid; train benign states inside the envelope | about 50 % |
| WP1-c | Rule synthesis from alerts: from an alert window, synthesize candidate physics rules (residual atoms on the elements involved) and context rules (command plus procedure state), certify with the oracle, refine with CEGIS | For each process attack type, at least one certified rule; count of rules refined into uselessness reported | about 60 % |
| WP1-d | Self-consolidation loop: replay the test timeline; the anomaly signal (here the D1 residual detector as stand-in, later an ML detector) triggers synthesis; certified rules enter the library | Detection and false alarms of the rule library over time against the detector alone | about 65 % |
| WP2 | Second dataset or grid (02-Semiurban, needs approval: 6.4 GB) and an ML detector | Results hold on a second grid | about 70 to 75 % |

## Risks

| Risk | Effect | Likelihood | Mitigation |
| --- | --- | --- | --- |
| Physics rules miss command attacks (industroyer 5 of 7 missed) | The certified library covers only telemetry-integrity attacks | high (measured) | Second rule family: context rules (command in no procedure, setpoint outside schedule); certify them against benign procedures, not physics |
| "Certified" is challenged by reviewers | Main claim weakened | medium | Use the claim "certified relative to LinDistFlow with a validated error bound, AC-validated"; report delta and how it was found; offer a tighter linearization as future work |
| One small grid (15 buses) and one scenario | Generalization questioned | high | WP2 on 02-Semiurban; synthetic scaling test on a larger pandapower grid |
| Sherlock grid reconstructed, not given | Model doubts | low | Validation at the noise floor is documented (`sherlock_model_check.md`, `sherlock_taps.md`) |
| Balance rules not certifiable in the exact layer | Fewer certified rule types | medium | Loss-aware exact layer (loss bounds per topology from the search) |
| Detector stand-in (residual) instead of ML | Reviewers expect ML alerts | medium | WP2 adds an ML detector; the pipeline only needs an alert time and asset list |
| Few attack instances (3 types, 4 to 7 each) | Weak statistics | medium | Report per instance; add 02-Semiurban and 03-Rural |
| Benign procedures cause short residual transients | False alarms | low (0.00059 per record) | Persistence filter calibrated on train; procedure-aware suppression in WP1-c |

## Decisions the owner will be asked for later

1. Approve the 02-Semiurban download (6.4 GB) for WP2.
2. Target venue, which fixes the page budget and how formal the certification claim must be.
