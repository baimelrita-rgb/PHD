# Red team, round 3: synthesis (three independent reviewer agents, full reviews alongside)

Scores: A (power systems) 4/10, B (security, formal methods) 4/10, C (ML, statistics) 4/10; all major revision, close to reject.
Spot checks: 51 numbers checked across the three reviews; all matched their cited reports. The problems are in claims and design, not in numbers.

## Confirmed by the authors in the code

1. **The SMT layer is not informative for invariant rules (P, G).** `src/p3/synthesis.py:199-205` and `:279-281` set the rule-specific error bound to 1.25 x the searched AC residual bound, and `src/p3/oracle_exact.py:238-239` uses min(per-kind, per-atom) as slack. The margin is 1.5 x max(noise, bound), so UNSAT follows by construction whenever the search finds no counterexample. The guarantee for P and G rules is therefore the search bound, not the SMT proof. S rules (state atoms) are unaffected.
2. **The headline paired test cannot fail.** "Combined" is classic OR library, so "only classic detects" is 0 by construction; McNemar then only counts what the OR adds, at a higher false-alarm rate on 01-Basic.
3. **The pre-registered 80 % gate for the SE proof failed (61 %) and the paper does not say so**; margins were raised after detection results existed. The remainder delta is set by 150 uniform samples plus 100 DE evaluations.

## Open objections (to test)

- 02-Semiurban baseline: SE-BDD with fixed sigmas, global threshold at 138 to 170 sigma. Missing: properly weighted BDD, library without oracle (margin = 1.5 x noise), limit check.
- Pooled statistics: 13 discordant instances from 3 grid-day clusters (cluster sign test p = 0.25); additional-day attack magnitudes drawn from the real test days.
- Propositions 1 and 2: margin uses max(noise, bound), needs bound + noise; claim "a certificate never makes a rule fire less" is false (CFC 7/7 to 6/7).
- Threat model: no adaptive attacker; reporting-robust margins subtract variation an attacker controls; calibration window can be opened by a valid switching command.
- Test knowledge in design decisions (DER envelope, tap padding, v2 attack model, L = 3): needs a decision chronology.
- Length: 27 pages A4 single column; TSG limit about 10 pages two-column.

## Text inconsistencies found

- Sec. IV-I says the proof cost one detected instance per Sec. VI-C; VI-C says none (the loss is on the additional day).
- Sec. VII "only 10 % of load Q" vs 90.4 % in the cited report; "every topology certified on 03-Rural" vs 2 of 13 refuted in the 30-min run.
- `[sherlock_metrics.md]` should be `sherlock_metrics_sherlock.md`; 01-Basic "combined" includes the autoencoder, not stated in Table VII or the abstract.
- Latency 2 s: 3.47 % (robust_margins) vs 6.70 % (red_team_sherlock) for nominally the same experiment (lag draw corrected; old report still cited elsewhere).
