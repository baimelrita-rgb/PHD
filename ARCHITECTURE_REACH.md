# REACH: a Detect -> Explain -> Blast-radius architecture grounded in what has worked

Written 2026-10-31 after the pre-registered experiments P1-P3 and E1 (STT-GNN- repo, branch `claude/dep-paper`,
`dep/pilot/RESULTS_*.md`, `dep/explain/RESULTS_E1.md`). Tags: **[ours]** = measured in our experiments;
**[lit]** = reported in a paper or product documentation (not verified by us); **[guess]** = estimate.

---

## 1. What our own experiments taught us [ours]

| Observation | Evidence | Design consequence |
|---|---|---|
| A simple pooled autoencoder beat every structured method on the held-out test | OpTC host-day AUC 0.960 vs ours 0.673 | Detection core = simple, pooled, self-supervised reconstruction |
| Per-host baselines fail with short history | ~1,000 hosts x 4 training days on OpTC | Share one model across hosts; condition on host role, not one model per host |
| Hourly aggregates hide single malicious events | DEDALE: 1 C2 beacon per day invisible | Score individual events, aggregate later |
| Network sensors at the perimeter do not see lateral movement | OpTC Zeek: 60 internal flows per hour, all ICMP | Use host telemetry (process/file/flow events) |
| Statistical "tactic channels" did not identify the attack stage | E1 accuracy 0.275 = random | Map to ATT&CK from event semantics (process, command line, port), not statistics |
| AE reconstruction error grouped by ATT&CK channel was the best explainer; KernelSHAP was at or below random | E1 0.530 vs SHAP-AE 0.311 (OpTC 0.069) | Explanation = the model's own per-event reconstruction evidence |
| Naive gates can pass for the wrong reason | P1: model ranked host types | Keep within-host controls, pre-registration, several seeds |

## 2. What exists today

### 2.1 Cyber security
- **Provenance-based IDS (host telemetry graphs).** Kairos (S&P 2024) detects anomalous events with a temporal GNN
  encoder-decoder and outputs compact attack graphs [lit]. MAGIC (USENIX Sec 2024) is self-supervised masked graph
  representation learning [lit]. Orthrus (USENIX Sec 2025) targets "quality of attribution": a GNN flags nodes,
  then causality analysis reconstructs a compact attack path; it cuts the nodes an analyst inspects by orders of
  magnitude [lit].
- **Reality check.** "Sometimes Simpler is Better" (USENIX Sec 2025) re-implemented 8 systems: a simple neural
  network (Velox) reaches state of the art on 5 of 7 DARPA datasets; true malicious nodes are 41-123, not
  thousands as earlier labels claimed [lit]. PIDSMaker (KDD 2026) packages the 8 systems, pre-processed DARPA
  TC and OpTC data and consistent ground truth; it warns about seed instability [lit].
- **Lateral movement.** Euler, Argus, Jbeil and CyberGFM model lateral movement as temporal link prediction [lit].
  Larroche (2026) shows published results are over-optimistic under fair evaluation on LANL and OpTC [lit].
- **LLM investigators.** OCR-APT (CCS 2025) uses GNN subgraph anomaly detection plus an LLM that writes
  kill-chain-staged reports, evaluated on DARPA TC3 and OpTC. ANANKE, ProvAgent and Microsoft's DTDA ground LLM
  reasoning in bounded graph evidence [lit]. These papers report that LLMs help most when grounded in
  deterministic graph analysis [lit].
- **Industry.**
  - Darktrace: per-entity "pattern of life" with Bayesian scoring [lit, vendor]; needs a learning period.
  - Splunk risk-based alerting: accumulates risk per entity and alerts when the number of ATT&CK tactics in
    7 days passes a threshold [lit, vendor docs].
  - Microsoft Defender: automatic attack disruption, plus an exposure graph that shows the "blast radius" and
    chokepoints around critical assets such as domain controllers [lit, vendor docs].
  - Microsoft (2020): Bayesian network over TTPs to predict the next attack step [lit].

### 2.2 Analogous problems outside cyber security
| Field | Same structure | What works there [lit] | What we borrow |
|---|---|---|---|
| AIOps root-cause analysis (microservices) | anomaly -> propagation graph -> root cause and impacted services | anomaly scores as personalization vector of personalized PageRank on the service graph (MicroRCA, RUN, MicroGBPM) | blast radius = personalized PageRank seeded by detections |
| Epidemiology on contact networks | find patient zero, predict spread | GNNs outperform other source-detection methods (2025 benchmark); DeepTrace refines the source estimate as tracing data arrives | backward tracing to the entry point; forward spread ranking |
| Fraud / AML on transaction graphs | rare coordinated behaviour in a temporal graph | temporal GNNs with node memory; explanations as subgraph evidence, not single-feature attributions; leakage-safe time-respecting features | explain with evidence subgraphs; strict time ordering |
| Power-grid cascading failures | predict which components fail next | GNNs with attention or causal subgraphs as explanation; PowerGraph benchmark has ground-truth explanations | evaluate explanations against ground truth |
| Time-series anomaly detection | unsupervised detection under weak labels | ICML 2024 position paper: simple baselines (PCA, L2, NN distance) match deep models once evaluation is fixed | simple core, rigorous evaluation |

## 3. The REACH architecture

```
host telemetry (process / file / flow / logon events, all hosts)
        |
 L1  DETECT  : event-level masked reconstruction, one model shared by all hosts
        |       score(e) = -log p(event e | its context); conformal calibration on benign days
        v
 L2  EXPLAIN : (a) evidence  = top-surprise events + time-respecting causal expansion -> compact attack graph
        |      (b) semantics = deterministic ATT&CK tagging of each evidence event (rules on process, command line, port)
        |      (c) narrative = optional LLM summary constrained to (a)+(b)
        v
 L3  BLAST   : (a) retrospective: causal closure from detected nodes, across hosts via flows/logons -> affected set
     RADIUS    (b) prospective : personalized PageRank on the enterprise host graph, seeded by detection mass;
                   edge weights = admin-protocol reachability x credential-exposure tags from L2 x recency
```

**L1 Detect.**
- **Objective:** predict each event's type and target from the entity's context (Velox/Kairos style).
- **Node features:** textual features of process path and command line, from a pretrained encoder available in
  PIDSMaker.
- **Score:** each event's reconstruction loss.
- **Kept from our work:** calibration on benign days into p-values, and within-host controls in evaluation.
- **Why:** the simplest pooled reconstruction model won both in the literature and in our test, and scoring
  single events avoids the dilution we saw with hourly aggregates.

**L2 Explain.** Explanations are the model's own evidence, faithful by construction: the alert is the sum of its
events' surprise. ATT&CK labels come from explicit semantics in the telemetry, which avoids the failure of our
statistical channels. Examples:
- `wmiprvse.exe` spawning `powershell` -> T1047;
- access to `lsass` -> T1003.001;
- TCP 3389 to an internal host -> T1021.001.

**L3 Blast radius.**
- **Retrospective (what is already affected):** follows causality, like Kairos/Orthrus reconstruction, but
  across hosts.
- **Prospective (who is next):** imports the AIOps personalized-PageRank recipe and Microsoft's exposure-graph
  idea, and conditions it on L2's technique tags. Example: a host where `lsass` was accessed exposes credentials,
  so the weights of its admin-protocol edges go up.
- **Optional learned edge prior:** temporal link prediction (Euler/Argus/CyberGFM), kept only if an ablation
  shows a gain.

## 4. Data and evaluation
| Layer | Development data | Test data (untouched until the gate) | Baselines |
|---|---|---|---|
| L1 | DARPA E3: CADETS, THEIA, CLEARSCOPE (PIDSMaker) | OpTC h201, h501, h051 (PIDSMaker, consistent ground truth) | Velox, Orthrus, Kairos, MAGIC, Flash, NodLink (all in PIDSMaker), several seeds |
| L2 | same | same + red-team report timeline (technique list) | Orthrus/Kairos attack graphs; SHAP; AE-error grouping |
| L3 | LANL red team (lateral movement) | OpTC real chains: day 1 0201->0402->0660->DC1->14 hosts; day 2 0501->DC1->... | BFS, degree, random, Euler/Argus-style link prediction |

**Pre-registered gates (to be fixed before running the test data).**
- **G1 detect:** node-level detection on OpTC not worse than the best of Velox and Orthrus beyond seed variance.
- **G2 explain:** nodes to inspect per detected attack <= Orthrus at equal or higher recall; ATT&CK tag
  precision reported against the red-team report.
- **G3 blast radius:** next-host recall@5 above BFS and link prediction on the OpTC chains.

## 5. Requirements and risks
- **Compute.** PIDSMaker expects Docker, Postgres and a CUDA GPU. This cloud environment has Docker but no GPU;
  the E3 datasets may be feasible on CPU, OpTC and the temporal GNN baselines probably not.
  Need: a GPU machine (university cluster, the user's machine, or a GPU cloud environment).
- **Data.**
  - The PIDSMaker dumps are on Google Drive: OpTC h201/h501/h051 = 5.2 GB compressed, 23.4 GB loaded;
    E3 = 3.1 GB compressed. A user copy avoids the shared-file quota.
  - The enterprise-wide host graph for L3 needs OpTC eCAR flow and logon events across all hosts (the LMDEval
    extraction), which is much larger.
- **Risks.**
  - Velox is already near the ceiling on several DARPA datasets: L1 may only reach parity, so the paper's novelty
    must come from L2 + L3 and their evaluation.
  - Seed instability (PIDSMaker): report the distribution over seeds.
  - Real chains for L3 are few (2 days of OpTC): report as a case study with raw counts, plus semi-synthetic
    campaigns.
- **Odds [guess].**
  - G1 parity: 50-60%; G2: about 50%; G3: 40-50%.
  - If all pass: Q2 about 60%, Q1 about 25-30%.
