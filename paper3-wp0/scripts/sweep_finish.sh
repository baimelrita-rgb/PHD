#!/usr/bin/env bash
# Finish the drift-magnitude sweep: consolidation loops for both variants (after the restart).
cd "$(dirname "$0")/.."
for V in split_d05 split_d20; do
  ( export P3_VARIANT=$V; LOG=data/${V}_runs.log
    for cmd in "scripts/14_consolidation.py" "scripts/14_consolidation.py --topo-cal-s 300 --tag _tc" "scripts/18_semiurban_consolidation.py --grid semiurban"; do
      echo "=== $(date +%H:%M:%S) START $cmd" >> $LOG; s=$(date +%s); python3 $cmd >> $LOG 2>&1; echo "=== $(date +%H:%M:%S) END rc=$? $(( $(date +%s)-s ))s $cmd" >> $LOG
    done ) &
done
wait
echo SWEEP FINISHED >> data/sweep.log
