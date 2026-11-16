#!/usr/bin/env bash
# Rerun the drift-strength sweep for 02-Semiurban with proved certification (telemetry regenerated deterministically).
cd "$(dirname "$0")/.."
for V in split_d05:0.5 split_d20:2.0; do
  name=${V%%:*}; scale=${V##*:}
  ( export P3_VARIANT=$name; LOG=data/${name}_prove.log
    python3 scripts/22_split_day.py --grids semiurban --drift-scale $scale > $LOG 2>&1
    for cmd in "scripts/16a_semiurban_envelope.py --grid semiurban" "scripts/17_se_bdd.py --grid semiurban" "scripts/13_ml_detectors.py --grid semiurban --features physics" "scripts/18_semiurban_consolidation.py --grid semiurban --prove" "scripts/20_statistics.py"; do
      python3 $cmd >> $LOG 2>&1
    done
    unset P3_VARIANT; python3 scripts/20_statistics.py --pool-with $name >> $LOG 2>&1 ) &
done
wait
echo "SWEEP PROVE DONE" >> data/seeds.log
