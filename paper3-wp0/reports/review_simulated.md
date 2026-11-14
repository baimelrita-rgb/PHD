# Simulated peer review of the draft "From Alerts to Certified Rules"

*Written as a reviewer for IEEE Transactions on Smart Grid would, against the draft in `paper_draft.md` (version with Figs. 1 to 8). The purpose is to find the weaknesses before a real reviewer does. Every criticism below points at something in the draft or in the underlying reports; where a fix exists in the repository it is named.*

## Summary of the submission

The paper proposes a self-consolidating intrusion detection system for distribution grids: detector alerts are turned into deterministic rules, and a rule is admitted to a library only after a two-layer physics oracle (AC search plus a robust SMT layer over a linearised AC model) certifies that no benign feasible state fires it. The method is evaluated on three grids reconstructed from the Sherlock dataset, including a partially observed 178-bus grid, a zero-training transfer to a 99-bus grid, and a semi-synthetic additional test day. The main quantitative claim is a statistically significant paired advantage of "detector plus certified library" over the classic detector (14 against 0 discordant instances, p = 0.00012 over 103 instances), with a large advantage on the partially observed grid at zero false alarms.

## Overall assessment

**Recommendation: major revision.** The idea is clear and timely, the engineering is unusually thorough, and the negative results are reported honestly, which I appreciate. The paper is not yet acceptable because (i) the headline statistical claim leans on a semi-synthetic day whose attack generator the authors themselves designed, (ii) the certificate's semantics are weaker than the word "certified" suggests in several places, and (iii) on the fully observed grid the method's gain over a well-tuned classic detector is small while its false-alarm rate is higher. These are addressable with rewording, one or two additional experiments, and a clearer statement of scope.

Significance: 4/5. Originality: 4/5. Technical soundness: 3/5. Presentation: 3/5. Reproducibility: 5/5.

## Major comments

**M1. The word "certified" is overloaded.** The paper uses "certified" for four different guarantees: (a) UNSAT in the robust exact layer under empirical error bounds; (b) "no counterexample found" by the search layer alone (all of 02-Semiurban and 03-Rural); (c) a scenario-approach probabilistic statement relative to a uniform sampling distribution; and (d) certification after online noise calibration, where the margin was raised on test data. A reader of the abstract will assume (a) everywhere. Please introduce two distinct terms, for example *proved (robust SMT)* and *search-validated*, label every table row and every rule in Section VI-B with the one that applies, and state in the abstract that on the partially observed grid the certificate is search-validated only.

**M2. The headline p-value depends on the semi-synthetic day.** On the recorded days alone the paired test gives 5 against 0, p = 0.062. Significance appears only after adding 42 injected instances. The injection model was revised once (v1 to v2) after seeing v1 results, and although the authors argue the revision followed the measured anatomy, a reviewer cannot exclude that the choice of magnitude distribution, frozen-area size and the 60 % line-opening probability influenced the outcome. Required: (1) report the McNemar result for v1 and v2 side by side in the main text, not only in the log; (2) report a sensitivity sweep over the frozen-area size and the drift magnitude scale (for example 0.5×, 1×, 2× the measured magnitudes); (3) state clearly in the abstract that 42 of the 103 instances are injected. If the recorded-day result alone is to be the headline, say "consistent but not significant".

**M3. Industroyer is essentially undetected by the proposed method and is zero on the additional day for every method.** The paper's own anatomy shows that two of the three real attack families are telemetry falsifications; the third, valid commands, is the one that caused the 2015 blackout. The method catches it only through transients (single-record mode, at 1.6 % false alarms) or through two state rules on islanded zones. This should be presented as a scope limitation in the introduction, not discovered in Section VI. The claim "the library detects attacks the detectors miss" should be qualified as "falsification attacks".

**M4. Fully observed grid: the library adds false alarms and little detection.** On 01-Basic the strict library catches the same number of instances as D1 (10 of 16) with twice D1's false-alarm rate before WP5 and a comparable rate after. The combined system adds two instances (one of them an arp-spoof that is excluded elsewhere). The honest reading is that on a fully observed grid with a good residual detector, the library's value is auditability and durability, not detection. The discussion says this in part; the abstract and introduction do not. Please align them.

**M5. Strict accounting is applied inconsistently.** On 01-Basic the paper reports the strict variant (rules learned before the attack). On 02-Semiurban the rules are certified on demand when a topology first appears, which can be during an attack; the SE rule of that topology then acts on the same attack. This is the non-strict situation the authors avoided on 01-Basic. Please report, for 02-Semiurban, how many detected instances were caught by a rule certified during the attack itself, and provide a strict variant (rule acts only from the next benign record after certification, or only on topologies seen before the attack started).

**M6. The error bounds are empirical and the probabilistic bound is weaker than it looks.** The scenario-approach statement holds for states drawn uniformly over the envelope box. Benign operation is not uniform over that box; the corners, which are exactly where linearisation errors are largest, are under-weighted by a uniform draw relative to an adversary. The adversarial search mitigates this, but with a fixed budget (500 flows per topology). Please (1) report the sensitivity of the worst case to the search budget (for example 500, 2,000, 8,000), (2) say explicitly that the robust certificate is conditional on the bound and that violating it on a real grid produces a false alarm, not a missed attack (this is the right direction of failure and should be stated as a design argument), and (3) consider interval or sampling-based bounds for the Jacobian over the box as future work.

**M7. One recorded test day per grid.** Confidence intervals are reported, which is good, but the paper should be explicit that every detection number on the recorded days rests on 4 to 9 instances per type, and should avoid phrases such as "catches every drift-off" without the denominator attached.

**M8. The envelope is partly learned from the same recording family the attacks come from.** Load ranges come from the training day of the same simulator scenario. In a real deployment the envelope would come from planning data and operating procedures. The 03-Rural experiment shows the SimBench-profile envelope covering 100 % of load P but only 10 % of load Q without transfer. Please discuss what a utility would need to provide to write the envelope, and the consequence of an envelope that is too narrow (certified rules that fire on benign states the envelope omitted, as happened with the unseen tap position) or too wide (rules that cannot be certified).

**M9. Baselines.** The classic baselines are reasonable (residual test, SE-BDD), and the ML baselines are deliberately simple. For a TSG audience, at least one published process-aware IDS from the Sherlock paper's own evaluation, or a graph-based detector, should be run on the same splits, or the authors should justify why the SE-residual autoencoder is a fair proxy. The present ML results (86 % to 99.99 % false alarms on raw telemetry) will be read as a straw man unless the physics-informed variant is treated as the real ML baseline throughout.

**M10. Partial observability model.** Pseudo-measurements for unmonitored loads are built from monitored loads of the same SimBench profile. That information (which profile each unmonitored load follows) comes from the dataset's planning records and would not be available in that form on a real grid. Please state this assumption and estimate the degradation with profile-agnostic pseudo-measurements (for example feeder-level average scaling).

## Minor comments

1. Abstract: "48 % against 34 %" mixes recorded and injected instances; give both numbers or say "recorded plus injected".
2. Section III: define the measurement noise model formally (per-measurement bound, kind floor) since margins depend on it.
3. Section IV-E: the margin formula uses "noise" as a maximum over training records. A maximum over 21,000 records is sensitive to single outliers and to the record step; state the step used (every 10th train record in the consolidation loop) and the effect of using a high percentile instead.
4. Section IV-G: "a larger margin cannot break a certificate" is true for firing-region inclusion but changes detection; say that detection may drop and report that it did not.
5. Section V-B: give the reconstruction procedure enough detail to reproduce (switch mapping test, least-squares fit targets) or move it to an appendix with the tables.
6. Section VI-B: the G rule example has 31 injection terms and 56 clauses; a reader cannot verify it. Publish the libraries as JSON (they exist in the repository) and show one full clause with all coefficients in an appendix.
7. Table IV: mean delay for the library on 01-Basic is 102 s against 78 s for D1; the text says the combination "cuts the mean delay from 77 to 68 s". Both are true but the reader should see that the library alone is slower.
8. Section VI-C: "all 13 test topologies certified in 5 to 11 s" but the on-demand log in the report shows 4 to 10 s; harmonise.
9. Section VI-E: the tap-padded variant is reported with "v1" figures (consolidation_sherlock_split_v1_tappad); the v2 tap-padded result (control-and-freeze 6/7, drift-off 4/7, false alarms 0.0181) should be the one cited, as the text claims.
10. Fig. 4: mark which library firings come from G and which from S rules; mark the three attacks on which the library fired but the detectors did not.
11. Fig. 6: the 100.0 % label for the raw autoencoder on 01-Basic is 99.988 %; label precision should match the table.
12. The scripts use the term "WP5" and tags such as `_tc` in file names cited in the text; replace with descriptive names before submission.
13. References: [1] and [2] are grey literature; fine, but give URLs and access dates. Add the Wattson GitHub release used for reconstruction checks, with a commit or version.
14. Language: consistent "false alarm rate per benign record" versus "episodes per benign hour"; the paper switches between them.

## Questions to the authors

- How long does a full certification of a G rule take on the 178-bus grid if the exact layer were applicable, and what prevents it (the Gauss-Newton correction)? Could a linear surrogate of the corrected residual be bounded the same way as the voltage model?
- What happens to a certified rule when the grid model is updated (new DER, line re-rating)? Is re-certification incremental?
- How does the loop behave under a slow attack whose first 60 s look benign? The alert window is fixed; was a longer window tried?
- Could an attacker who knows the library poison it, for example by triggering alerts in a topology where the online calibration window captures attacker-controlled "noise"? The 5-minute online calibration uses records with no detector alarm; a stealthy falsification below the detector threshold during those 5 minutes would inflate the margin. Please discuss.

## What would make this a clear accept

- Terminology fixed (M1) and scope stated up front (M3, M4).
- The paired test reported for recorded days, v1, v2 and the magnitude sweep (M2), with the headline chosen accordingly.
- A strict on-demand variant for 02-Semiurban (M5).
- A search-budget sensitivity for the error bounds (M6).
- One external IDS baseline or a justified proxy (M9).

With these, the contribution is a convincing, well-documented step toward auditable intrusion detection for distribution grids, and the negative results alone (mined thresholds refined into uselessness; raw-telemetry ML failing under benign change; per-grid noise not transferring) are worth publishing.
