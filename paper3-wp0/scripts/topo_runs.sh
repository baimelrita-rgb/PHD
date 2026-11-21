#!/usr/bin/env bash
# Test phase of scripts/41 (frozen P2 calibration), then the remainder correction of scripts/42 and its effect.
cd "$(dirname "$0")/.."
LOG=data/topo_runs.log
for D in recorded split split_s8 split_s9 split_s10 split_s11; do
  echo "== test $D" >> $LOG; python3 scripts/41_topo_abc.py --phase test --day $D >> $LOG 2>&1 || echo "FAILED $D" >> $LOG
done
echo "TEST DONE" >> $LOG
