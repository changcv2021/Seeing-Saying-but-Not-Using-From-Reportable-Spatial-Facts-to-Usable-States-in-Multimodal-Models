#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-resume
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=2
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=runs/spaceconf_resume_%j.out
#SBATCH --error=runs/spaceconf_resume_%j.err

set -euo pipefail

PROJECT_ROOT="./SpaceConflict"
SEED=20260826
JOB_TAG="${SLURM_JOB_ID:-manual}"
RESULT_DIR="${PROJECT_ROOT}/runs/ca_resume_${JOB_TAG}"
mkdir -p "$RESULT_DIR"

module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src pytest -q >"${RESULT_DIR}/pytest.txt"
srun env PYTHONPATH=src python -m spaceconflict.cli reconstruct-source-qa \
    --dataset ca_vqa --seed "$SEED" --run-id "ca_reconstruct_fixed_${JOB_TAG}" --workers 1 \
    >"${RESULT_DIR}/source_reconstruction.json"
srun env PYTHONPATH=src python -m spaceconflict.cli validate-graphs \
    --dataset all --seed "$SEED" --run-id "validate_graph_v4_${JOB_TAG}" --workers 1 \
    >"${RESULT_DIR}/graph_validation.json"
srun env PYTHONPATH=src python -m spaceconflict.cli generate-claim-graphs \
    --config configs/golden_set.yaml --resume --seed "$SEED" \
    --run-id "claim_build_v4_${JOB_TAG}" --workers 1 \
    >"${RESULT_DIR}/claim_generation.json"
srun env PYTHONPATH=src python -m spaceconflict.cli realize-text \
    --candidates 3 --resume --seed "$SEED" --run-id "realization_v7_${JOB_TAG}" --workers 1 \
    >"${RESULT_DIR}/language_realization.json"

set +e
srun env PYTHONPATH=src python -m spaceconflict.cli verify-text \
    --resume --seed "$SEED" --run-id "text_verification_v7_${JOB_TAG}" --workers 1 \
    >"${RESULT_DIR}/text_verification.json"
TEXT_RC=$?
set -e
if [[ "$TEXT_RC" != 0 && "$TEXT_RC" != 2 ]]; then
    exit "$TEXT_RC"
fi

srun env PYTHONPATH=src python -m spaceconflict.cli verify-proofs \
    --resume --seed "$SEED" --run-id "proof_verification_v6_${JOB_TAG}" --workers 1 \
    >"${RESULT_DIR}/proof_verification.json"
srun env PYTHONPATH=src python -m spaceconflict.cli generate-unknown \
    --config configs/unknown_2k.yaml --resume --seed "$SEED" --limit 120 \
    --run-id "unknown_v1_${JOB_TAG}" --workers 1 \
    >"${RESULT_DIR}/unknown_generation.json"
srun env PYTHONPATH=src python -m spaceconflict.cli sample-quota \
    --config configs/golden_set.yaml --resume --seed "$SEED" --limit 120 \
    --run-id "quota_golden_v5_${JOB_TAG}" --workers 1 \
    >"${RESULT_DIR}/quota.json"
srun env PYTHONPATH=src python -m spaceconflict.cli export-benchmark \
    --resume --seed "$SEED" --limit 120 --run-id "export_golden_v5_${JOB_TAG}" --workers 1 \
    >"${RESULT_DIR}/export.json"
