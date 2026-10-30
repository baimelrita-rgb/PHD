# Work Plan: Detect -> Explain -> Predict (real data for Detect/Explain, semi-synthetic propagation for Predict)

Agreed with the user on 2026-10-30. Replaces the earlier versions of this file (see git history).
Status tags: **[measured]** = from a file in our repos; **[search]** = from a web-search snippet, to be verified;
**[guess]** = estimate, to be replaced by a measurement. Every number in the paper must come from a file.

---

## 0. The paper in one paragraph

Analysts need to know whether an attack is happening, what the attacker is doing, and where it will go next.
We propose a **Detect -> Explain -> Predict** pipeline. **Detect** has two channels: a technique channel
(MITRE ATT&CK technique probabilities inferred from network flows) and a residual "unexplained behaviour" channel
(anomaly detection), so that attacks that match no known technique are not lost. **Explain** reports each alert either
as the techniques that triggered it or as "unexplained, possibly novel". **Predict** combines the same evidence with the
observed reachability between hosts to rank the hosts most likely to be compromised next.
Detect and Explain are evaluated on a real public dataset; Predict is evaluated on semi-synthetic campaigns injected into
that dataset's real hosts and benign traffic, with an attacker model calibrated on the documented DARPA OpTC campaigns,
and checked on OpTC's real lateral-movement chains.

Working title: *Detect, Explain, Predict: ATT&CK-Grounded Network Detection with Novelty Awareness and Threat-Propagation Prediction*

### Research questions and claims (a claim enters the abstract only if its gate passes)
- **RQ1 Detect.** Does the two-channel detector match a black-box detector on the same features ("price of explanation"),
  beat shortcut baselines (port, IP, time), and still detect a technique that was held out of training?
- **RQ2 Explain.** Are the technique explanations correct (vs. ground truth), faithful (interventions on a technique change
  the decision as expected), and honest about novelty (a held-out technique is explained as "unexplained", not as a wrong technique)?
  How much of each decision flows through the residual channel?
- **RQ3 Predict.** Does technique-aware propagation, fed by the RQ1 detector's real outputs, rank next-compromised hosts better
  than BFS, persistence and degree at equal isolation budget, under several attacker models, and on OpTC's real chains?

## 1. Where things live
- Plans and paper text: `baimelrita-rgb/PHD`, branch `claude/fervent-pasteur-ot9uly` (this file).
- Code and data audits: `baimelrita-rgb/STT-GNN-` (private). New branch `claude/dep-paper`, new directory `dep/`.
  The UNSW work and `analysis_uwf/` are not modified; their scripts are reused by import or copy.
- Raw data is never committed; each download writes a manifest with SHA-256.

## 2. Network access needed (environment -> Network access -> Limited -> Allowed domains; keep "Allow package managers")
Already reachable: GitHub (incl. raw.githubusercontent.com: MITRE ATT&CK STIX data `mitre/cti`), PyPI, datasets.uwf.edu.

| Domain | For | Needed in |
|---|---|---|
| doi.org | DEDALE DOI and paper DOIs | Phase 1 |
| entrepot.recherche.data.gouv.fr | DEDALE files (DOI 10.57745/Y5JLDG) [search] | Phase 1 |
| dedale.inria.fr | DEDALE documentation | Phase 1 |
| fkie-cad.github.io | COMIDDS dataset catalog (Unraveled, DEDALE descriptions) | Phase 1 |
| zenodo.org | AIT-LDS v2, CAM-LDS; possibly Unraveled | Phase 1 |
| speed.cs.nycu.edu.tw | CREMEv3 paper and data pointers | Phase 1 |
| drive.google.com, drive.usercontent.google.com | DARPA OpTC (`ecar-bro`, 2 GB) | Phase 3 |
| arxiv.org, export.arxiv.org | reading related work | all |
| www.mdpi.com | UWF-ZeekData24 paper (paper_vs_observed) | optional |
| api.crossref.org, api.semanticscholar.org | automatic reference/DOI check of the manuscript | Phase 6 |
| csr.lanl.gov | LANL (topology sensitivity only) | optional |
If a download redirects to a host not listed here, the run stops and reports the host name.

## 3. Phases, deliverables, gates

### Phase 0. Setup (user, 10 minutes)
Add the domains above. Confirm the target journal (affects length and figure style).

### Phase 1. Dataset audits and choice of D (week 1)
Audit DEDALE and Unraveled first, CREMEv3 if obtainable, with the UWF Phase-0 protocol (`analysis_uwf/TASK.md`, items 1-7):
files and SHA-256, schema, labels, label x port / service / IP / time mutual information, lookup baselines, benign/attack day overlap,
hosts per technique, duplicates, paper-vs-observed.
Deliverables: `dep/audit/<dataset>/RECON.md` and CSVs; `dep/audit/CHOICE.md` (one table, all datasets incl. UWF [measured]).

**Gate G0 (pre-registered).** D must satisfy, on a split by host or by campaign:
(R1) technique labels per flow or per window; (R2) a dst-port lookup does not reach the technique macro-F1 of the GBDT within 0.05;
(R3) benign and attack flows share days; (R4) at least 4 techniques with at least 50 flows and 3 windows in every split;
(R5) at least 20 hosts with benign traffic (room for injection).
- Pass: D is chosen; continue.
- Fail for all: Detect/Explain is reported as a negative measurement on all audited datasets (the audits are the evidence),
  and the paper becomes the measurement paper (Option A) with Predict as a simulation section. Decision with the user.

### Phase 2. Detect -> Explain on D (weeks 2-3)
- Features: per-flow Zeek fields and per-window host aggregates; IPs and time never used as features (kept only for splits and shortcut tests).
- Technique channel: multi-label technique probabilities (GBDT first; a neural model only if it adds something).
- Residual channel: anomaly score trained on benign traffic of the training hosts only.
- Decision: a small, inspectable function of [technique probabilities, residual score] (logistic or shallow tree).
- Baselines: S1-S8 of the UWF task (majority, IP, port, service, time lookups; GBDT with/without IP/port/time); a black-box GBDT
  on the same features (for the price of explanation).
- Leave-one-technique-out (LOTO): for each technique, retrain without it; measure its detection recall at fixed FPR, the share of
  its detections that come from the residual channel, and how often it is explained as another technique.
- Explanation tests: technique accuracy vs ground truth; intervention test (set a technique probability to 0/1, measure decision change);
  residual share of all decisions.
- Seeds 42-46; bootstrap CIs over hosts.
**Gate G1 (pre-registered).** Technique channel beats the dst-port lookup outside the CI (macro-F1); the two-channel detector is
within 0.05 AP of the black box; LOTO recall above the residual-only baseline for at least half of the techniques.
Each failed condition is reported and its claim is removed from the abstract; the phase is not repeated with new tuning on test.

### Phase 3. Propagation generator (weeks 3-5)
- Calibration targets from OpTC [measured from optc_redteam.csv and the red-team PDF; timings need the OpTC flows]:
  chain depth 3-4; domain-controller fan-out to 14 hosts (day 1) and 6 hosts (day 2); failed attempts; methods WMI, RDP, SMB;
  inter-step delays (to be measured from the extracted OpTC flows with `PHD/optc/extract_labeled.py`).
- Attacker models (the generator is NOT known to the predictors): (M1) OpTC-like with hub fan-out; (M2) chain-only, no hub;
  (M3) stealthy, low-and-slow on benign-looking services; (M4) misspecified: random walk ignoring preconditions.
- Injection: for each campaign step, sample real attack flows of the matching technique from D, re-address them to the simulated
  source/target hosts of D and re-time them into D's benign traffic.
- **Gate G2.** (a) Artifact test: a classifier separating injected attack flows from original attack flows of D has AUC <= 0.60
  (otherwise fix the injection). (b) Calibration: M1 reproduces the OpTC targets within the bounds stated before running.

### Phase 4. Predict (weeks 5-6)
- Input: the outputs of the Phase 2 detector on the injected data (never the labels).
- Predictors: random, degree, persistence, BFS-k from detected hosts; technique-aware Bayesian propagation (preconditions + evidence,
  no training); optional GNN trained on M1/M2 and tested on M3/M4.
- Metrics: AP/AUC on next-window compromise; coverage at budget (hosts isolated per window); hosts isolated per prevented compromise;
  time to contain. 1,000+ campaigns per cell; seeds fixed.
- Sweeps: attacker model; detection quality (Phase 2 detector vs. degraded vs. oracle); budget; topology size (subsets of D).

### Phase 5. Real-chain check on OpTC (week 6-7)
Extract OpTC days 1-2 (LMDEval preprocessing + our wrapper); map the documented hops to techniques from the red-team report
(table published in the appendix); run the predictors with oracle evidence and with evidence degraded by the Phase 2 confusion matrix.
Reported as a case study with raw counts (about 30 first-compromise events [measured, approx.]).

### Phase 6. Writing and checks (weeks 8-10)
All tables/figures generated by scripts from files; references verified through Crossref/Semantic Scholar; the real vs semi-synthetic
status stated in the abstract, in every table caption and in the limitations; code and generator released.

## 4. Roles
- Claude: code, runs, audit reports, tables, drafts; stops at each gate with a factual report.
- User: decisions at gates G0-G2, domain expertise (attacker models, SOC framing), co-author coordination, final writing.

## 5. Risks and mitigations
| Risk | Mitigation |
|---|---|
| No dataset passes G0 | Pre-defined fallback (Option A + simulation section); audits are already a contribution |
| Residual channel absorbs everything (explanations meaningless) | Measure residual share; report; constrain or regularise the residual |
| Injection artifacts | Gate G2a; ID2T-style checks |
| Circularity between generator and predictor | Misspecified attacker models (M3, M4); predictors do not see the generator |
| Reviewers: "synthetic propagation" | Calibration table (G2b), OpTC real-chain check, open generator, explicit labelling of what is synthetic |
| References | Automatic DOI check before submission |

## 6. Predictions [guess], replaced by measurements at each gate
| Event | Probability |
|---|---|
| DEDALE or Unraveled passes G0 | ~45% |
| G1 passes in full | ~35% |
| G2 passes after at most one revision of the injection | ~70% |
| Technique-aware propagation beats BFS at equal budget under M1 | ~60% |
| ... and under M3/M4 | ~35% |
| Acceptance Q2 / Q1 if Phases 1-5 complete | ~45-55% / ~15-25% |

## 7. Immediate next steps
1. User: add the Phase 1 domains (first block of the table in Sec. 2) and say "done".
2. Claude: download and audit DEDALE (`dep/audit/dedale/`), then Unraveled; write `CHOICE.md`; stop at G0 with a factual report.
