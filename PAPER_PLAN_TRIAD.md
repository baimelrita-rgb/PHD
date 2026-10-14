# Paper Plan v2: TRIAD-GNN (bidirectional attack subgraphs)

Supersedes the paper framing in `PAPER_PLAN.md`. Phase 1 diagnostics from that plan are
reused as Week 1 here. Locked decisions 1-5 of `PAPER_PLAN.md` still hold (crown-jewel
masked, MITRE embedding removed, validation-only selection, numbers only from files).

Target: Q2 with UNSW-NB15 only; Q1 requires adding LANL 2015 (Week 4).

---

## 1. The claim

Explanation and blast radius are the backward and forward halves of one object: the
attack subgraph around a detection. TRIAD-GNN learns that object directly.

- Backward half (explanation): which observed edges caused this detection.
- Forward half (scope): which nodes are exposed in the next window.
- The detection decision sits at the center and constrains both halves.

## 2. What changes in the model (minimal delta on the existing code)

Kept unchanged: graph builder, features, GAT encoder, EMA node memory, Detection Head
(multi-label), per-edge head.

Replaced: the separate Blast-Radius Head and Explainability Head become one
bidirectional head. Removed from the paper: ATTACK-BERT/MITRE consistency, anomaly layer.

### 2.1 Bidirectional head

Edge representation (already computed for the per-edge head):

    r_ij = [h_i || h_j || x_ij]

Shared trunk, two outputs:

    u_ij        = MLP_shared(r_ij)
    m_back_ij   = sigmoid(w_b . u_ij)                    # explanation mask, edge level
    q_fwd_i     = sigmoid(w_f . [h_i || mem_i || a_i])   # exposure, node level
    a_i         = max_{j : (i,j) or (j,i) in E_t} m_back_ij   # node anchor from backward mask

Forward is node-level on purpose: next-window edges may not exist yet at t.

### 2.2 Losses (each is new code of roughly 10-30 lines)

    L = L_det + L_edge + l1*L_sparse + l2*L_fid + l3*L_anchor + l4*L_temp

| Term | Definition | Role |
|---|---|---|
| L_sparse | mean(m_back) | compact explanations (existing) |
| L_fid | CE(f_det(G_t with edge weights m_back), stopgrad(y_hat_det)) | sufficiency: the explanation alone reproduces the decision |
| L_anchor | mean_i q_fwd_i * (1 - max_{u in N_k(i)} a_u) | scope must grow from the explanation, not from anywhere |
| L_temp | BCE(q_fwd_i(t), stopgrad(z_i(t+1))), z_i(t+1) = max edge-head maliciousness over edges of i at t+1 | self-supervised scope: no propagation labels needed |

Notes:
- L_temp uses t+1 only inside the training loss, never at inference. t and t+1 must be
  in the same split; drop the last window of each split segment.
- k = 2 for L_anchor (= number of hops the GAT sees is 3; keep k <= L).
- Weights l1..l4: small grid (3 values each, coordinate-wise) on validation only.

## 3. Evaluation (all measurable from existing UNSW-NB15 edge labels)

| Task | Primary metric | Secondary |
|---|---|---|
| Detection | edge macro F1, AP; window binary F1 | per-class F1 |
| Explanation | fidelity+ / fidelity- at matched sparsity | precision@k vs malicious edges |
| Scope | AP / AUC of q_fwd for "node involved in attack at t+1"; coverage vs budget curve | same on the NEW-exposure subset (not involved at t) |

Baselines (all cheap):
- Detection: IP-only rule (175.45.176.0/30), LR and RF on the same clean features,
  detection-only GAT (TRIAD with heads off).
- Explanation: GNNExplainer (PyG, post-hoc on the same model), attention weights,
  random mask at matched sparsity, "edge-head score as explanation".
- Scope: persistence (exposed at t+1 = involved at t), BFS-k from detected nodes,
  degree ranking, random.

Ablations (flags only): no L_fid, no L_anchor, no L_temp, separate heads (old design).

## 4. Schedule with kill gates

### Week 1: cheap checks BEFORE building anything (no new model code)
Run on the existing trained model and data:
1. IP-only, LR, RF detection baselines (= old Phase 1B).
2. Old explanation mask: distribution, collapse check (= old 1C); GNNExplainer on it.
3. Scope baselines on the next-window exposure target: persistence, BFS-k, degree.
   Report the size of the NEW-exposure subset in test.
4. Malicious-graph shape per split (= old 1E): star or multi-hop.

Gate G1 (decide here, not later):
- If persistence AP >= 0.95 on UNSW: the forward half cannot be shown on UNSW alone.
  Week 4 (LANL) becomes mandatory, not optional.
- If RF edge F1 is within CI of the GNN: detection is reported as "on par", and the
  paper sells explanation + scope only.
- If NEW-exposure subset in test < 30 nodes: report it descriptively only.

### Week 2: implement bidirectional head + 4 losses (Section 2)
Unit tests: shapes, stopgrad on L_temp target, no t+1 data at inference.

### Week 3: 5 seeds (42-46), baselines, ablations; freeze config, tag `triad-v1`.

### Week 4 (Q1 path): LANL 2015
Auth graph (src computer -> dst computer), 5-min windows, red-team events as labels.
Real multi-hop lateral movement: the forward half is tested where it matters.
Only detection + scope + one case study; no new features beyond structural + T2V.

### Weeks 5-6: writing
Reuse: Sec 1-2 (rewrite contributions), Sec 3 encoder, Sec 4.1 formalism (rename
"forecasting" to "next-window exposure"), complexity table, new figures.
New: Sec 3 bidirectional head, Sec 5 results, case-study figure
(detection -> backward subgraph -> forward exposure on one window).
Must fix regardless: all 27 references against DOIs; table order; declarations.

## 5. Paper outline

1. Introduction: detection alone does not answer "why" and "what next".
2. Related work: GNN IDS, GNN explainability, propagation/attack graphs.
3. TRIAD-GNN: encoder, bidirectional head, chain-consistency losses.
4. Formal properties: exposure learning problem, label aggregation (Prop. 1, short),
   complexity.
5. Experiments: setup, detection, explanation, scope, ablations, case study.
6. Limitations: synthetic data, star topology on UNSW, small NEW-exposure set.
7. Conclusion.

## 6. Predicted outcomes (estimates before Week 1; update after G1)

| Experiment | Expected | Confidence |
|---|---|---|
| Edge F1 stays >= 0.95 with clean features | likely | high |
| GNN beats RF outside CI on UNSW | uncertain | ~30% |
| IP-only rule reaches high binary detection | likely | high |
| Trained mask beats GNNExplainer on fidelity at matched sparsity | likely | ~70% |
| Mask beats "edge-head score" on precision@k | unlikely | ~20% (do not make this the claim) |
| Forward head beats BFS-k on coverage-per-budget | likely | ~60% |
| Forward head beats persistence on UNSW | unlikely | ~25% (star topology, repeated victims) |
| Forward head beats persistence on LANL | plausible | ~50% |
| Each consistency loss gives a significant gain on UNSW | uncertain | ~35% (46 test windows) |

Acceptance estimate: Q2 with UNSW only ~40%; Q1 with UNSW only ~15%;
with LANL added: Q2 ~60%, Q1 ~30%.
