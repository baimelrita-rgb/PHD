# Red-team review, Reviewer A (power systems)

Paper: `paper3-wp0/reports/paper_draft.md` ("From Alerts to Certified Rules"), target IEEE Trans. Smart Grid.
All file references are relative to `/home/user/PHD/paper3-wp0/`. No repository files were changed and nothing long was run.

**Score: 4/10. Recommendation: major revision, close to reject.** The idea is new for TSG and the authors are unusually honest about negative results. The rejection risk comes from five places: (1) the partially observed grid, which produces almost all of the paired gain, is compared against a mis-specified bad-data detector; (2) the "proved" SE certificate depends on a remainder bound validated by exactly the kind of sampling the paper itself calls insufficient; (3) the grids are the simulator's own models, so model fidelity and pseudo-measurement quality are unrealistically good; (4) the SCADA-realism claim is only half tested; (5) the paper is roughly twice the TSG length limit.

---

## 1. Strongest objections (ranked by impact on acceptance)

### O1. The partially observed result compares against a mis-specified SE-BDD baseline, so the gain comes from per-measurement calibration, not from certification
**Claim in paper.** The abstract and Sec. VI-E say the proved library detects 10 of 21 injected attacks against 2 for SE-BDD, because "one threshold at 138 sigma hides what per-measurement margins expose". Sec. II says per-measurement granularity "accounts for the library's advantage".

**Verification.**
- `src/p3/state_est.py:26-29`: the SE uses fixed sigmas (vm 5e-4 pu, flows 2e-3 MW) and pseudo-measurement sigma `PSEUDO_REL = 0.01` (1 % of nominal). In real distribution-system state estimation (DSSE), pseudo-measurement errors are typically 20 to 50 %.
- Because the weights do not match the actual errors, the training 99.9th percentile of the largest normalised residual is about 85 sigma, so θ = 170.45 (`reports/se_bdd_semiurban.md:13`) and 138.18 on the split day (`reports/se_bdd_semiurban_split.md:13`). A largest-normalised-residual (LNR) test at 170 sigma corresponds to about 0.085 pu on a voltage channel. No DSO would run BDD this way.
- The library's per-kind noise floors are 0.16 to 2.5 "sigma" (`reports/semiurban_consolidation_semiurban.md:5`). Margins are therefore set per measurement from training data, which is simply a calibrated per-measurement residual test.
- The library margin is m_i = 1.5 · max(noise_i, bound_i). A per-measurement test with m_i = 1.5 · noise_i and no oracle detects at least as much as the library, by construction. That ablation is missing: I searched the reports and scripts for a no-oracle or noise-only variant and found none.
- No plain limit check is used as a baseline. Several real drift-offs moved a voltage reading by 0.10 to 0.39 pu (`reports/drift_magnitude.md:9-31`), which a [0.90, 1.10] pu plausibility alarm in any SCADA system would flag.
- The paired gain is concentrated where this baseline is weakest. On the split day, 01-Basic gives 0 discordant pairs (`reports/statistics_split.md:34`) and 02-Semiurban gives 8/0 (`:37`). On the recorded days, 3 of the 5 discordant instances come from Semiurban (`reports/statistics.md`).

**What neutralises it.** (a) Re-weight the SE: estimate per-channel sigmas, including realistic pseudo-measurement sigmas, from the training residuals. Then run a standard LNR test at 3 to 4 sigma, or with a calibrated threshold, as the classic baseline. (b) Add the ablation "library without oracle" (margin = 1.5 × noise_i only) on both grids, and report detection and false alarms. This isolates what certification adds: fewer false alarms in unseen topologies, presumably. (c) Add a limit or plausibility-check baseline. This is the highest-impact experiment. If the gain survives (a) and (b), the paper becomes much stronger.

### O2. The "proved" SE certificate rests on a remainder δ validated by the method the paper discredits, and "proved by construction" is close to a tautology
**Claim.** Sec. IV-H and IV-I, Proposition 2: every SE rule is proved, and "in high dimension 'no counterexample found' by sampling is not evidence of absence".

**Verification.**
- `src/p3/se_proof.py:25` and `scripts/18_semiurban_consolidation.py:47`: δ_i = 1.25 × the largest remainder over n = 150 uniform benign states plus a differential evolution with `budget=100` evaluations, in 481 dimensions. This is the same procedure that, in its 40-sample form, missed benign counterexamples at the box corners in every topology. The paper does not state the DE budget of 100.
- `corner_check` (`se_proof.py:73-93`) evaluates corners only against the *old* margins. The remainder at the corners, where nonlinearity is largest, never enters δ. Nobody checks whether the corners respect the *new* proved margins.
- "The rule is then proved by construction, since its margin is at least 1.5 × that bound" (Sec. IV-H). The margins are simply raised to the bound (204 to 246 margins per topology, `reports/semiurban_consolidation_semiurban.md:20-33`). The proof is only as good as δ.
- The pre-registered gate failed. Only 61 % of measurement checks were proved, against a gate of 80 % (`reports/se_rule_proof_semiurban.md`, last line: "gate (80 %): not passed: search validation stays"). The paper then adopts raised margins and calls the rules proved, and it does not mention the failed gate.
- 03-Rural "proved" library: the margins are floored at the transferred SE-BDD threshold (`reports/semiurban_consolidation_rural.md:5`, floor 113.63 × 1.5 = 170.45). The library therefore equals SE-BDD by construction (5/22 each, `reports/statistics.md`), yet its 22 instances are counted in the pooled 61.

**What neutralises it.** Bound the remainder formally: interval or Lipschitz bounds on the second-order term of the AC map over the box, or at least include the box corners and a large DE budget in the δ estimation. Report the failed gate in Sec. IV-I. Present 03-Rural separately rather than in the pooled denominator, or state plainly that its library equals the detector.

### O3. Realism of the grid reconstruction and of the observability model
- The "reconstruction" recovers the pandapower model the co-simulator used: CIGRE and SimBench with fitted transformers. Its error is about 1e-3 pu at worst (`reports/sherlock_model_check.md:48`, `reports/semiurban_model_check_test.md:13`). Real DSO models carry line-impedance and topology errors of several percent. The paper itself says the stealth band is "set by model fidelity" (Sec. VI-I), so every margin, every certificate and every detection number is optimistic for a real feeder. No parameter-error sensitivity analysis is given.
- Pseudo-measurements use the simulator's own profile assignment (`net.load.profile`, `src/p3/state_est.py:92`) with 1 % sigma. A DSO knows the profile class only approximately. The paper calls this "planning knowledge" (Sec. VII). It is closer to leakage from the data generator.
- The model is single-phase and balanced, MV only, with no LV aggregation and no voltage-dependent loads.
- Envelope realism:
  - The tap range is "positions seen in training" ([-1, 0], `reports/sherlock_taps.md:6`). A benign tap change outside that range stopped synthesis for two hours (Sec. VI-E). A real OLTC range is ±8 to ±10 steps, and the paper never tests the full engineering range.
  - Load Q/nominal is allowed in [-0.116, 2.542] (`reports/rural_envelope_rural.md:8`), which is physically implausible.
  - On 03-Rural the transferred Q envelope covers only 90.4 % of benign records (`reports/rural_envelope_rural.md:13`). Assumption A1 therefore fails on about 10 % of the day.

**What neutralises it.** (a) Perturb line R/X by ±5 to 10 % and the transformer parameters in the model the oracle uses, then rerun certification and detection. (b) Run pseudo-measurements with 20 to 50 % sigma and without profile labels (open item M10 in `reports/response_to_review.md`). (c) Use the full nameplate OLTC range as the envelope.

### O4. SCADA and IEC 104 realism is only half tested, and the fully observed grid gains nothing on the independent day
- In Sec. VI-I, "detection (detectors or library) at 12/16 in every case" uses detector alarms computed on the *clean* recording (`reports/robust_margins_sherlock.md`, header: "detector alarms as computed on the recorded telemetry"). D1, a full AC power flow, would also degrade under latency and deadband, and that is not shown.
- The latency tested is at most 5 s at 1 Hz. Real IEC 104 links mix cyclic transmission (10 to 60 s), spontaneous transmission with deadband, and GI interrogations. Deadbands were set as a percentage of the training range, not as configured absolute or full-scale values.
- The robust margin is inflated by V_j(t), the recent variation of the reading itself. A slow drift-off ramp therefore raises its own threshold. This self-masking is not analysed.
- The word "margin" has two meanings: the threshold μ, and the firing score. As a result, "margins reduced online" in the abstract reads as "more sensitive", which is the opposite of what is meant.
- On the independent day for 01-Basic, the combined system detects 11/21, the same as D1, at 5.69 false-alarm episodes per hour against 1.07 (`reports/comparison_split.md:13,22`). That is five times the alarm load for zero gain. Table VI shows only false alarms per record, which hides this.

**What neutralises it.** Apply the artifacts to the detectors as well. Emulate IEC 104 cyclic and spontaneous reporting with absolute deadbands. Report false-alarm episodes per hour in Table VI. Analyse attacker exploitation of V_j(t). Rename the robust term (for example "reporting allowance added to the threshold").

### O5. Length and presentation versus TSG limits, and statistics framed by the most favourable seed
- The paper is about 13,100 words (`wc -w`), with 9 tables and 9 figures. `reports/paper_draft.pdf` is 27 A4 pages. A TSG regular paper is limited to about 10 pages in two-column format, with overlength charges and a hard cap; check the current guidelines. As it stands, the paper risks a desk reject and must be cut roughly in half. Candidates to cut or move to supplementary material: VI-K (ML negative result), the CUSUM negative result, the rule listing in VI-B, Table VI-a, and most of the ablations.
- Statistics:
  - The "main" seed 7 has the largest discordance of the five seeds (8/0, against 3, 6, 5, 3; `reports/seed_summary.md`). The per-seed p-values are 0.25, 0.031, 0.062 and 0.25 for seeds 8 to 11, so only seeds 7 and 9 are significant.
  - The headline p = 0.00024 pools a semi-synthetic day the authors designed. Of its 13 discordant instances, 11 come from 02-Semiurban (see O1).

**What neutralises it.** Report the median seed or all seeds as the primary result. Lead with the recorded-day result (5/0, p = 0.062). Compress to TSG length.

---

## 2. Number spot-checks (paper vs. cited report)

**Matches** (25 checked):

| Paper claim | Report |
| --- | --- |
| 36 % / 41 % / 44 % (22, 25, 27 of 61) | `statistics.md` |
| 35 / 41 / 48 of 103; 13/0, p = 0.00024 | `statistics.md` |
| Table V, all rows | `comparison.md` |
| Table VI, all rows | `comparison_split.md` |
| Table VIII seeds; 25/0 of 218 | `seed_summary.md` |
| Table IX | `sherlock_metrics_sherlock.md` |
| 2.2 ms vs 35.2 ms; 5.0e-7 | `envelope_smoke.md:42-44` |
| 0.00708 / 0.00834 / 0.01204 / 0.01207 pu | `linac_error*.md`, `lindistflow_error*.md` |
| 0.287 vs 0.538 MW | `atom_bounds_linac_sherlock.md:9` |
| Budget 0.194 → 0.199 MW (+2.6 %), δ ≥ 1.22× | `linac_error_budget*.md:360` |
| ε = 3.45e-4, N = 20,000 | `scenario_bound.md` |
| Tap error 2.68e-4 vs 1.23e-2 pu | `sherlock_taps.md:13-14` |
| Table III | `sherlock_model_check.md`, `semiurban_model_check_test.md` |
| Latency 120 / 160 s; 13 topologies | `semiurban_consolidation_semiurban.md` |
| Noise floors 0.16 to 2.50 | same report |
| Robust-margin percentages (3.5, 6.9, 18 to 38, 0.80, 0.041 to 0.053, 0.047, 0.044 %) | `robust_margins_sherlock.md` |
| CUSUM 71 % / 64 % | `cusum_tc*.md` |
| Certification costs 17.6 to 60.6, 6.0 to 27.1, 3.3 to 4.0 s; 1.7 ms; 446 clauses | `consolidation_tc_sherlock.md` |
| SE-BDD θ = 170.45 | `se_bdd_semiurban.md` |
| 19,500 states, 4.6e-3 | `se_rule_validation_semiurban.md` |
| Rural cal30: 5/5, 8/9, 4/8 at 0.184 | `semiurban_consolidation_cal30_rural.md` |
| Rural 0.723 false alarms | `decision_log.md:79` |

**Mismatches and inconsistencies:**
1. **Sec. IV-I vs. Sec. VI-C contradiction.** IV-I says "Section VI-C reports that this [proof] cost one detected instance". VI-C says "the proof costs no detection here". According to `response_to_review.md` (third round), the lost instance was on the *additional* day (CFC 7/7 → 6/7), which is Sec. VI-E.
2. **Load Q coverage, Sec. VII ("only 10 % of load Q").** The cited Rural envelope report shows 90.4 % coverage with the transferred bounds (`rural_envelope_rural.md:13`). The 10 % figure, for SimBench qload profiles, appears only in `decision_log.md:77`. In addition, "nothing calibrated on Rural / no recorded data used" hides that the Q bounds come from the Semiurban recording.
3. **"On 03-Rural every topology was certified on demand" (Sec. VII).** This is true only for the global-threshold run. The 30-minute calibration run cited in VI-D refuted 2 of 13 topologies (`semiurban_consolidation_cal30_rural.md:10`), and that run is search-validated only.
4. **Sec. VI-I, "detection (detectors or library) at 12/16 in every case".** The detector alarms come from clean telemetry (`robust_margins_sherlock.md` header), so this is not an artifact-robust detection result.
5. **Sec. V-B, "All three reconstructions reproduce the recorded voltages at that level [5.0e-4 pu]".** The maximum errors are 1.01e-3 to 1.06e-3 pu, about twice the noise floor. Only the means are below it.
6. **Citation names.** `[sherlock_metrics.md]` does not exist; the file is `sherlock_metrics_sherlock.md`. `[rules_sherlock.json]` and `[library_sherlock.json]` are not in `reports/`.
7. **Sec. IV-H** omits that the DE budget for δ is only 100 evaluations (`scripts/18_semiurban_consolidation.py:47`).
8. **Report bug.** The header of `semiurban_consolidation_rural.md` (run with `--prove`) says "only the search layer applies (AC-validated, not a formal certificate)", while its log says "proved (affine bound)". The report text contradicts itself.
9. **Abstract, "On the fully observed grid ... the combination detects 14 of 18".** This compares unfiltered results with published numbers obtained after filtering, and uses a reconstructed exact grid model that the published, model-free IDSs did not have. The text discloses the filtering, but the abstract presents the comparison as like for like.

---

## 3. Actions ranked by impact on acceptance

1. **O1.** Correctly weighted SE-BDD (realistic pseudo-measurement sigma, standard LNR) plus a "library without oracle" ablation plus a limit-check baseline. This decides whether the partially observed result, and hence the headline p-value, survives.
2. **O2.** A formal or corner-inclusive remainder bound for δ, disclosure of the failed 80 % gate, and 03-Rural separated from the pooled statistics.
3. **O5.** Cut to TSG length, otherwise the paper risks a desk reject. Lead with recorded days and all seeds.
4. **O3.** Sensitivity to line and transformer parameter errors (±5 to 10 %), realistic pseudo-measurements, and the full OLTC range.
5. **O4.** Artifacts applied to the detectors as well, IEC 104 cyclic and spontaneous emulation, episodes per hour in Table VI, analysis of drift self-masking, and fixed "margin" terminology.
6. Fix mismatches 1 to 8 above. These are text-only changes, but items 1 to 3 are the kind a TSG reviewer reads as carelessness.
