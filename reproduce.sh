#!/usr/bin/env bash
# ==============================================================================
# TriNetra-Link one-command reproduction (Protocol v2.6.0)
#
#   bash reproduce.sh                             checks + tests; study pipeline only if captured data exists
#   PILOT_FILE=<pilot.json> bash reproduce.sh     also re-runs the Gate G-3 pilot check on the captured pilot
#   PLACEHOLDER=1 bash reproduce.sh               full study pipeline on 120 SIMULATED placeholder journeys
#   VISUAL_METHOD=local bash reproduce.sh         use the registered local visual score (needs an amendment)
#
# The study pipeline runs only on captured observations. Without them this script runs the
# watermarked synthetic dry run instead and says so: it never reports a gate or result it did not earn.
# ==============================================================================

set -euo pipefail

DB="${TRINETRA_DB_PATH:-data/trinetra_store.sqlite}"
MANIFEST="data/derived/split_manifest.json"
STAGING_LOG="data/restricted/staging_log_120.csv"
SCALES="data/derived/scales.json"
VISUAL_METHOD="${VISUAL_METHOD:-global}"   # 'global' is preregistered; 'local' needs a protocol amendment
EXTRA=()

# PLACEHOLDER=1 runs the complete study pipeline on 120 SIMULATED placeholder journeys in
# data/placeholder/ (created if missing). Every output is watermarked NOT A RESULT.
if [[ "${PLACEHOLDER:-0}" == "1" ]]; then
  P=data/placeholder
  [[ -f "${P}/trinetra_store.sqlite" ]] || python -m trinetra_link.cli placeholder create
  DB="${P}/trinetra_store.sqlite"; MANIFEST="${P}/split_manifest.json"
  STAGING_LOG="${P}/staging_log_120.csv"; SCALES="${P}/scales.json"
  EXTRA=(--allow-synthetic-dry-run)
  echo "PLACEHOLDER MODE: simulated journeys, outputs are NOT results."
fi

echo "[1/4] Python environment"
python -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11+ required'"
python --version

echo "[2/4] Repository guards and data linter"
python testing/run_remediation_guards.py
python scripts/data_lint.py

echo "[3/4] Test suite"
python -m pytest tests/ -q

if [[ -n "${PILOT_FILE:-}" ]]; then
  echo "[Gate G-3] Pilot check on ${PILOT_FILE}"
  python -m trinetra_link.cli pilot check --fixtures "${PILOT_FILE}"
fi

if [[ -f "${DB}" && -f "${MANIFEST}" && -f "${STAGING_LOG}" && -f "${SCALES}" ]]; then
  echo "[4/4] Study pipeline on captured journeys"
  RUN_DIR="results/reproduce_$([[ "${PLACEHOLDER:-0}" == "1" ]] && echo PLACEHOLDER_)$(date +%Y%m%d_%H%M%S)"
  mkdir -p "${RUN_DIR}"
  python -m trinetra_link.cli fit --split calibration --db "${DB}" --manifest "${MANIFEST}" \
    --staging-log "${STAGING_LOG}" --scales "${SCALES}" --visual-method "${VISUAL_METHOD}" "${EXTRA[@]}" | tee "${RUN_DIR}/fit.log"
  THETA=$(grep -Eo 'theta \(quality\) *= *[0-9.]+' "${RUN_DIR}/fit.log" | grep -Eo '[0-9.]+$')
  VT=$(grep -Eo 'visual_threshold *= *[0-9.]+' "${RUN_DIR}/fit.log" | grep -Eo '[0-9.]+$')
  COMMON=(--split test --manifest "${MANIFEST}" --staging-log "${STAGING_LOG}" --scales "${SCALES}" --db "${DB}" --theta "${THETA}" --visual-threshold "${VT}" --visual-method "${VISUAL_METHOD}" "${EXTRA[@]}")
  for MASK in full field; do
    python -m trinetra_link.cli eval e1 "${COMMON[@]}" --mask "${MASK}" --output "${RUN_DIR}/e1_${MASK}"
  done
  python -m trinetra_link.cli eval e2 "${COMMON[@]}" --output "${RUN_DIR}/e2"
  python -m trinetra_link.cli eval ablations "${COMMON[@]}" --output "${RUN_DIR}/e3"
  echo "Results written to ${RUN_DIR}/"
else
  echo "[4/4] No captured study data (${DB}, ${MANIFEST}, ${STAGING_LOG}, ${SCALES})."
  echo "      Running the watermarked synthetic dry run instead. Its outputs are NOT results."
  python -m trinetra_link.cli demo run
fi
