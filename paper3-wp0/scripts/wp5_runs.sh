#!/usr/bin/env bash
# WP5: per-topology online noise calibration (scripts/14 --topo-cal-s 300) on the recorded 01-Basic day and the split days.
cd "$(dirname "$0")/.."
LOG=data/wp5_runs.log
run() { echo "=== $(date +%H:%M:%S) START $*" >> $LOG; s=$(date +%s); "$@" >> $LOG 2>&1; rc=$?; echo "=== $(date +%H:%M:%S) END rc=$rc $(( $(date +%s)-s ))s $*" >> $LOG; }
run python3 scripts/14_consolidation.py --topo-cal-s 300 --tag _tc
P3_VARIANT=split run python3 scripts/14_consolidation.py --topo-cal-s 300 --tag _tc
P3_VARIANT=split_tappad run python3 scripts/14_consolidation.py --topo-cal-s 300 --tag _tc
echo "=== ALL DONE" >> $LOG
