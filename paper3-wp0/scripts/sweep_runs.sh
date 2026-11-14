#!/usr/bin/env bash
# Reviewer M2: drift-magnitude sensitivity of the split day (0.5x and 2x the measured magnitudes).
cd "$(dirname "$0")/.."
for V in split_d05:0.5 split_d20:2.0; do
  name=${V%%:*}; scale=${V##*:}
  ( export P3_VARIANT=$name; python3 scripts/22_split_day.py --drift-scale $scale > data/${name}_gen.log 2>&1 && ./scripts/split_runs.sh ) &
done
wait
echo SWEEP DONE >> data/sweep.log
