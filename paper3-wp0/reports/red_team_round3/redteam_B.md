# Red-team review B: cyber-physical security and formal methods

Paper: "From Alerts to Certified Rules: Self-Consolidating Intrusion Detection for Power Grids" (reports/paper_draft.md, IEEE TSG submission)

**Score: 4/10. Recommendation: major revision. As submitted, this reviewer would argue for rejection.**

The empirical work is careful, and the paper is unusually candid about its negative results. The central claim does not survive inspection. The paper says rules are "proved" or "certified" by an SMT or worst-case layer. For the G and P rules on 01-Basic, the SMT query is a tautology. For both grids, the guarantee rests entirely on sampled or searched maxima inflated by a factor of 1.25, which is the same kind of evidence that Section IV-I says is "not evidence of absence". The threat model also leaves several attacker-controlled channels open.

---

## Objection 1 (fatal as worded): on 01-Basic, the robust SMT "proof" of G and P rules is a tautology, so the certificate is search validation under another name

**Code evidence**
- `src/p3/synthesis.py` (around line 199) contains the comment: "rule-specific bound: the linear model value of the expression is the constant c, so |linear - AC| is the AC residual itself, bounded by the oracle search". The next line, 204, reads: `d.setdefault("linear_atoms", {})[X.atom_key(cand.info["coeffs"])] = BOUND_SAFETY * cand.info["ac_bound"]`. `certify_grid` does the same.
- `ac_bound` (synthesis.py) is a single DE run: `st = O.de_maximize(lambda x, m: abs(...) - c), cfg, E.full(), budget, seed)`. `scripts/14_consolidation.py:69` sets `--bound-budget` to a default of 800 power flows.
- The margin is `MARGIN_FACTOR * max(noise, b)` with `MARGIN_FACTOR = 1.5` and `BOUND_SAFETY = 1.25`.
- 01-Basic uses `load_q="fixed"` (`envelope.py:144`), so `n_lq = 0`. The invariant expression is therefore identically the constant `c` in the Z3 variables. `oracle_exact.py:241` encodes the atom as `e > value - slack`, which reduces to `c > (margin + c) - min(slack_kind, 1.25*ac_bound)`, that is, `0 > 1.5*max(n,b) - 1.25*b`. This is false for every input, so Z3 always returns UNSAT, whatever the envelope, the benign limits or the topology.
- The margin-factor ablation confirms this. With factor 1.25 (`consolidation_m125_sherlock.md`), every G rule is "inconclusive". At that factor the inequality is `0 > 0`, which is decided by floating-point rounding. The paper's explanation in Section VI-G, "the robust bound (1.25 × oracle bound) is not below the margin", is the same statement: the certificate is the arithmetic fact 1.5 > 1.25.

**Consequence**
"Every P, G and S rule on the 15-bus grid is proved by the robust SMT layer" (Section III) is true only for S rules. For G and P rules, the only substantive evidence is "an 800-flow DE run on one topology did not find a residual above b", plus the search layer at cert-budget 6000. That is exactly the class of evidence the paper rejects in Section IV-I.

**The validated bounds do not cover these rules.** The scenario bound (`scenario_bound.md`) and the budget-stability study (`linac_error_budget*`) validate the per-kind δ_vm = 0.01042 pu. The deployed G-rule voltage clauses have margins of 0.0020 to 0.0264 pu, median 0.0073 (`red_team_sherlock.md`). Most of them are therefore below δ_vm, and they are certifiable only through the unvalidated per-rule `atom_d = 1.25*ac_bound`. Section IV-D's argument (scenario approach, ε = 3.45e-4, stability at 4× and 8× budget) does not apply to the bounds the library actually uses. The same per-kind study shows how weak sampling is here: 1,000 samples gave a maximum of 0.00214 pu, while DE found 0.00834 pu, a factor of 3.9.

**Fix (highest impact)**
- State plainly that for G and P rules the exact layer reduces to the check margin > 1.25 × searched residual bound, and rename the certificate.
- Alternatively, make the SMT layer do real work. Encode the AC residual with a bound obtained independently of the rule, such as the validated per-kind δ, interval or Taylor remainder bounds, or a convex relaxation of AC, and report how many clauses remain certifiable.
- At minimum, apply the scenario and stability validation to each per-rule `ac_bound`.

## Objection 2 (fatal as worded): the "proved" SE rules on 02-Semiurban rest on a remainder δ estimated by the method the paper itself shows to fail

**Code evidence**
- `src/p3/se_proof.py:46-67`: δ = 1.25 × the maximum remainder over `n` uniform samples plus one DE run. `scripts/18_semiurban_consolidation.py:47` sets `PROVE = {"on": False, "n": 150, "budget": 100}`, so δ comes from 150 uniform samples and 100 DE evaluations in 481 dimensions.
- Section IV-I argues that "in 481 dimensions, uniform sampling almost never reaches" the corners. The affine remainder is second order in ‖x − x0‖, and ‖x − x0‖² at a corner is about 3 times its typical value for a uniform sample. So the remainder is largest exactly where δ was not sampled, and a 1.25 safety factor is not justified.
- `corner_check` (`se_proof.py:73-93`) evaluates the worst corners on the full AC model, but only against the old margins (`scripts/18:77`). Its states are never fed into δ. After the margins are raised (`scripts/18:80-83`), nothing re-checks those 24 benign counterexamples, or any corner, against the new margins. "The rule became proved" is asserted by construction (`info["verdict"] = "proved (affine bound)"`), not verified.
- Proposition 2 is circular as a "proof". The margin is defined as 1.5 × (box + δ), so the proposition holds by definition. Its whole content is the validity of δ and of the first-order Jacobian taken by finite differences at one point (`J = np.nan_to_num(J)` silently zeroes failed evaluations).
- **Undisclosed deviation from pre-registration.** The docstring of `scripts/29_prove_se_rules.py:16-17` reads: "Gate (fixed before running): if fewer than 80 % of monitored measurements are proved, search validation stays ... margins are not raised after seeing detections." The gate failed: `se_rule_proof_semiurban.md` reports 4376 of 7137, or 0.61, with "not passed: search validation stays". The margins were then raised anyway (`decision_log.md:169`). The search-validated detection results already existed (`semiurban_consolidation_search_semiurban.md`, dated 2026-11-14; the proved run is dated 2026-11-16). The CEGIS rationale is reasonable, but the paper does not mention the gate, and it presents pre-registration as a strength elsewhere.

**Fix**
- Bound the remainder rigorously, for example with a Hessian or Lipschitz bound of the AC map and the Gauss-Newton step over the box, or interval arithmetic. Alternatively, call the result "worst-case-affine, remainder-validated" rather than "proved".
- Include the corner and DE states in δ, and re-run the corner check against the final margins.
- Disclose the failed gate and the deviation from it.

## Objection 3 (major): Propositions 1 and 2 are mis-stated: noise is combined with max, not added

- Propositions 1 and 2 assume (A4), that noise stays below its calibrated level. The margin, however, is `1.5 × max(noise, bound)` (Section IV-E/H; `synthesis.py`; `scripts/18:59,81`). The residual on telemetry is at most physical bound + noise contribution, and 1.5·max(n, b) < 1.25·b + n whenever n and b are comparable. For example, with n = b the margin is 1.5b against 2.25b needed. So "the noise term of the margin covers (A4)" does not follow.
- Proposition 2's argument ignores noise entirely: it bounds |r| for noise-free AC measurements.
- The paper's own data contradict "no benign state fires a proved rule". The proved semiurban library fires on 0.00889 of benign records in single-record mode (`semiurban_consolidation_semiurban.md`), compared with 0.00000 for SE-BDD. The headline 0.00017 depends on the L = 3 persistence filter, which is not part of any certificate.
- Item (iv) of "What is not guaranteed" says "a certificate never makes a rule fire less". This is false as worded: CEGIS raised 204 to 303 margins per topology, and on the split day this cost one control-and-freeze detection (7 to 6, `semiurban_consolidation_semiurban_split.md`).

**Fix**: use margin ≥ bound + noise, or state the propositions without (A4) and treat noise as an empirical false-alarm rate. Report single-record false alarms of proved rules as violations of the assumptions.

## Objection 4 (major): the threat model leaves attacker-controlled inputs into the margins open

1. **Reporting-robust margins (Section VI-I)** subtract Σ|w_j|(V_j(t) + b_j), where V_j is the range of *reported* values over the last Δ+1 records. The attacker controls those reports. Oscillating a falsified reading with amplitude a ≥ bias makes the range 2a exceed the added residual, so an arbitrary bias can be hidden. No adaptive-attacker evaluation is given.
2. **Calibration poisoning (Section VII).** The paper concedes that the attacker "gains stealth, never a false alarm". Stealth is the attacker's objective, and there is no cap. An attacker with command capability (in scope as industroyer) can *create* a new topology with a valid switching command, which triggers the 300 s calibration window, and then falsify telemetry below the detector threshold during it. This is a two-step attack the paper's own threat model allows, and it permanently widens the margins for that topology. It is not evaluated.
3. **Stealth band.** Voltage margins have a median of 0.0073 pu, while the noise floor is 0.0005 pu. Line-flow margins go down to 0.0000 MW (`red_team_sherlock.md`, p_from row), a degenerate zero-margin clause that the paper does not discuss. The CUSUM attempt failed, with 71 % and 64 % false alarms. A "knows the margins" attacker that drifts at 0.9 × margin is never simulated, so the stealth band is described but not attacked.
4. **Coordinated FDI (Liu et al.).** This is dismissed in one sentence as "outside the reach of every consistency check". The partially observed grid is exactly where unobservable attacks are easiest to construct: an attack in the null space of the SE Jacobian plus pseudo-measurements. The paper does not test it, even though it is the canonical TSG threat.
5. **Command attacks.** Industroyer is 0/9 with L = 3 on Semiurban and 0/7 on both split days, so the "self-consolidating IDS" does not address one of the three process-attack families.

**Fix**: add an adaptive attacker: (a) drift just below each margin, (b) oscillation against the robust margins, (c) poisoning through a commanded topology change, (d) an SE-unobservable FDI on 02-Semiurban. Cap the calibrated noise, and restrict calibration to logged operator procedures, as the paper itself suggests.

## Objection 5 (moderate): the comparison with published IDSs is not like-for-like

- Table IX compares unfiltered results with published numbers obtained on filtered data. The SIMPLE rerun uses framework defaults on all 325 fields without the dataset authors' filtering (`published_ids_sherlock.md`: 100 % alarms, a single alarm start), which is a strawman configuration. GeCo did not finish (`timeout after 14400 s`), so it has no like-for-like result. The fair experiment is to apply the dataset paper's filter to SIMPLE, or to both.
- The library's own increment over the authors' D1 in Table IX is small: D1 detects 12/18 at 8 false alarms, the combined system 14/18 at 10.
- The 18 attacks include arp-spoof, for which no method here is designed.

**Fix**: rerun SIMPLE with the published filtering, or a documented equivalent, or drop the head-to-head claim from the abstract.

---

## Numbers spot-checked (13)

| Claim in paper | Source | Status |
| --- | --- | --- |
| SE latency 120 s median / 160 s max | semiurban_consolidation_semiurban.md | matches |
| FA 0.00889 single / 0.00017 L=3 | same | matches |
| CFC 4/5, drift-off 6/9 vs SE-BDD 3/5, 4/9 | same | matches |
| Search-validated FA 0.00401 | semiurban_consolidation_search_semiurban.md | matches |
| 7 or 8 of 8 corners | same log | matches |
| 204 to 303 margins raised | recorded day 204 to 246; split day up to 303 | matches across both days |
| ~38 % measurements not proved | se_rule_proof: 0.61 proved | matches |
| 19,500 states, 4.6e-3 | se_rule_validation: 4.59e-03 per rule | matches |
| ε = 3.45e-4, δ_vm = 0.01042 | scenario_bound.md, linac_error_sherlock.md | matches |
| Voltage margins 0.0020 / 0.0073 / 0.0264, 112 clauses | red_team_sherlock.md | matches |
| CUSUM 71 %, 64 % | cusum_tc*.md | 0.71024, 0.64225, matches |
| 22/61, 25/61, 27/61; 5/0 p = 0.062; 13/0 p = 0.00024 | statistics.md | matches |
| Seeds 80/79/105 of 218, 25/0 | seed_summary.md | matches |
| Table IX rows | sherlock_metrics_sherlock.md | matches (cited as sherlock_metrics.md) |
| Latency FA 3.5 % (1 to 2 s), 6.9 % (5 s) | robust_margins_sherlock.md 3.46 / 3.47 / 6.88 % | matches, but red_team_sherlock.md reports 6.70 % at 2 s for the same experiment |

## Mismatches and inconsistencies found

1. Section IV-I says "Section VI-C reports that this cost one detected instance". Section VI-C says "the proof costs no detection here". The cost is on the split day (CFC 7 to 6), not on the recorded day.
2. Latency false alarms at 2 s are 3.47 % in robust_margins_sherlock.md and 6.70 % in red_team_sherlock.md. The result is sensitive to the random lag assignment, and only one value is reported.
3. The "scores up to 2.9" for corner counterexamples are cited to semiurban_consolidation_semiurban.md, which does not contain scores. They appear only in decision_log.md.
4. Section IV-D gives the search budget as "32,000 per rule on the 15-bus grid". The synthesised rules use `--cert-budget 6000` and `--bound-budget 800` (`scripts/14:69-70`). The 32,000 applies only to the hand-written R1 to R3.
5. The cited report semiurban_consolidation_semiurban.md has the header "--tag _proved". It is a renamed copy of the _proved run, which is a provenance oddity for a paper that says every number is traceable.
6. A p_from clause with margin 0.0000 MW exists in a "proved" G rule (red_team_sherlock.md) and is not discussed.
7. `se_proof.py:68`: `corner_sign` is computed and never used. This is dead code, harmless, but it suggests the corner logic was not reviewed.

## Ranked changes to neutralise the objections

1. Rename and reformulate the certificates (Objections 1 and 2). Drop "proved" for G, P and SE rules, or supply a rigorous remainder bound and an SMT encoding with a rule-independent δ. Validate per-rule bounds with the scenario and stability study. Fold the corner states into δ and re-check them against the final margins.
2. Correct Propositions 1 and 2: margin ≥ bound + noise, and remove claim (iv). Treat persistence and false alarms empirically.
3. Evaluate an adaptive attacker: sub-margin drift, oscillation against the reporting-robust margins, calibration poisoning through a commanded topology change, and SE-unobservable FDI on 02-Semiurban. Add a noise cap.
4. Disclose the failed 80 % pre-registered gate and the post-hoc margin raise, and fix the IV-I / VI-C contradiction.
5. Give a like-for-like comparison with SIMPLE using the published filtering. Otherwise remove the "best published detectors" comparison from the abstract.
