#!/usr/bin/env bash
# Autonomous experiment chain (decision_log.md, steps A to D). Sequential; a failing step is logged and skipped.
cd "$(dirname "$0")/.."
LOG=data/night_runs.log
run() { echo "=== $(date +%H:%M:%S) START $*" >> $LOG; s=$(date +%s); python3 "$@" >> $LOG 2>&1; rc=$?; echo "=== $(date +%H:%M:%S) END rc=$rc $(( $(date +%s)-s ))s $*" >> $LOG; }
# A: ML detectors on Semiurban
run scripts/13_ml_detectors.py --grid semiurban --features physics
run scripts/13_ml_detectors.py --grid semiurban --features raw
# main loops again, saving per-record firings
run scripts/14_consolidation.py
run scripts/18_semiurban_consolidation.py
# C: seeds
for S in 8 9; do
  run scripts/13_ml_detectors.py --grid sherlock --features physics --seed $S --tag _s$S
  run scripts/14_consolidation.py --seed $S --tag _s$S --alarms detector_alarms_physics_s$S.npz
  run scripts/18_semiurban_consolidation.py --seed $S --tag _s$S
done
# D: margin factor ablation
for MF in 1.25 2.0; do
  T=_m$(echo $MF | tr -d .)
  run scripts/14_consolidation.py --margin-factor $MF --tag $T
  run scripts/18_semiurban_consolidation.py --margin-factor $MF --tag $T
done
echo "=== ALL DONE $(date +%H:%M:%S)" >> $LOG
