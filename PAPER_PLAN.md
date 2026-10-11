# Paper Plan: Multi-task GNN Framework (Detection + Explainability + Blast Radius)

Target: Q2 journal. Timeline: ~6 weeks. Dataset: UNSW-NB15.

This file is the working plan for Claude Code. Follow it phase by phase.

---

## 0. Locked decisions (do NOT reopen)

1. **Paper type:** framework paper (architecture: detection, explainability, blast radius) **with a leakage-aware evaluation protocol as part of the contribution**. Only clean (leak-free) results are reported as results. Leaky results appear only in the leakage-protocol section, as "before vs. after".
2. **Dataset:** UNSW-NB15 only. A second dataset (e.g., OpTC with Larroche 2026 labels) is future work / revision material.
3. **Blast radius = a deterministic graph computation, not a learned prediction.** It is the propagation from the attacked vertex over the graph. The paper calls it "blast radius computation" / "impact estimation", never "prediction".
4. **Crown-jewel feature stays masked** (`mask_crown_jewel_feature=True`) and **`remove_mitre_embedding=True`** in every reported run.
5. **No new audits outside this plan.** If something new looks suspicious, log it in `docs/OPEN_ISSUES.md` and continue. Do not start a new investigation without approval.

## Working rules

- Every phase ends with a committed + pushed report under `docs/` and raw outputs under `analysis/<phase>/`.
- Every number in a report must come from a file in `analysis/` or `out/` (no hand-typed numbers).
- Cite `file:line` for every claim about code. Separate "verified" from "hypothesis".
- Model selection, early stopping and any hyperparameter choice use **validation only**. The test set is touched only for final reported numbers.
- Report all metrics as mean ± std and 95% CI over 5 seeds (42–46).
- Stop and wait for approval **only at the gates (G1, G2)**. Between gates, proceed autonomously.

---

## Phase 1: Decision-gate diagnostics (week 1)

Diagnostics only. No model or code changes.

### 1A. Clean retrain report
- All 5 seeds: mean ± std, 95% CI, per-class F1.
- State whether "window macro F1" is the multi-label head (`y_graph_multilabel`, max(3, 1%) threshold) or the single-label plurality target.
- Seed 44 wall time: per-epoch timings from the log. If no evidence of the cause, write "cause unknown".
- Early stopping: which split and metric it monitors, its patience, and the val curve at epoch 50 for each seed.

### 1B. Detection baselines (same splits, same test set, same metric functions)
1. Trivial window-level: "always-present" and "all-present-if-attack" (already computed, include them).
2. IP-only binary attack detector per window (any flow from 175.45.176.0/30 means attack). Report binary F1, AUC and AP.
3. Edge-level: logistic regression and random forest on the **same 36 clean edge features** (20 structural + 16 Time2Vec, no MITRE, crown-jewel masked). Use 5 seeds and report edge macro F1, per-class F1 and AP.
4. Table: GNN clean vs. each baseline, with the gap and its CI.

### 1C. Explainability head
- Definition of "sparsity" (code and threshold).
- `edge_mask` distribution on test for seeds 42–46: min, max, mean, std, percentiles and a 10-bin histogram.
- Verdict: collapsed (constant mask) or not. If collapsed, give the most likely cause with evidence: loss weights, sigmoid saturation, or L_causal interaction.
- If not collapsed: fidelity+ and fidelity- (remove the top-k vs. bottom-k mask edges and measure the prediction change).

### 1D. `edge_mitre` provenance (short version)
- UNSW-NB15 has no native ATT&CK labels. Show exactly how `edge_mitre` is produced. Is it a mapping from `attack_cat`, i.e. from the label?
- Report a 2x2 table of has_technique × is_malicious per split, and the mutual information with `edge_label`.
- Save the result as `docs/EDGE_MITRE_PROVENANCE.md`.

### 1E. Blast radius: current implementation
- Show the code that computes blast radius: its input, its output, the algorithm (BFS / k-hop / weighted), whether paths are directed, and whether it respects time ordering.
- **Seed vertex source:** where does "the attacked vertex" come from at evaluation time?
  - from ground-truth labels: acceptable only as an oracle reference
  - from the model's own detections: the pipeline version
  - Report which one the current code uses.
- Graph structure of malicious traffic per split:
  - number of distinct attacker source IPs and victim destination IPs
  - whether malicious edges form a star (few sources to fixed victims)
  - number of multi-hop malicious paths (length ≥ 2, i.e. a victim later acts as a source)

### Gate G1: `docs/DECISION_GATE.md`

| # | Condition | Measured value | Pass/Fail |
|---|-----------|----------------|-----------|
| 1 | GNN clean edge macro F1 > best of LR/RF by a margin outside the CI | | |
| 2 | Explainability head not collapsed, or a clear and fixable cause identified | | |
| 3 | Blast radius can be computed from model-detected attacked vertices (not only from labels) | | |

Add a list of anything that blocked a measurement.

**Commit, push, STOP and wait for approval.**

Outcome mapping (decided in advance):
- All pass: Phase 2 as written.
- 1 passes, 2 fails: explainability becomes a qualitative case study plus fidelity numbers. No further fixing beyond Phase 2B.
- 1 fails: the paper's emphasis shifts to the evaluation protocol, and the framework is presented as a case study. The same phases apply, but the headline claims change.

---

## Phase 2: Fixes and final configuration (weeks 2–3)

### 2A. Detection target
- **Primary detection metrics:** edge-level multi-class (macro F1, per-class F1, AP) and window-level **binary** attack detection.
- Window-level multi-label macro F1 is reported **only next to** the trivial baselines (always-present, all-present-if-attack), with one sentence explaining that UNSW-NB15 attack windows contain 5–6 classes simultaneously.
- Drop the single-label plurality target from headline results. Reconnaissance and Shellcode have zero targets in all splits, and DoS has zero in test. Mention this in Limitations.
- Verify that the plurality rule (`graph_builder.py:172-174`) is used consistently in training and evaluation, and that the max-index rule is used nowhere.

### 2B. Explainability fix (only if G1 #2 failed with a fixable cause)
- Make a small sweep of the explanation-loss weight / sparsity weight (≤ 5 values), selected on **validation** fidelity.
- Report fidelity+, fidelity- and the sparsity of the final config.
- Hard limit: 3 working days. If still collapsed, fall back to the qualitative case study.

### 2C. Blast radius module: formalize and evaluate

**Definition** (write it in `docs/BLAST_RADIUS.md` and implement it exactly):
- Input: snapshot graph G_w = (V, E_w), a set of attacked vertices S, and a hop limit k.
- BR_k(S) = the set of vertices and edges reachable from S by directed paths of length ≤ k (time-respecting if edge timestamps are available).
- Optional weighted variant: rank the reachable edges by path probability, using the model's edge maliciousness scores.

**Two seed sources:**
- Ŝ_w (pipeline): vertices incident to edges the model flags as malicious, with p ≥ τ (τ chosen on validation).
- S*_w (oracle reference): vertices incident to ground-truth malicious edges.

**Evaluation** (computation quality under realistic detection, not a prediction claim):
- Jaccard(BR_k(Ŝ), BR_k(S*)) for k = 1, 2, 3.
- Coverage: the fraction of ground-truth malicious edges inside BR_k(Ŝ), against the size |BR_k(Ŝ)| (cost to the analyst).
- Sensitivity to τ (a curve).
- Reference baselines with the same |S|: random vertices, and highest-degree vertices.
- Runtime per snapshot.
- Report the multi-hop statistics from 1E honestly. If propagation is mostly 1-hop (a star), say so in Limitations.

### 2D. Final run
- Freeze the config in `configs/final.yaml`.
- Run 5 seeds. Save checkpoints, metrics JSON and per-class outputs.
- Tag the commit `final-results-v1`.

---

## Phase 3: Ablations and comparisons (weeks 3–4)

1. **Multi-task value:** detection-only vs. detection + explanation vs. full model. Use the same seeds and report edge macro F1 and AP.
2. **Graph value:** GNN vs. LR and RF on the same clean features (from 1B), and GCN and GAT on the same clean features.
3. **Leakage protocol table:** leaky vs. clean for the main metrics, plus the four tests in `tests/test_leak_removal.py` (bit-identical default, tripwire, out-of-range constant, permutation guard).
4. **Temporal component:** with vs. without Time2Vec.

### Gate G2: `docs/RESULTS_FREEZE.md`

Include all tables generated from files, the list of figures, and every open issue.

**Commit, push, STOP and wait for approval.** After G2, no new experiments, except those a reviewer later requests.

---

## Phase 4: Writing (weeks 4–6)

### Paper structure
1. Introduction: from detection to response (detect, explain, scope the impact)
2. Related work: GNN-based IDS, GNN explainability, and evaluation pitfalls (Arp et al. USENIX Sec 2022; Larroche 2026 arXiv:2607.29390; Wang et al. R+R, ACSAC 2025)
3. Framework architecture: the encoder, the three heads, and the blast radius computation
4. Leakage-aware evaluation protocol: tripwire, permutation, label-only and trivial baselines, validation-only selection
5. Experimental setup: UNSW-NB15, windowing, splits, and label-supply statistics (`out/table_label_supply.tex`)
6. Results: detection, explainability and blast radius, clean only, against baselines
7. Case study: one attack window end to end (detection, explanation, blast radius)
8. Limitations: synthetic dataset, star-shaped attack topology, window-label co-occurrence, single dataset
9. Conclusion and future work (OpTC with Larroche's labels for multi-hop blast radius)

### Deliverables
- `paper/` with the target journal's LaTeX template.
- All tables are auto-generated from `analysis/` and `out/` by a script (`scripts/make_tables.py`).
- All figures are generated by a script (`scripts/make_figures.py`).
- A reproducibility README: the environment, the commands to regenerate every table and figure, and the seeds.

---

## Definition of done

- [ ] G1 report pushed and approved
- [ ] Final config frozen, 5-seed run tagged
- [ ] G2 report pushed and approved
- [ ] Every number in the paper traceable to a file
- [ ] Draft complete, with Limitations written honestly
- [ ] Reproducibility README tested from a clean clone
