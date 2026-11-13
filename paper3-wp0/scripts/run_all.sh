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
# WP1-b2: linearised AC model (also meshed), rule-specific bounds, exact layer and CEGIS with it
python scripts/04_lindistflow_error.py --seed "$SEED" --model linac
python scripts/04b_atom_bounds.py --seed "$SEED" --model linac
python scripts/05_oracle_exact.py --seed "$SEED" --model linac
python scripts/06_cegis_demo.py --seed "$SEED" --model linac
if [ -d data/raw/01-Basic/01-Basic ]; then
  python scripts/01_inventory.py --seed "$SEED"
  python scripts/07_sherlock_model_check.py --seed "$SEED"
  python scripts/08_identify_taps.py --seed "$SEED"
  python scripts/09_physics_residual.py --seed "$SEED" --step 1
else
  echo "Sherlock data missing: run scripts/00_download_sherlock.sh first (T1, T7 skipped)"
fi
pip freeze > reports/env.txt
# WP1-b: oracle on the reconstructed Sherlock grid (needs Sherlock data and rules/sherlock_grid_params.json)
if [ -d data/raw/01-Basic/01-Basic ]; then
  python scripts/10a_sherlock_envelope.py --seed "$SEED"
  python scripts/10b_sherlock_rules.py --seed "$SEED"
  python scripts/03_oracle_search.py --seed "$SEED" --grid sherlock --budget 32000
  python scripts/04_lindistflow_error.py --seed "$SEED" --grid sherlock --adv-budget 500
  python scripts/05_oracle_exact.py --seed "$SEED" --grid sherlock
  python scripts/06_cegis_demo.py --seed "$SEED" --grid sherlock
  python scripts/04_lindistflow_error.py --seed "$SEED" --grid sherlock --model linac --adv-budget 500
  python scripts/04b_atom_bounds.py --seed "$SEED" --grid sherlock --model linac
  python scripts/05_oracle_exact.py --seed "$SEED" --grid sherlock --model linac
  python scripts/06_cegis_demo.py --seed "$SEED" --grid sherlock --model linac
  # WP1-c: attack anatomy and rule synthesis from alerts
  python scripts/11_attack_anatomy.py --seed "$SEED"
  python scripts/12_synthesize.py --seed "$SEED"
  # WP1-d: ML detectors (physics-informed and raw features) and the consolidation loop
  python scripts/13_ml_detectors.py --seed "$SEED" --features physics
  python scripts/13_ml_detectors.py --seed "$SEED" --features raw
  python scripts/14_consolidation.py --seed "$SEED"
fi
pip freeze > reports/env.txt
# WP2: 02-Semiurban (needs data/raw/02-Semiurban, scripts/00b_download_semiurban.sh)
if [ -d data/raw/02-Semiurban/02-Semiurban ]; then
  python scripts/15a_semiurban_identify.py --seed "$SEED"
  python scripts/15b_semiurban_model_check.py --seed "$SEED" --split train
  python scripts/15b_semiurban_model_check.py --seed "$SEED" --split test
  python scripts/16a_semiurban_envelope.py --seed "$SEED"
  python scripts/17_se_bdd.py --seed "$SEED"
  python scripts/18_semiurban_consolidation.py --seed "$SEED"
fi
pip freeze > reports/env.txt
