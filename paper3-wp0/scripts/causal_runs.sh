#!/usr/bin/env bash
# Full 01-Basic consolidation loop rerun with chronological rule activation (--causal).
cd "$(dirname "$0")/.."
LOG=data/causal_runs.log
run() { echo "== $*" >> $LOG; "$@" >> $LOG 2>&1 || echo "FAILED $*" >> $LOG; }
( unset P3_VARIANT
  run python3 scripts/14_consolidation.py --causal --tag _causal
  run python3 scripts/14_consolidation.py --causal --topo-cal-s 300 --tag _tc_causal ) &
( for V in split split_s8 split_s9 split_s10 split_s11; do
    export P3_VARIANT=$V
    run python3 scripts/14_consolidation.py --causal --tag _causal
    run python3 scripts/14_consolidation.py --causal --topo-cal-s 300 --tag _tc_causal
  done ) &
wait
echo "CAUSAL DONE" >> $LOG
