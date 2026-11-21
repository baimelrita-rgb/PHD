# Red-team review, Reviewer C (ML for anomaly detection, experimental design, statistics)

Paper: "From Alerts to Certified Rules: Self-Consolidating Intrusion Detection for Power Grids" (`paper3-wp0/reports/paper_draft.md`)

**Score: 4/10. Recommendation: major revision (borderline reject).** The certification idea is interesting and the engineering is careful and openly documented. But the statistical headline (p = 0.00024; 25 against 0 over five seeds, p = 5.96e-08) tests something that is true by construction. All of the detection gain on the additional day comes from one grid against a deliberately coarse baseline. And the claim of "complementarity" is a grid effect, not a complementarity between the two methods. As written, the paper's evidence that the certified library improves detection does not support the way it is presented in the abstract and conclusion.

---

## Objection 1 (critical): the McNemar test compares X with (X OR Y), so "only classic = 0" is guaranteed by construction

`combined` is defined as the classic detector OR the library. The classic detector's alarms are therefore a subset of the combined system's alarms, and the discordant cell "only classic detects" is structurally zero.

- `scripts/20_statistics.py:103-110`: `det = d["det"]...; al = det | d["lib_prior"]` (01-Basic) and `det = sb["alarm"]...; al = det | d["fires_p"]` (02-Semiurban, 03-Rural). In the strict variant, line 112 sets `added_t = np.where(det, -np.inf, ...)` and line 118 appends `det` to the rule fires with time −∞. Every variant is a superset.
- So with b = 0 forced, the "exact McNemar" p-value is just 2·0.5^c, a monotone function of how many extra instances the OR catches. The null hypothesis P(only combined) = P(only classic) is false a priori as soon as the library fires once inside an attack window. The test does not measure a better detector. It measures whether adding a second alarm source adds any hit. Adding *any* alarm source does that, including a random alarm generator with a nonzero false-alarm rate.
- The paper presents this tautology as a finding three times: line 340 "The combined system never loses an instance the classic detector catches"; line 322 "the classic detector never catches an instance the combined system misses"; and the abstract, line 9, "none only by the detector".
- The pre-registered success criterion for the five-seed study cannot fail. `improvement_plan.md:51`: "*Success:* the sign of the paired effect is the same in every seed". With c ≡ 0, the sign is ≥ 0 in every seed by construction.
- The OR also raises the false-alarm budget, which the test ignores. 01-Basic recorded day: D1 0.00059, combined 0.00171 per benign record (Table V; 0.85 to 1.06 episodes/h in `statistics.md`). Additional day, 01-Basic: classic 1.07 against combined 8.18 episodes/h (`statistics_split.md`). There is no matched-false-alarm comparison anywhere.
- The OR also includes the autoencoder on 01-Basic (`det` = D1 or AE; the header of `statistics.md` says "01-Basic: detectors D1 or AE or library"), while "classic" is D1 alone. On the recorded day the AE adds no instance (the per-type counts of "D1 or AE" equal D1's), but the comparison is not library against nothing.

**Fix (highest impact):**
1. Make the primary test **library alone vs classic** (a genuine two-sided McNemar test).
2. Compare combined vs classic **at matched false-alarm rate**: lower D1's and SE-BDD's thresholds until their benign false-alarm episodes per hour equal the combined system's, then compare detection, or report ROC / partial-AUC curves per grid.
3. Drop "never loses an instance" as an empirical finding, or label it as true by definition.

## Objection 2 (critical): the gain is a single-grid, single-mechanism effect against a strawman BDD; "complementarity" is misreported

I recomputed this from the per-seed reports (`statistics_split{,_s8,_s9,_s10,_s11}.md`):

| Seed | 01-Basic: library vs D1 (only lib / only D1) | 01-Basic: combined vs D1 | 02-Semiurban: library vs SE-BDD |
| --- | --- | --- | --- |
| 7 | 0 / 5 | 0 / 0 | 8 / 0 |
| 8 | 0 / 5 | 0 / 0 | 3 / 0 |
| 9 | 0 / 4 | 0 / 0 | 6 / 0 |
| 10 | 0 / 7 | 0 / 0 | 5 / 0 |
| 11 | 0 / 5 | 0 / 0 | 3 / 0 |
| Pooled | **0 / 26 (p = 3.0e-08)** | 0 / 0 | **25 / 0** |

- On the fully observed grid the library is a **strict subset** of D1 in every seed: it adds nothing and loses 26 instances. On 02-Semiurban, SE-BDD is a strict subset of the library in every seed (classic count + discordant = library count, for example 2 + 8 = 10 and 3 + 3 = 6). All 25 "only combined" instances in Table VIII come from 02-Semiurban.
- Line 345, "the gain comes from complementarity, not from a stronger single detector", is therefore misleading. Within each grid one method dominates the other. The pooled "79 vs 80" is a cancellation between grids (25 vs 26), not evidence that the two methods catch different attacks on the same grid. Library alone vs classic, pooled over seeds: 25 vs 26, p = 1.0 (recomputed).
- Of the 13 discordant instances behind p = 0.00024, 11 come from 02-Semiurban: 3 recorded and 8 injected. The other 2 come from the 01-Basic recorded day (`statistics.md`, `statistics_split.md`).
- The 02-Semiurban baseline is weak by design. SE-BDD alarms when the *maximum* normalised residual exceeds θ = 170.45 (recorded day) or **138.18 σ** (additional day, `se_bdd_semiurban_split.md:13`). A single global threshold at 138 σ is set by the worst-modelled measurement. The paper itself says this is the reason for the gain: line 309, "one threshold at 138 sigma hides what per-measurement margins expose"; line 39, "On the partially observed grid this difference accounts for the library's advantage".
- The obvious ablation is missing: a **per-measurement normalised BDD**, with each |r_i| divided by its own training 99.9th percentile under one global threshold and no oracle. That baseline isolates "per-measurement calibration" from "certification". The certification step can only *raise* margins, and Section IV-I says the proof cost one detected instance. An uncertified per-measurement detector would very likely detect at least as much, so the detection gain cannot be credited to the certification gate, which is the paper's contribution.

**Fix:**
1. Add the per-measurement BDD and the "library without oracle (noise margins only)" ablation on 02-Semiurban.
2. Report results per grid as the primary unit. Rewrite the abstract and conclusion to say the detection gain is confined to the partially observed grid against a global-threshold BDD.
3. Remove or correct the complementarity sentence.

## Objection 3 (major): pooling and independence. Instances are clustered, the additional day is not independent of the recorded day, and p-values are presented with false precision

- **Clustering.** McNemar assumes independent pairs. Instances on the same grid and day share one detector threshold, one rule library and one set of topologies. The 13 discordant pairs come from 3 grid-day clusters (01-Basic recorded: 2; 02-Semiurban recorded: 3; 02-Semiurban additional: 8). A cluster-level sign test gives 3 of 3 clusters with a non-negative difference, p = 0.25 (recomputed). Because of Objection 1, a negative cluster was impossible anyway.
- **The additional day borrows from the test day.** Its attack model v2 draws each drift-off's magnitude and bus count from the measured real *test-day* attacks (`scripts/22_split_day.py:201-204`: `real = json.loads(... "drift_magnitudes.json")[grid] ... D = float(real["max_signed_offset_pu"][k_inst]) * ...`). The model was adopted after v1 had been run (`decision_log.md:113-118`). Pooling recorded and injected instances as 103 independent trials double-uses the recorded attacks.
- **Five seeds on one benign base.** The paper correctly calls p = 5.96e-08 "descriptive" (line 345 and the docstring of `scripts/32_seed_summary.py`), but still prints it in Table VIII and repeats "25 against 0 over 218" in the abstract and conclusion. Per-seed p-values are 0.0078, 0.25, 0.031, 0.0625 and 0.25, so 2 of 5 are below 0.05 with no correction.
- **Multiplicity and forking paths.** The paper reports strict and non-strict accounting, L = 1/3/5, v1 and v2, 0.5×/1×/2×, with and without per-topology calibration, with and without tap padding, three margin factors and three seeds. The headline picks recorded + additional v2 pooled. The Holm argument in `red_team_review.md:61` covers only four tests chosen after the fact.
- **The strength sweep does not probe the decision boundary.** Measured drifts are bimodal: 0.036 to 0.39 pu, or about 0.0015 pu (line 295). Library voltage margins are 0.0020 to 0.0264 pu (line 399). Scaling by 0.5× to 2× never moves an instance across the margin band. That is why the 0.5× row is identical to the 1× row (13/42, 16/42 and 21/42 in both `statistics_split.md` and `statistics_split_d05.md`). The claim "the paired result does not depend on the attack model" (line 311) is therefore not supported by a sweep that cannot change it.
- **Chance hits.** An instance counts as detected if any alarm falls in [start, recovery], and windows are long (drift-off 480 to 630 s, control-and-freeze 360 to 690 s; `scripts/22_split_day.py` DUR). At 1.06 false-alarm episodes per hour (01-Basic combined, recorded day), a 10-minute window has roughly a 15 to 18 % chance of a spurious hit. On the additional day the 01-Basic library runs at 7.82 episodes/h. Example: on the additional day, single-record library mode catches 6/7 drift-offs on 02-Semiurban (`comparison_split.md:59`) although only 4 have a visible magnitude, which suggests the other 2 hits are chance alarms at 2.64 episodes/h. No chance-corrected or event-precision metric is reported.

**Fix:**
1. Use a cluster-aware analysis: a stratified or Cochran–Mantel–Haenszel analysis over grid-days, or a permutation test that shifts alarm sequences in time relative to the attack windows. The time-shift permutation also controls chance hits.
2. Report the recorded-day result alone as the confirmatory test: 5/0, p = 0.062, not significant.
3. Replace the 0.5× to 2× sweep with a detection-vs-magnitude curve over 0.001 to 0.05 pu.
4. Remove p = 5.96e-08 from the table and the abstract.

## Objection 4 (major): the ML baselines are straw men, and the published-IDS comparison is not like-for-like

- **Raw-feature ML.** The input includes absolute operating-point values, the discrete line states and the tap positions (`scripts/13_ml_detectors.py:51`). It is standardised with training statistics, and constant training features get sd = 1 (`:116-117`), so any topology unseen in training produces z-scores of tens and the clip at ±50 saturates them. The autoencoder is an sklearn MLP with `max_iter=60`, early stopping, trained on every second record of 75 % of half a day (`:124-125`). There is no hyperparameter search, no topology conditioning, no sequence model and no graph model. The 0.99988 benign alarm rate (Table V) follows from this design, not from ML as a class. The isolation forest "saturates" (line 407) for the same reason.
- **The fair ML proxy is close to the library.** On the additional day, the SE-residual autoencoder detects 10/21 on 02-Semiurban (7/7 control-and-freeze, 3/7 drift-off; `comparison_split.md:58`), the same count as the proved library, but at 0.059 false alarms per record. Its threshold is the 99.95th percentile of calibration scores; it was never tuned to the library's false-alarm level. A threshold matched to the library's false-alarm rate is the comparison an ML reviewer will ask for.
- **The SIMPLE rerun.** It uses all 325 numeric and 145 Boolean fields, including switch states, with the framework's defaults and no filtering (`published_ids_sherlock.md`; `scripts/30_published_ids.py:37-45`). That configuration is guaranteed to alarm on 100 % of records on a day with benign switching. Concluding that "the published 16/18 therefore depends on the measurement filtering" (line 385) is reasonable, but the rerun deliberately disables the protocol that made SIMPLE work. It tests a misconfigured SIMPLE, not SIMPLE.
- **GeCo** timed out, so no like-for-like result exists.
- **Table IX** still compares our unfiltered numbers with published filtered numbers on a metric the authors themselves say "rewards alarm starts, not alarm coverage" (line 385), and then uses that metric for the abstract claim "14 of 18 at 10 false alarms against 16 and 15 at 33 and 94". Its "Combined" row also includes the AE. Without a single operating curve there is no dominance claim, only a different trade-off point.

**Fix:**
1. Rerun SIMPLE with the dataset paper's feature filtering reproduced: the same fields for every method, with the filter defined only from training data.
2. Give GeCo the filtered feature set so it finishes.
3. Add one competent learned baseline: a topology-conditioned or per-topology-normalised autoencoder or LSTM on SE/D1 residuals, tuned on training data, compared at matched false-alarm rate.
4. Report all methods on a single metric with operating curves.

## Objection 5 (moderate): design decisions informed by test data and evaluation on the learning day

- **Envelope.** It is widened because of what was seen on the test day: line 96, "DER output in [0, 1] ... (the test days contain benign set-point changes not seen in training)". This is test knowledge entering the envelope, which is the object being certified.
- **Post-hoc fixes after failures, all openly reported but still choices made after seeing test outcomes:**
  - tap padding added after synthesis stopped on the additional day (line 309);
  - Rural "transferred global threshold as minimum margin (a decision taken after this failure)" (line 288);
  - free load Q after the 72 to 86 σ residuals (line 138);
  - proved margins on 02-Semiurban after the red-team round (lines 152, 281);
  - attack model v2 after v1.
- **Unclear provenance of fixed values.** L = 3 for the library on 02-Semiurban equals SE-BDD's persistence. `decision_log.md:14` says margin and persistence "were fixed by judgement". "Fixed before results" is asserted in the decision log, but there is no timestamped pre-registration for 1.5, L = 3 or 300 s. Only `improvement_plan.md` (round 3) is pre-registered.
- **Same-day learning.** The library learns on the test day itself (limitation 4, line 425). Strict accounting removes credit only for rules learned *during* an attack. G rules learned from earlier alerts in the same topology still benefit from same-day operating conditions.
- **Online calibration (not leakage, but a disclosure gap).** The 300 s per-topology calibration takes the first 300 s of test records in that topology without a detector alarm (`scripts/14_consolidation.py:149`, `rows = [i for i, x in enumerate(cfg_te) if x == T and not det[i]][:need]`). It acts only after the last calibration record, so it is causal. But it can absorb undetected attack records, and those records are excluded from library false-alarm scoring because the rule is inactive during calibration. The paper should state this.

**Fix:**
1. Add a leakage table listing every design decision, its date, the data seen when it was made, and whether it was taken after a test result.
2. Rerun 02-Semiurban with the envelope built strictly from the training day plus documented engineering ranges.
3. Add a held-out evaluation: learn the library on the additional-day first half, freeze it, and evaluate on the recorded test day with no learning.

---

## Spot-checks (13 numbers; all match unless noted)

| Claim in paper | Source | Result |
| --- | --- | --- |
| 13/0, p = 0.00024 | `statistics.md` | match; recomputed 2·0.5^13 = 2.44e-4 |
| 25/0, p = 5.96e-08 | `seed_summary.md` | match; recomputed |
| 5/0, p = 0.062; 8/0, p = 0.008; 10/0, p = 0.0020 | `statistics*.md` | match (0.0625, 0.0078, 0.00195) |
| 27/61 = 0.44 [0.33, 0.57] | `statistics.md` | match; Wilson recomputed [0.325, 0.567] |
| 48/103 = 0.47 [0.37, 0.56]; 35/103 = 0.34 [0.26, 0.44] | `statistics.md` | match ([0.373, 0.562]; [0.256, 0.436]) |
| 25/61 library, 41/103 | `statistics.md` | match |
| Seed rows 8, 3, 6, 5, 3 against 0 | `seed_summary.md` | match |
| SE-BDD 2/21 vs library 10/21 on the additional day | `statistics_split.md` | match |
| Margin factor 2.0: 0.00109 (01-Basic) | `comparison.md:46` | match. `decision_log.md:51` gives 0.00150 from an earlier run; the stale log entry should be marked superseded |
| L = 1/3/5: 0.00124 / 0.00091 / 0.00065 | `comparison.md:25-27` | match |
| Scenario ε = 3.45e-4 | recomputed: 1 − 0.001^(1/20000) = 3.454e-4 | match |
| AE raw 0.99988; 336/170 configurations; voltage margins 0.0020/0.0073/0.0264, 112 clauses | `ml_detectors_raw_sherlock.md`, `sherlock_envelope_sherlock.md`, `red_team_sherlock.md` | match |

**Mismatches and inconsistencies found:**

1. **The proof's detection cost is attributed to the wrong section.** Line 152 says "Section VI-C reports that this cost one detected instance". Section VI-C (line 281) says "the proof costs no detection here". The one-instance cost (control-and-freeze 7/7 to 6/7) is on the *additional* day (`response_to_review.md:42`), and Section VI-E does not mention it.
2. **"Three misses" holds only with persistence.** Line 309 says every visible drift-off is caught and "the three misses per grid are the near-zero instances". This holds for L = 3, but single-record mode on 02-Semiurban detects 6/7 drift-offs (`comparison_split.md:59`), so 2 near-zero instances were "detected", most likely chance hits (see Objection 3).
3. **Wrong file name.** Table IX cites `[sherlock_metrics.md]`; the file is `sherlock_metrics_sherlock.md`.
4. **Ambiguous "classic" in Table VII.** The caption says "combined against classic (D1 or SE-BDD)", while on 01-Basic the combined system also includes the AE. This should be stated in Table VII and in the abstract.

## Ranked changes that would neutralise the objections

1. **Replace the superset McNemar test.** Use library vs classic, plus combined vs classic at matched false-alarm rate (or ROC/pAUC per grid). This neutralises Objection 1 and most of the headline problem.
2. **Add a per-measurement BDD / "library without oracle" ablation on 02-Semiurban**, and report results per grid. This decides whether certification or per-measurement normalisation produces the gain (Objection 2).
3. **Use cluster-aware or time-shift permutation statistics, and drop the pooled descriptive p-values from the abstract.** Make the recorded-day result the confirmatory one (5/0, p = 0.062) and add a detection-vs-magnitude curve (Objection 3).
4. **Make the baselines fair.** Rerun SIMPLE with the dataset's filtering, give GeCo the filtered features, and add a tuned, topology-aware learned baseline at matched false-alarm rate (Objection 4).
5. **Add a leakage and decision-chronology table**, a training-only envelope rerun, and a frozen-library cross-day evaluation (Objection 5).
6. **Fix the four inconsistencies above.**
