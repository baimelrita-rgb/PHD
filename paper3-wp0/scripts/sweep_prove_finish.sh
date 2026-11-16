#!/usr/bin/env bash
# Finish sweep_prove.sh after the report-text bug in scripts/18: telemetry, envelope, SE-BDD and ML outputs are complete.
cd "$(dirname "$0")/.."
for name in split_d05 split_d20; do
  ( export P3_VARIANT=$name; LOG=data/${name}_prove.log
    python3 scripts/18_semiurban_consolidation.py --grid semiurban --prove >> $LOG 2>&1
    python3 scripts/20_statistics.py >> $LOG 2>&1
    unset P3_VARIANT; python3 scripts/20_statistics.py --pool-with $name >> $LOG 2>&1 ) &
done
wait
echo "SWEEP PROVE FINISH DONE" >> data/seeds.log
