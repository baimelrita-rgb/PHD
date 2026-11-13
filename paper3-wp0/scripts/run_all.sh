#!/usr/bin/env bash
# Reproduce every WP0 report. Seeds: default 7 (each script takes --seed).
set -euo pipefail
cd "$(dirname "$0")/.."
SEED="${SEED:-7}"
mkdir -p data/interim reports
python -m pytest -q
python scripts/02_envelope_smoke.py --seed "$SEED"
python scripts/02b_build_rules.py --seed "$SEED"
python scripts/03_oracle_search.py --seed "$SEED"
python scripts/03_oracle_search.py --seed "$SEED" --budget 32000 --report oracle_search_budget32000.md
python scripts/03b_r3_diagnostic.py --seed "$SEED"
python scripts/04_lindistflow_error.py --seed "$SEED"
python scripts/05_oracle_exact.py --seed "$SEED"
python scripts/06_cegis_demo.py --seed "$SEED"
if [ -d data/raw/01-Basic/01-Basic ]; then
  python scripts/01_inventory.py --seed "$SEED"
  python scripts/07_sherlock_model_check.py --seed "$SEED"
  python scripts/08_identify_taps.py --seed "$SEED"
  python scripts/09_physics_residual.py --seed "$SEED" --step 1
else
  echo "Sherlock data missing: run scripts/00_download_sherlock.sh first (T1, T7 skipped)"
fi
pip freeze > reports/env.txt
