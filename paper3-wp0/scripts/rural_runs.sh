#!/usr/bin/env bash
cd "$(dirname "$0")/.."
LOG=data/rural_runs.log
run() { echo "=== $(date +%H:%M:%S) START $*" >> $LOG; s=$(date +%s); python3 "$@" >> $LOG 2>&1; rc=$?; echo "=== $(date +%H:%M:%S) END rc=$rc $(( $(date +%s)-s ))s $*" >> $LOG; }
run scripts/18_semiurban_consolidation.py --grid rural --noise-from semiurban
run scripts/13_ml_detectors.py --grid rural --features physics
run scripts/13_ml_detectors.py --grid rural --features raw
run scripts/19_comparison.py
echo "=== ALL DONE $(date +%H:%M:%S)" >> $LOG
