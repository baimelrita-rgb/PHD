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
