# Week 1: model-free checks (PAPER_PLAN_TRIAD.md, Section 4)

Runs checks 1, 3 and 4 of Week 1 directly on the raw UNSW-NB15 export. Check 2
(old explanation mask + GNNExplainer) needs the trained model and runs in the model repo.

## Run

```bash
pip install -r week1/requirements.txt
python -m week1.checks \
  --data /path/UNSW-NB15_1.csv /path/UNSW-NB15_2.csv /path/UNSW-NB15_3.csv /path/UNSW-NB15_4.csv \
  --out analysis/week1 \
  --split-file split.json          # recommended: the model pipeline's own split
  --features struct+flow           # struct | struct+flow | struct+flow+ttl
```

Writes `analysis/week1/week1_report.{json,md}`. The markdown ends with the pre-registered
G1 rules evaluated on the numbers.

`split.json` format: `{"train": [window ids], "val": [...], "test": [...]}`, where a window
id is `floor(Stime / 300)`. Without it, the script builds its own per-session,
attack/benign-stratified chronological 70/15/15 split. That split is close to the paper's
description but not guaranteed identical, so paper numbers must use `--split-file`.

## What each check computes

| Check | Output |
|---|---|
| 1. Detection baselines | IP-only rule (src in 175.45.176.0/30), LR, RF over 5 seeds: macro F1, macro AP, binary F1, per-class F1, 95% CI |
| 3. Next-window exposure | for each node in window t: is it involved in a malicious edge at t+1? Baselines persistence, BFS-1, BFS-2, degree, random: AP, AUC, AP on NEW exposure, coverage@budget |
| 4. Malicious-traffic shape | attacker/victim counts, share from the attacker /30, top-1/top-4 source share, pivot nodes (victim later attacks), classes per attack window |

Feature sets: `struct` = per-window graph features only; `flow` adds aggregated flow
statistics; `ttl` adds sttl/dttl/ct_state_ttl, which are known to separate attack from
benign traffic in UNSW-NB15 on their own. Report `struct+flow` as the main baseline and
`struct+flow+ttl` only to show the TTL effect.

## Tests

`python -m pytest week1/tests` runs the pipeline on a synthetic file in the raw format.
It tests the plumbing only; its numbers are meaningless.
