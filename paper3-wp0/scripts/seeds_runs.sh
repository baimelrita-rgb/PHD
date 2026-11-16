#!/usr/bin/env bash
# Improvement B2: four more injection seeds for the additional day (v2 attack model), full pipeline each.
cd "$(dirname "$0")/.."
one() {
  V=$1; SEED=$2
  export P3_VARIANT=$V
  python3 scripts/22_split_day.py --seed $SEED > data/${V}_gen.log 2>&1 || return
  ./scripts/split_runs.sh
  python3 scripts/14_consolidation.py --topo-cal-s 300 --tag _tc >> data/${V}_runs.log 2>&1
  python3 scripts/20_statistics.py >> data/${V}_runs.log 2>&1
  unset P3_VARIANT
  python3 scripts/20_statistics.py --pool-with $V >> data/${V}_runs.log 2>&1
  echo "SEED $V DONE" >> data/seeds.log
}
( one split_s8 8; one split_s10 10 ) &
( one split_s9 9; one split_s11 11 ) &
wait
echo "SEEDS ALL DONE" >> data/seeds.log
