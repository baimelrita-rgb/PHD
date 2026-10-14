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

---

## 12. Update after reading Larroche (arXiv:2607.29390v1, read in full)  [verified from the PDF]

**Links stated in the paper**
- Code: https://github.com/cl-anssi/LMDEval/ (footnote 1, p.2). The paper says it releases "code implementing" its preprocessing and labeling policies. Whether the OpTC label files themselves are in the repository is NOT stated: check the repo.
- OpTC: https://github.com/FiveDirections/OpTC-data (ref. 8). LANL: https://doi.org/10.17021/1179829 (ref. 12).
- Majorczyk et al., "A new hope for DARPA OpTC", ACSAC Workshops 2025 (ref. 21): process-based labels (563 flows) that Larroche starts from.

**OpTC facts that change the plan**
- 9 days: 17-22 Sep benign only; 23-25 Sep one red-team scenario per day. Recommended test = last 3 days (Sec. 4.3).
  There are no attack labels in the first six days, so a supervised model cannot train on them.
- No system logs for half of the workstations and all servers; lateral-movement flows must be taken from
  FLOW START system events, internal hosts only, duplicates removed, all IPs of a host mapped to one node.
- After his preprocessing (Table 4): 897 nodes, 36,227,823 events, 1,354 malicious flows of which only
  **244 lateral-movement flows**, over three scenarios. Host-based labeling gives ~25,000 "malicious" flows (overly broad).

**LANL facts**: all labeled malicious authentications are one intrusion, almost all from host C17693; use only for
unsupervised evaluation, or for detectors trained on another dataset (Sec. 5.2). After preprocessing: 16,159 nodes,
369.6M events, 702 malicious. Recommended split: train on the first 41 hours, test on the rest; keep all remote LogOn events.

**State of the art under a fair protocol (Tables 5-6)**: Pikachu, Euler and Argus drop sharply.
LANL AP 0.00-0.09 %. OpTC, strictly lateral movement: AUC 43-53, AP about 0.01 %; all malicious events: AUC 80-86, AP 0.5-3.4 %.
Conclusion of the paper: lateral movement detection "remains an open problem".

**Consequences for this plan**
1. **The 7-class supervised detection head does not apply.** The labels are binary (malicious / lateral movement) and
   scarce. The realistic setups are (a) benign-trained anomaly scoring on days 1-6, tested on days 7-9, which is the
   community protocol, or (b) leave-one-scenario-out over the three attack days with ~244 positives in total.
   This is a bigger model change than "remove MITRE and fix the mask".
2. **The temporal self-distillation idea of the TRIAD plan fits (a)**: scope can be learned without propagation labels.
3. **The G0 thresholds in Sec. 4 are probably too high** (244 lateral-movement flows in total). Replace them by the
   actual counts from the LMDEval labels: compromised hosts, first-compromise events per scenario, multi-hop chains
   per scenario. Decide the thresholds only after seeing them, and write them down before any modeling.
4. **Evaluation must follow the paper**: event-level metrics on exactly the same events for all methods, test = last 3 days,
   report both "lateral movement only" and "all malicious" labels. Baselines: run Euler and Argus with their released code
   through LMDEval (Pikachu, Euler, Argus are already adapted there).
5. **The bar is low in absolute terms and high in credibility**: a method that beats these numbers under this protocol
   would be a real result; a method that does not is still publishable only as part of an evaluation study.

**Revised guesses** (replace Sec. 8): scope beats BFS/persistence ~20 %; any model beats Argus/Euler on lateral-movement-only AP
~35 %; acceptance Q2/Q1 given a full pipeline ~35 % / ~10 %. These are guesses and should be replaced by the G0 and G1' measurements.

**First action**: open the LMDEval repository and answer: are the OpTC label files included, in what format
(per flow? per host and time?), and how many compromised hosts per scenario.

---

## 13. Update after the OpTC README, errata, eCAR notes, ground-truth PDF and LMDEval README  [verified from the files, except where marked]

**Data hosting and size (OpTC README)**
- Data is on Google Drive: https://drive.google.com/drive/u/0/folders/1n3kkS3KR31KUegn42yk3-e6JkZvf0Caa
  with three folders: `ecar-bro`, `ecar`, `bro`. "Approximately a terabyte" compressed in total.
- `ecar-bro` holds only the eCAR FLOW-START events (annotated with the bro-id), with sub-folders `short` (events with
  missing data), `evaluation` (red-team period) and `benign`. This is the folder that is most likely much smaller than `ecar`.
  Whether `extract_optc.py` accepts `ecar-bro` or needs `ecar` is NOT known: check `python extract_optc.py -h`.
- DARPA: data released "as-is", "practically guaranteed to be imperfect"; errata lists duplicate process objects,
  missing hashes in module loads, acuity_level 0 for FLOW OPEN, and disk-device paths. None of these is about flow endpoints,
  but they are the reason the preprocessing must be taken from LMDEval and not rewritten.
- Data from 500 of ~1000 hosts only (no system logs for the rest).

**LMDEval (README)**: `extract_optc.py` extracts FLOW START events from the raw gzipped JSON, drops irrelevant/duplicate flows,
maps IP -> hostname with `optc_known_addresses.json` and labels with **`optc_redteam.csv`** (so the label file is in the repo;
its format is not yet seen). `extract_lanl.py` needs `auth.txt.gz` and `redteam.txt.gz` (auth.txt.gz is not in the user's current LANL download).

**What the red-team ground truth documents (my reading of the PDF; transcribe and verify against `optc_redteam.csv`)**

| Day | Scenario | Documented spread | First-compromise events (approx.) | Max chain depth |
|---|---|---|---|---|
| 23 Sep | Plain PowerShell Empire | 0201 -> 0402 -> 0660 (WMI) -> DC1 (WMI) -> 14 workstations (WMI, 14:45) | 18 hosts (0201, 0402, 0660, DC1, +14) | 4 |
| 24 Sep | Custom PowerShell Empire | phish 0501 and 0811; 0501 -> DC1; 0501 -> 0974 -> 0005 (RDP); DC1 -> 6 workstations (15:42) | 11 hosts | 2 |
| 25 Sep | Malicious notepad++ upgrade | 0051 and 0351 infected independently; no lateral hop documented | 2 hosts | 0 |

So: about 30 first-compromise events in total, with timestamps in the log, two scenarios with real multi-hop chains, and a third with none.
Assumption A1 (observable first compromise) is satisfied in the documentation. The spread from DC1 is again a fan-out
(14 and 6 targets at once), but DC1 also talks to every host legitimately, so "neighbors of a compromised host" is NOT a
cheap oracle here: the budget (hosts flagged per window) is what separates a good scope method from BFS.

**Consequences (replace the corresponding parts of Secs. 4, 5, 7 and 12)**
1. **G0 thresholds**: "at least 30 first-compromise events in test" cannot hold for one scenario (18 / 11 / 2). Use leave-one-scenario-out
   and pool the three folds, report bootstrap CIs over hosts, and state in the abstract that scope is evaluated on ~30 events.
   Day 3 has no chain and is not a scope test.
2. **A learned forward head is not trainable**: days 1-6 contain no compromise, so there is nothing for a learned
   scope head (or the temporal self-distillation of the TRIAD plan) to learn from. Use the original locked decision of
   `PAPER_PLAN.md`: **blast radius is a deterministic graph computation** seeded by the model's own detections,
   BR_k(S_hat), evaluated against the documented chains (coverage of next-compromised hosts vs. size of the set).
3. **Model** = benign-trained anomaly scorer on days 1-6 + explanation (subgraph around detections) + deterministic blast radius.
   The 7-class supervised head, `edge_mitre` and `L_causal` are removed. This is a larger change than before, stated openly.
4. **Novelty is modest**: the joint pipeline and its fair evaluation, not a new learned propagation head. Position it that way.
5. **Case study for free**: the ground truth gives an end-to-end story (Day 1: 0201 -> 0402 -> 0660 -> DC1 -> 14 hosts) that can be
   shown as a figure: detections, explanation subgraph, predicted blast radius vs. documented spread.

**Immediate actions (user's side, then I write `optc_audit.py`)**
1. Clone https://github.com/cl-anssi/LMDEval and send: the first 20 lines of `optc_redteam.csv`, the number of rows, and the output of
   `python extract_optc.py -h` (to learn which Drive folder it needs).
2. Open the Drive folder, and check the sizes of `ecar-bro/benign`, `ecar-bro/evaluation` (and `ecar` if needed). Start with `ecar-bro`.
3. Decide where ~100s of GB can be stored, or use a subset of benign days for training (to be justified, not silent).
