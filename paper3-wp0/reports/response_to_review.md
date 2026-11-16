# Response to the simulated review

Point-by-point response to `review_simulated.md`. Every new number comes from a generated report, named in brackets. Changes are in `paper_draft.md`.

| # | Reviewer point | What we did | Result |
| --- | --- | --- | --- |
| M1 | "Certified" is overloaded | Two named strengths: **proved** (robust SMT layer UNSAT) and **search-validated** (AC search only). Defined in Section III, used in the abstract, contributions, Fig. 1 and Section VI. | Every P, G, S rule on 01-Basic is proved; every SE rule on 02-Semiurban and 03-Rural is search-validated. |
| M2 | Headline p-value rests on the semi-synthetic day; injection model revised once | Abstract now reports the recorded days first (5/0, p = 0.062) and states that 42 of 103 instances are injected. New sweep: drift magnitudes 0.5× and 2× the measured ones, same seed, all calibrations rerun (`scripts/sweep_runs.sh`, `sweep_finish.sh`). Table V-a and Fig. 7(b). | Pooled with recorded days: 14/0 (p = 0.00012) at 0.5× and 1×, 12/0 (p = 0.00049) at 2×; v1 (guessed): 16/0 on the additional day alone. The classic detector never catches an instance the combination misses [statistics_pooled_split_d05.md, statistics_pooled_split_d20.md]. |
| M3 | Industroyer essentially undetected | Scope paragraph in the introduction; abstract says command attacks are out of reach of consistency rules. | Text only. |
| M4 | Little gain on the fully observed grid | Stated in abstract and scope: value there is auditability and durability. External comparison (M9) added. | Text only. |
| M5 | Strict accounting missing on 02-Semiurban | Each record now carries the certification time of its topology rule; an attack is credited only if that rule was certified before the attack began (`scripts/18`, `19`, `20`). | No change on any grid or day: Semiurban recorded 4/5, 6/9; additional day 7/7, 4/7; pooled 14/0 under strict accounting too [comparison.md, comparison_split.md, statistics.md]. |
| M6 | Error bounds empirical; search budget | Budget sensitivity at 4× and 8× (2,000 and 4,000 power flows per topology and quantity), saved bounds untouched (`scripts/04 --report-tag`). Failure direction stated (a too-small bound yields a false alarm, never a missed attack). | Worst case grows by at most 2.6 %; δ still exceeds every worst case by at least 1.22× [linac_error_budget2000_sherlock.md, linac_error_budget4000_sherlock.md]. |
| M7 | Denominators | "catches every drift-off" replaced by counts (4 of 4, D1 3 of 4; 4 of 4 visible drifts per grid). | Text only. |
| M8 | Envelope source | New discussion paragraph "What a utility must provide". | Text only. |
| M9 | External baseline | Our methods scored with the dataset paper's own metrics on 01-Basic, beside its five published IDSs (`scripts/24_sherlock_metrics.py`, Table VII). | Combined 14/18 at 10 false alarms; calibrated library 11/18 at 2; published SIMPLE 16/18 at 33, GeCo 15/18 at 94 [sherlock_metrics.md]. |
| M10 | Pseudo-measurement assumption | Stated in the discussion (profile membership of unmonitored loads is planning knowledge). | Text only; a profile-agnostic run remains open. |
| Q | Poisoning the online calibration | Discussion paragraph: the margin can only grow, so poisoning buys stealth, never false alarms; two mitigations named. | Text only. |
| m | Minor comments | Delay of the library alone stated (102 s vs 78 s); on-demand latency harmonised (4 to 10 s); tap-padded result cited with the v2 run; figure 6 label precision; rule list reformatted. | |

Not yet done: a profile-agnostic pseudo-measurement run (M10), interval bounds for the Jacobian (M6, future work), state-transition rules for command attacks (M3, future work).

---

# Second review round (external review, 7.4/10, major revision) and red team

| Point | What we did | Result |
| --- | --- | --- |
| Certification vs. search validation (critical) | Section IV-I states assumptions A1 to A4 and two propositions: proved rules (robust UNSAT) exclude every benign state of the envelope under the assumptions; search-validated rules get a measured scenario bound. Every Semiurban SE rule was re-checked on 1,500 fresh independent benign states (`scripts/25_validate_se_rules.py`). States what is not guaranteed and that every assumption failure is a false alarm, never a missed attack. | 13 rules, 19,500 states, 0 firing: per-rule firing probability at most 4.6e-3, pooled at most 3.5e-4, confidence 0.999; closest score 0.97 [se_rule_validation_semiurban.md]. Before, each rule rested on 40 samples plus a short search. |
| Comparison with the state of the art | Table I positions the work against seven lines of prior work on six properties; entries checked against the cited papers; Imhotep-SMT added as [27]; references [11], [12] completed. | Text and table. |
| Generalization | Discussion paragraph "How far the results generalise". | Text. |
| Operational scalability | Certification and evaluation timed inside the loop (`scripts/14`, cost section). Section VI-J. | G rule 17.6 to 60.6 s; S rule 3.3 to 27.1 s; library evaluation 1.7 ms per record; Semiurban topology 5 to 10 s [consolidation_tc_sherlock.md]. |
| Statistics presentation | Abstract reports the recorded days first and states which instances are injected (done in round 1). | Text. |
| Internal notes, placeholders, references | `scripts/27_render_paper.py` builds the submission version: no header note, no report file names, "n/r" for unreported values; source keeps traceability. | `paper_submission.md`, `paper_draft.pdf`. |
| Red team A (power systems): SCADA artifacts | Library replayed under latency and deadband (`scripts/26_red_team.py`); then the loop rerun with the artifact in training and test (`scripts/14 --artifact`). Section VI-I, Fig. 9. | Clean calibration: 3.5 % false alarms with 1 s latency, 27 % with 1 % deadband. Calibrated on the same feed: deadband fully absorbed (0.056 %), latency 2 s reduced to 1.0 %. New limitation stated. |
| Red team B (security): stealth budget | Margins recovered from the stored rules. Section VI-I. | Voltage margins 0.0020 to 0.0264 pu, median 0.0073 pu, against real drift attacks of 0.036 to 0.38 pu. |
| Red team C (machine learning): weak baselines | Answered by the published-IDS comparison (Table VII) and the physics-informed baseline; Holm correction noted in `red_team_review.md`. | Text. |

# Third round: improvement plan (`improvement_plan.md`, approved by the owner)

| Point | What we did | Result |
| --- | --- | --- |
| Certification vs. search validation (critical), revisited | Affine worst-case bound for the SE residual over the envelope box plus a validated remainder (`src/p3/se_proof.py`, `scripts/29_prove_se_rules.py`); box corners checked on the full AC model; on-demand certification gains `--prove` (`scripts/18 --prove`). | The pre-registered gate failed (61 % of measurement checks proved by the search margins), and the corner check found benign counterexamples to the search-validated rules in every topology: the round-2 claim above (0 firings in 19,500 uniform states) was not a guarantee. CEGIS raised the margins to the proved bound; every SE rule is now proved up to the remainder bound. Cost: certification latency 120 s median (was 5 to 10 s); detection on the recorded day unchanged with persistence (CFC 4/5, drift-off 6/9), false alarms 0.00401 to 0.00017; on the additional day CFC 7/7 to 6/7 [semiurban_consolidation_semiurban.md, comparison.md, comparison_split.md]. Section IV-I, paragraph "Why search validation was not enough". |
| Pooled statistics with proved rules | `scripts/20_statistics.py` rerun. | Recorded plus additional day: 48/103 combined against 35/103 classic, 13/0, p = 0.00024, also under strict accounting [statistics_split.md]. |
| Red team A: SCADA artifacts | Reporting-robust margins: each atom's margin reduced online by the observable reporting uncertainty (`scripts/28_robust_margins.py`). Section VI-I, Fig. 9. | Clean calibration with robust margins: 0.041 to 0.053 % false alarms under latency up to 5 s, 0.047 % under deadbands up to 2 %, detection 12/16 throughout [robust_margins_sherlock.md]. |
| Red team B: stealth band | CUSUM on certified residuals (`scripts/31_cusum.py`), pre-registered criterion. | Failed: 71 % false alarms per benign record; reported as a negative result with its diagnosis (benign model-mismatch bias) [cusum_tc_sherlock.md]. |
| Like-for-like published IDS | SIMPLE and GeCo from the open IPAL IDS framework, framework defaults, same unfiltered files (`scripts/30_published_ids.py`). | SIMPLE alarms on 100 % of benign records; by the dataset metric 0/18 and 1 false alarm. GeCo did not finish training within 6 hours on 4 cores (2 h plus a 4 h resumed run); reported as not available [published_ids_sherlock.md]. |
| Injection seeds | Five seeds for the additional day, all calibrations rerun (`scripts/seeds_runs.sh`, `scripts/32_seed_summary.py`). | Only combined / only classic: 8, 3, 6, 5, 3 against 0; pooled 25/0 over 218 instances (descriptive) [seed_summary.md]. Table VIII. |
| Attack-strength sweep with proved rules | `scripts/sweep_prove.sh`, `sweep_prove_finish.sh` (after a report-text bug in `scripts/18`). | Pooled with recorded days: 13/0 (p = 0.00024) at 0.5× and 1×, 10/0 (p = 0.0020) at 2×; the additional day alone at 2×: 5/0, p = 0.062 [statistics_pooled_split_d05.md, statistics_pooled_split_d20.md, statistics_split_d20.md]. |
