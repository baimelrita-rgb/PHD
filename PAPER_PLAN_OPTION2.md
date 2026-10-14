# Paper Plan: Option 2 - the multi-task model, tested on data where it can be tested

Supersedes `PAPER_PLAN_TRIAD.md` (its UNSW-based gates have failed, see Section 1).
Reuses from `PAPER_PLAN.md`: the working rules (numbers only from files, validation-only
selection, 5 seeds 42-46, leak tripwires) and the formalism of Sections 4.1-4.2 of the
manuscript (assumptions A1-A5).

Status of each claim below: **[verified]** = read in a report or source in this project;
**[search]** = from a web search snippet, to be checked at the source; **[guess]** = my estimate.

---

## 1. Why a different dataset (what the project's own reports establish)  [verified]

From `docs/DECISION_GATE.md` and `analysis/` in `baimelrita-rgb/STT-GNN-`:

- UNSW-NB15: 4 attacker IPs, 10 victim IPs, 0 multi-hop malicious paths in every split.
  A non-learned "distance to compromised node" heuristic reaches blast AUC 0.982 / AP 0.891
  vs 0.76 / 0.44 for the learned head. The forward half of the idea cannot be shown there.
- Clean (leak-free) edge macro F1 = 0.2966; RF on the same features = 0.4222.
- LANL as audited (`results/lanl_edge_00_label_audit.md`, flows + redteam only): 899 malicious
  edges, 1 malicious source, 4 destinations, and 0 malicious edges in val and test.
- [search] A 2026 evaluation paper (Larroche, ANSSI, arXiv:2607.29390) reports that all labeled
  malicious LANL authentications belong to one simulated intrusion, almost all from one source
  host, and that LANL should only be used for unsupervised evaluation.

So LANL is not a candidate for a supervised propagation head either. UNSW-NB15 and LANL are out
as the main evidence for blast radius and explanation.

## 2. Candidate datasets

| Dataset | Why it might work | Open questions (must be answered by the audit in Sec. 4) |
|---|---|---|
| **DARPA OpTC** | [search] Host-to-host flow edges, a simulated enterprise, red-team campaign over several days, ~976 hosts. Larroche's paper evaluates graph lateral-movement detectors on it | [search] No official event-level labels, only a ground-truth description with host names / IPs / process IDs. Labeling policy changes results a lot. Corrected labels (Majorczyk et al., CSET 2025) are announced but I found no release link. Larroche's labeling policies and code are said to be at github.com/cl-anssi/LMDEval; one third-party summary says the OpTC label set is manual and unreleased - check the repo |
| LMDG (arXiv:2508.02942) | [search] A dataset-generation framework built for lateral movement | Unknown whether it yields labeled multi-hop chains at useful volume. Needs reading |
| LANL with `auth.txt.gz` | Real red-team, authentication edges | Single intrusion, one source host [search]. Only usable for detection, not propagation |

**Working choice: OpTC**, labeled with the LMDEval policy if its labels are available, otherwise
with a labeling policy we define from the ground-truth document and report openly.
This is conditional on the audit in Section 4 (gate G0).

Blocked in the cloud sandbox: arxiv.org, github.com (data), csr.lanl.gov, research.unsw.edu.au.
Downloads and the heavy preprocessing happen on the user's machine, or the sandbox network is
opened (Settings -> environment -> Network access).

## 3. What the paper claims (and what it must not claim)

Claim: one model that detects, explains and scopes an intrusion, evaluated on a dataset with
real multi-host campaigns, against baselines that are cheap and strong.

Rules fixed in advance because of what went wrong on UNSW:
1. No claim survives unless it beats the pre-registered baselines outside the confidence interval.
2. Every claim not supported is dropped from the abstract, not softened.
3. Leak tripwires are part of the paper (constant / permuted / zeroed channels, label-only lookup
   baselines, IP-only or host-only baselines). They run on every model before any result is reported.

## 4. Gate G0 - data audit BEFORE any modeling (week 1, no GPU)

Run the project's `analysis/label_supply` and `analysis/decision_gate` logic on the OpTC graph
(host nodes, flow-start edges, 5-minute windows). Required outputs, all from files:

| Check | Proposed pass threshold [guess] |
|---|---|
| Distinct compromised hosts | >= 20 |
| First-compromise events (assumption A1) in test | >= 30 (so ranking metrics have power, A2) |
| Multi-hop chains (a compromised host later acts as a source toward a new host) | >= 10 in train and >= 5 in test |
| Share of malicious edges from the single largest source host | < 50% |
| Positive edge rate | reported; if < 0.1% use AP and TPR@fixed-FPR, not F1 |
| Labeling policy | named and justified; results reported under at least 2 policies (Larroche's concern) |
| Split | by red-team scenario or day if the ground truth supports it, never random windows |

If G0 fails: stop Option 2 and go to Option A (see Section 9). Nothing has been spent on modeling.

## 5. Model changes (minimal, driven by the reports)

1. **MITRE channel removed from the model.** `edge_mitre` is a recoding of the edge's own label
   [verified], and `L_causal` still reads it during training even in the clean config [verified].
   Remove the embedding and `L_causal`. ATT&CK stays as a post-hoc annotation of detected
   subgraphs, not a model input or loss term. (Frees the paper from the "approximate mapping" weakness.)
2. **Explainability fix, time-boxed to 3 days.** Cause of collapse: mean-mask L1 penalty with
   strongly negative logits (all masks < 0.5, sparsity exactly 1.0) [verified; cause is a hypothesis].
   Replace the L1 mean penalty by a top-k budget (or anneal beta from 0), sweep <= 5 values on
   validation fidelity. If still collapsed: report explanation as a case study only.
3. **Blast radius redefined** as next-window exposure (node involved in a malicious edge at t+1)
   with the first-compromise subset reported separately. Seeds for the scope computation come from
   the model's own detections (pipeline) and from the labels (oracle reference), as in `PAPER_PLAN.md` 2C.
4. **Optional, only if Stage 1 passes:** the bidirectional-subgraph head of `PAPER_PLAN_TRIAD.md`
   (backward mask + forward exposure with the anchor and temporal self-distillation losses).
   It is the novelty claim, so it is built last and kept behind a flag.
5. **No node identity features.** Host IDs and the crown-jewel feature stay masked; node memory is
   keyed by structure, not by host name. The tripwire must show it.

## 6. Baselines (pre-registered)

- Detection: host-only / source-only rule, LR, RF on the same clean features, GCN, GAT
  (already in `baselines/`), and at least one published detector run through Larroche's evaluation code.
- Explanation: GNNExplainer on the same model, attention weights, random mask at equal sparsity,
  the per-edge classifier score used as an explanation.
- Scope: persistence, BFS-k from the same seeds, degree, random, at equal budget (nodes flagged per window).

## 7. Stages and kill gates

| Stage | Weeks | What | Gate |
|---|---|---|---|
| 0 | 1 | Data access + G0 audit | G0 above |
| 1 | 2-3 | Graph build, tripwires, baselines, clean base model (detection only) | **G1'**: base model beats best of LR/RF/GAT outside the CI on AP (not F1), or at least matches them while fixing a failure they have. If not: Option A with OpTC as the second dataset |
| 2 | 4 | Explainability fix + scope computation on pipeline seeds | **G2'**: explanation fidelity beats GNNExplainer at equal sparsity; scope beats BFS-k/persistence at equal budget on first-compromise nodes. Claims that fail are dropped |
| 3 | 5-6 | Bidirectional head (optional), 5 seeds, ablations, freeze config, tag | one pass, no tuning on test |
| 4 | 7-9 | Writing; every table generated from files; reference check against DOIs | - |

Total about 9 weeks if G0 passes. Kill gates mean a failure costs 1-3 weeks, not the whole plan.

## 8. Predictions before running anything  [guess]

| Event | Probability |
|---|---|
| G0 passes on OpTC with usable labels | ~50% (depends on label availability) |
| Clean base model beats RF/LR outside the CI on AP | ~40% |
| Explanation beats GNNExplainer at equal sparsity | ~55% |
| Scope beats BFS-k / persistence on first-compromise nodes | ~30% (hard: heuristics from compromised neighbors are strong) |
| Acceptance, Q2 / Q1, conditional on reaching Stage 3 | ~40% / ~15% |

## 9. Fallback (built into the plan)

If any of G0, G1' fails, the OpTC audit and baselines are not wasted: they become the second
dataset of the measurement paper (Option A), which removes its main weakness (single dataset,
self-inflicted bug). So Option 2 has a floor.

## 10. Decisions needed from the user

1. Can OpTC be downloaded and stored locally (size to check on the official page), and what GPU is available?
2. Can the sandbox network be opened (arxiv, github, csr.lanl.gov), or should downloads happen only locally?
3. Is the Larroche LMDEval repository available to you, and are its OpTC labels included?
4. Authors: Larroche's paper evaluates exactly this problem; the framing should position this work
   as following its evaluation recommendations, not competing with it.

## 11. Immediate next steps (no modeling)

1. Fetch `cl-anssi/LMDEval`, read its labeling policy and what OpTC labels it ships.
2. Write `scripts/optc_audit.py` reusing `analysis/label_supply` functions; produce the G0 table.
3. Reference check: verify all 27 references of the manuscript against DOIs (at least 8 were not found).
