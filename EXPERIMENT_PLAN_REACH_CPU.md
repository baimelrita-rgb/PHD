# REACH experiment plan for the resources available now (CPU only)

Companion to `ARCHITECTURE_REACH.md`. Written 2026-10-31.

## 0. Resources (measured in the cloud environment)
- 4 CPU cores, 15 GB RAM, no GPU. Docker client installed, but no Docker daemon. apt and pip work.
- 16 GB free disk. About 23 GB after deleting re-downloadable raw files: DEDALE Zeek zips (3.7 GB) and
  Unraveled CSVs (3.5 GB). The features computed from them are kept.
- PIDSMaker pre-processed dumps on Google Drive (one file per dataset).
  - `atlasv2_edr.dump` (183 MB) downloaded directly.
  - If the shared-file quota blocks a file, the user copies that single file to her Drive.
- LANL (csr.lanl.gov): reachable, but the download needs a short form (e-mail and intended use), which the user
  fills in herself.

## 1. Scope adapted to CPU
| Layer | Full REACH | CPU version |
|---|---|---|
| L1 Detect | event-level masked reconstruction with a pretrained text encoder | same objective, light encoder: hashed tokens of process path / command line + 1-layer neighbourhood mean + MLP decoder predicting event type and target type; pooled over all entities; conformal calibration |
| L1 baselines | 8 PIDSs, several seeds | Velox (the simple state of the art) and MAGIC on CPU, 5 seeds; Orthrus/Kairos only on the smallest dataset if a CPU run finishes in < 6 h; otherwise their published numbers, marked "not reproduced" |
| L2 Explain | evidence graph + ATT&CK rules + optional LLM | evidence graph (top-surprise events + time-respecting causal expansion with a node budget) + deterministic ATT&CK rules on process / command line / port; no LLM |
| L3 Blast radius | enterprise host graph from OpTC eCAR | LANL authentication graph (17,684 computers, red-team compromise events with source and destination computer) streamed and aggregated per day; OpTC chains as a case study |

## 2. Data roles (fixed now; test data are not opened before their gate)
| Use | L1 / L2 | L3 |
|---|---|---|
| Development | ATLASv2-EDR (Windows, 10 attacks, 1 GB loaded); CARBANAKv2-EDR (6.6 GB loaded) | LANL red-team events of days 1-29 |
| Test | OpTC h201, h501, h051 (Windows, PIDSMaker ground truth; 6.7-9 GB loaded each, one at a time) | LANL red-team events of days 30-58; OpTC day 1 / day 2 chains (case study) |

## 3. Phases, gates and time
**Phase 0 — feasibility (about 1 day).**
- Steps:
  1. Delete the re-downloadable raw files.
  2. Install PostgreSQL (apt) and the PIDSMaker Python dependencies (CPU wheels).
  3. Restore ATLASv2-EDR and run Velox on CPU.
  4. Check which node attributes exist (process path, command line, ports).
- Gate F0: Velox finishes on ATLASv2 in <= 3 h and reports metrics.
- If F0 fails: export the PIDSMaker tables to parquet and run our own models plus a Velox re-implementation.

**Phase 1 — L1 + L2 development on ATLASv2 and CARBANAKv2 (about 1 week).**
- Build the event-surprise detector, the evidence graph and the ATT&CK rule set.
- Choose hyperparameters on development data only.
- Write every development round into a log; freeze the code before Phase 2.

**Phase 2 — L1 + L2 test on OpTC h201, h501, h051 (about 3-5 days of CPU time).**
- Ours, Velox and MAGIC, each with 5 seeds, under the PIDSMaker evaluation protocol.
- Gate G1 (detect): node-level detection not worse than Velox beyond the seed spread (median over seeds).
- Gate G2 (explain): nodes to inspect per detected attack lower than Velox's flagged set at equal recall;
  ATT&CK tag precision measured against the OpTC red-team report.

**Phase 3 — L3 on LANL (about 1 week).**
- Stream `auth.txt.gz` (about 7 GB compressed, never stored uncompressed) into daily
  (source computer, destination computer, auth type, logon type) counts.
- Blast-radius ranking: personalized PageRank seeded by compromised / detected hosts, with edge weights from
  admin logon types and recency.
- Baselines: BFS, degree, random, and a CPU temporal link predictor (logistic matrix factorization on daily
  graphs).
- Gate G3: next-compromised-host recall@5 and @10 above all baselines on the test days.
- OpTC chains reported as a case study with raw counts.

**Phase 4 — writing (about 1 week).** Every number comes from a results file; negative gates are reported.

## 4. What the user does
1. Approve deleting the re-downloadable raw files (DEDALE Zeek zips, Unraveled CSVs).
2. If Drive blocks a PIDSMaker dump: copy that file (`atlasv2_edr`, `carbanakv2_edr`, `optc_201`, `optc_501`,
   `optc_051`) from https://drive.google.com/drive/folders/1hqfz8__zVqb3QzBuOI2SxrW4lLIdYqFr to her Drive and share it.
3. LANL: fill in the form at https://csr.lanl.gov/data/cyber1/ (her e-mail; usage: "academic research on
   lateral-movement detection") and send the links it reveals for `auth.txt.gz` and `redteam.txt.gz`.

## 5. Risks under CPU limits
- Running PIDSMaker's GNN baselines on CPU may be too slow for OpTC. Then only Velox and MAGIC are reproduced, and
  the paper says so.
- Disk: one OpTC host at a time (compressed + restored = up to 11 GB).
- LANL red-team labels are compromise events, not full attack graphs; L3 measures next-host ranking only.
- Odds [guess]: F0 70%; G1 parity 45-55%; G2 50%; G3 40-50%.
