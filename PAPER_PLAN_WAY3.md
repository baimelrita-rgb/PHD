# Paper Plan, Way 3: technique detection on real data + blast radius by Monte-Carlo simulation on real topologies

Chosen by the user on 2026-10-30. Supersedes the model plans for UNSW-NB15 and UWF-ZeekData24 as the main paper.
Measurement work already done is reused: UNSW leak test and shortcut baselines (`STT-GNN-`, main),
UWF-ZeekData24 Phase 0 (`STT-GNN-`, branch `claude/uwf-zeekdata24-feasibility`, `analysis_uwf/`), OpTC label audit and
extraction wrapper (`PHD`, `optc/`).

Status tags: **[measured]** = from a file in one of the repos; **[search]** = from a web-search snippet, to verify;
**[guess]** = my estimate, to be replaced by a measurement.

---

## 1. The question the paper answers

> How good must technique-level detection be before technique evidence improves blast-radius prediction
> (and containment decisions) over topology-only heuristics, and do real detectors reach that level?

- **RQ1 (real data).** Can a technique-level detector be learned from public data without shortcuts (port, IP, time)?
  Output: per-technique confusion matrices with confidence intervals, plus the shortcut baselines that bound them.
- **RQ2 (simulation).** Given a detector with a given confusion matrix, how much does technique evidence improve
  next-step compromise prediction and containment cost, compared with BFS, persistence and degree, on real network topologies?
  Output: a "phase diagram" of benefit versus detector quality, topology and attacker behaviour.
- **RQ3 (real chains).** Do the RQ2 conclusions hold on the documented real chains (OpTC days 1-2; DEDALE campaign if usable)?

Why this is worth a paper: no public dataset combines (a) technique labels not determined by port/IP/time,
(b) benign traffic interleaved with attacks, (c) first-compromise times [measured for UNSW, UWF, OpTC; search for others].
Way 3 does not wait for such a dataset: it measures what real data can give (RQ1) and simulates only what no dataset gives (propagation).
No prior work using ATT&CK techniques as a bottleneck layer for detection was found in our search [search]; this must be re-checked before writing.

## 2. Work packages and gates

### WP0. Data audits (week 1) - reuse the UWF Phase 0 protocol (`analysis_uwf/TASK.md`)
Datasets, in order: DEDALE (55 machines, 28 days, flows reportedly labeled with ATT&CK tactic/technique [search]),
Unraveled (27+ machines, 6 weeks, three attacker groups, ATT&CK labels, label inconsistencies reported [search]),
CREMEv3 (technique and lifecycle labels, Linux, traffic logs [search]). UWF-ZeekData24 is already audited [measured].

For each: files and SHA-256; label columns; technique x port / service / IP / time mutual information and lookup baselines;
benign vs attack time overlap; number of hosts per technique.

**Gate G0** (decided in advance): a dataset is usable for RQ1 only if, on a split by host or by campaign,
(i) benign and attack share days, and (ii) a dst-port lookup does NOT reach technique macro-F1 within 0.05 of the best model.
- If at least one dataset passes: RQ1 uses it.
- If none passes: RQ1 is reported as a negative measurement (with the evidence), and RQ2 uses a family of synthetic
  confusion matrices (from perfect to random) instead of measured ones. The paper survives; its claim narrows.

### WP1. Technique detector on real data (weeks 2-3)
- Splits: by host, by campaign, and cross-dataset where label sets overlap. Never by random flow, never by calendar time across a class boundary.
- Baselines: S1-S8 of `analysis_uwf/TASK.md` (majority, IP, port, service, time, GBDT with/without IP/port/time).
- Detector: the simplest model that beats the baselines (GBDT on window features first; a GNN only if it is needed).
- Output: confusion matrix per technique with bootstrap CI over hosts; calibration curve.
- **Gate G1**: the detector beats the dst-port lookup outside the CI on macro-F1. If not, its confusion matrix is still used in WP2
  (it is a real measurement), and the paper reports that public data does not support the technique layer.

### WP2. Simulator and blast-radius predictors (weeks 3-5)
- **Topologies** (real): OpTC host graph from FLOW START events (extraction ready: `PHD/optc/extract_labeled.py`);
  DEDALE 55 machines from its flows; LANL authentication graph (optional, needs `auth.txt.gz`).
  Synthetic families (enterprise template, scale-free) only for sensitivity checks.
- **Attacker model**: a technique state machine with preconditions (service reachable, credential held, privilege),
  e.g. T1595 -> T1190/T1110 -> T1078 -> lateral movement (WMI/RDP/SMB) -> T1048.
  Calibrated against the OpTC ground truth [measured from optc_redteam.csv and the red-team PDF]: chain depth 3-4,
  a domain-controller fan-out to 14 and 6 hosts, failed attempts present, inter-step delays from the red-team log.
- **Defender evidence**: each attack flow emits a technique observation drawn from the WP1 confusion matrix
  (plus false positives on benign flows at the measured rate, plus detection delay).
- **Predictors** of "compromised in the next window":
  (a) persistence, BFS-k from detected hosts, degree, random;
  (b) technique-aware Bayesian propagation (preconditions + evidence; no training);
  (c) optional: a GNN trained on simulated campaigns, tested on held-out topologies.
- **Metrics**: AP and AUC on next-window compromise; coverage at budget (hosts isolated per window); hosts isolated per prevented
  compromise; time to contain.
- **Sweeps**: detector quality (interpolate the measured confusion matrix towards identity and towards random), topology,
  hub fan-out, attacker stealth, detection delay. 1,000+ campaigns per cell, fixed seeds.
- **Gate G2**: the simulated campaign statistics (fan-out, chain depth, delays) reproduce the OpTC values within stated bounds.
  If not, the attacker model is revised before any result is read.

### WP3. Real-chain check (week 6)
OpTC days 1-2 (requires the OpTC extraction, ~2 GB `ecar-bro` or the full `ecar/` folder): replay the documented chains through the
predictors with oracle evidence and with evidence degraded by the WP1 confusion matrix. DEDALE campaign if WP0 shows it is usable.
Reported as a case study with counts, not as significance claims (about 30 first-compromise events in OpTC [measured, approx.]).

### WP4. Writing (weeks 7-8)
Every number from a file; all tables generated by script; reference check against DOIs.

## 3. Validity guards (apply to every result)
- Leak tripwires from the UNSW work: constant / permuted / zeroed channels; label-only lookup baselines.
- Shortcut baselines from the UWF task on every real-data result.
- Simulation: seeds fixed and reported; simulator code released; the realism check of G2 reported in the paper.
- No claim in the abstract that is not supported by a gate that passed.

## 4. Predictions before running anything  [guess]
| Event | Probability |
|---|---|
| At least one of DEDALE / Unraveled / CREMEv3 passes G0 | ~50% |
| A real detector beats the port lookup outside the CI (G1) | ~40% |
| Technique-aware propagation beats BFS at equal budget for good-enough detectors (exists a positive region in the phase diagram) | ~75% |
| The measured real detector lies inside that positive region | ~35% |
| Acceptance Q2 / Q1 with WP0-WP3 done | ~45% / ~20% |

The paper is publishable in both outcomes of the fourth line: either "real detectors are good enough here" or
"they need to reach X, today they reach Y". This is the main reason for choosing Way 3.

## 5. Outline
1. Introduction: detection, explanation and containment are coupled; how much explanation is enough?
2. Related work: technique-level detection (RADAR, UWF, CREME), lateral-movement detection and its evaluation
   (Euler, Argus, Jbeil, Larroche 2026), attack simulation (CybORG/CAGE, ID2T), datasets (Sec. 1 table).
3. Data audits and the technique detector (RQ1).
4. Simulator, attacker model, calibration (G2).
5. Phase diagram and containment results (RQ2).
6. Real-chain case study (RQ3).
7. Limitations (simulation, single real topology families, small real chains).

## 6. Immediate next steps
1. User: allow these hosts in the environment's network settings (Limited -> Allowed domains), then I download and audit:
   `doi.org`, `entrepot.recherche.data.gouv.fr`, `dedale.inria.fr` (DEDALE); `zenodo.org` (AIT-LDS, CAM-LDS);
   `drive.google.com`, `drive.usercontent.google.com` (OpTC, for WP2 topology and WP3); `csr.lanl.gov` (optional LANL).
   GitHub is already reachable (Unraveled, if hosted there).
2. Me: WP0 audit of DEDALE with the UWF protocol, then Unraveled.
