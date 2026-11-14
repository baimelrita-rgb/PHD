#!/usr/bin/env bash
# Reviewer M5: rerun the on-demand libraries so that every record carries the certification time of its topology rule (strict accounting).
cd "$(dirname "$0")/.."
LOG=data/strict_runs.log
run() { echo "=== $(date +%H:%M:%S) START $*" >> $LOG; s=$(date +%s); "$@" >> $LOG 2>&1; rc=$?; echo "=== $(date +%H:%M:%S) END rc=$rc $(( $(date +%s)-s ))s $*" >> $LOG; }
run python3 scripts/18_semiurban_consolidation.py --grid semiurban
run env P3_VARIANT=split python3 scripts/18_semiurban_consolidation.py --grid semiurban
run python3 scripts/18_semiurban_consolidation.py --grid rural --noise-from semiurban --noise-mode global
echo "=== ALL DONE" >> $LOG
