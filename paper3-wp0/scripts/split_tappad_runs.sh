#!/usr/bin/env bash
# WP4d sensitivity: 01-Basic split day with the tap range padded by one step (bounds re-validated for it).
cd "$(dirname "$0")/.."
export P3_VARIANT=split_tappad
LOG=data/split_tappad_runs.log
run() { echo "=== $(date +%H:%M:%S) START $*" >> $LOG; s=$(date +%s); python3 "$@" >> $LOG 2>&1; rc=$?; echo "=== $(date +%H:%M:%S) END rc=$rc $(( $(date +%s)-s ))s $*" >> $LOG; }
run scripts/10a_sherlock_envelope.py --tap-pad 1
run scripts/04_lindistflow_error.py --grid sherlock --model linac --adv-budget 500
run scripts/04b_atom_bounds.py --grid sherlock --model linac
# detectors do not depend on the envelope: reuse the split-day alarms
cp data/interim/detector_alarms_physics_sherlock_split.npz data/interim/detector_alarms_physics_sherlock_split_tappad.npz
run scripts/14_consolidation.py
echo "=== ALL DONE $(date +%H:%M:%S)" >> $LOG
