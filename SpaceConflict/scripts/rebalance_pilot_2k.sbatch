#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-pilot-rebalance
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=2
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=runs/pilot_rebalance_%j.out
#SBATCH --error=runs/pilot_rebalance_%j.err

set -euo pipefail

PROJECT_ROOT="./SpaceConflict"
SEED=20260826
JOB_TAG="${SLURM_JOB_ID:-manual}"
RESULT_DIR="${PROJECT_ROOT}/runs/pilot_rebalance_${JOB_TAG}"
mkdir -p "$RESULT_DIR"

module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src pytest -q >"${RESULT_DIR}/pytest.txt"
srun env PYTHONPATH=src python -m spaceconflict.cli realize-text \
    --candidates 3 --resume --seed "$SEED" --run-id "realization_p1_v2_${JOB_TAG}" --workers 1 \
    >"${RESULT_DIR}/language_realization.json"

set +e
srun env PYTHONPATH=src python -m spaceconflict.cli verify-text \
    --resume --seed "$SEED" --run-id "text_verification_p1_v2_${JOB_TAG}" --workers 1 \
    >"${RESULT_DIR}/text_verification.json"
TEXT_RC=$?
set -e
if [[ "$TEXT_RC" != 0 && "$TEXT_RC" != 2 ]]; then
    exit "$TEXT_RC"
fi

srun env PYTHONPATH=src python -m spaceconflict.cli verify-proofs \
    --resume --seed "$SEED" --run-id "proof_verification_p1_v2_${JOB_TAG}" --workers 1 \
    >"${RESULT_DIR}/proof_verification.json"
srun env PYTHONPATH=src python -m spaceconflict.cli generate-unknown \
    --config configs/unknown_2k.yaml --resume --seed "$SEED" --limit 2000 \
    --run-id "unknown_p1_v2_${JOB_TAG}" --workers 1 \
    >"${RESULT_DIR}/unknown_generation.json"
srun env PYTHONPATH=src python -m spaceconflict.cli sample-quota \
    --config configs/pilot_2k.yaml --resume --seed "$SEED" \
    --run-id "quota_pilot_2k_v2_${JOB_TAG}" --workers 1 \
    >"${RESULT_DIR}/quota.json"
srun env PYTHONPATH=src python -m spaceconflict.cli export-benchmark \
    --resume --seed "$SEED" --run-id "export_pilot_2k_v2_${JOB_TAG}" --workers 1 \
    >"${RESULT_DIR}/export.json"

set +e
srun python scripts/analyze_pilot_2k.py \
    --root "$PROJECT_ROOT" --run-dir "$RESULT_DIR" --wall-seconds 177 --allocated-cpus 2 \
    --proof-version proof_verification_p1_v2 --quota-version quota_pilot_2k_v2 \
    --release pilot_verified_2k_v2 \
    >"${RESULT_DIR}/pilot_analysis.json"
ANALYSIS_RC=$?
set -e
srun python scripts/audit_release.py \
    --root "$PROJECT_ROOT" --release pilot_verified_2k_v2 \
    --quota-version quota_pilot_2k_v2 --unknown-version unknown_p1_v2 \
    --split-version world_split_v6 \
    >"${RESULT_DIR}/release_audit.json"
exit "$ANALYSIS_RC"
