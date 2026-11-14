#!/usr/bin/env bash
# WP4d: rerun every calibration and evaluation on the semi-synthetic split day (scripts/22_split_day.py first).
cd "$(dirname "$0")/.."
export P3_VARIANT=split
LOG=data/split_runs.log
run() { echo "=== $(date +%H:%M:%S) START $*" >> $LOG; s=$(date +%s); python3 "$@" >> $LOG 2>&1; rc=$?; echo "=== $(date +%H:%M:%S) END rc=$rc $(( $(date +%s)-s ))s $*" >> $LOG; }
if [ "${1:-all}" != "semiurban" ]; then
  run scripts/10a_sherlock_envelope.py
  run scripts/09_physics_residual.py --step 1
  run scripts/13_ml_detectors.py --grid sherlock --features physics
  run scripts/14_consolidation.py
fi
if [ "${1:-all}" != "sherlock" ]; then
  run scripts/16a_semiurban_envelope.py --grid semiurban
  run scripts/17_se_bdd.py --grid semiurban
  run scripts/13_ml_detectors.py --grid semiurban --features physics
  run scripts/18_semiurban_consolidation.py --grid semiurban
fi
echo "=== ALL DONE $(date +%H:%M:%S)" >> $LOG
