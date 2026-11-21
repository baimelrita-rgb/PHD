#!/usr/bin/env bash
# Test phase of the A/B/C experiment (frozen calibrations in reports/abc/frozen_*.json).
cd "$(dirname "$0")/.."
LOG=data/abc_runs.log
for V in "" split split_s8 split_s9 split_s10 split_s11; do
  echo "== variant ${V:-recorded}" >> $LOG
  python3 scripts/36_semiurban_abc.py --phase test --variant "$V" --workers 2 >> $LOG 2>&1 || echo "FAILED ${V:-recorded}" >> $LOG
done
echo "ABC DONE" >> $LOG
