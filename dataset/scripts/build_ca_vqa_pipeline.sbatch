#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-pipeline
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=2
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=runs/spaceconf_pipeline_%j.out
#SBATCH --error=runs/spaceconf_pipeline_%j.err

set -euo pipefail

PROJECT_ROOT="./dataset"
SEED=20260826
JOB_TAG="${SLURM_JOB_ID:-manual}"
RESULT_DIR="${PROJECT_ROOT}/runs/ca_pipeline_${JOB_TAG}"
mkdir -p "$RESULT_DIR"

module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src pytest -q >"${RESULT_DIR}/pytest.txt"
srun env PYTHONPATH=src python -m spaceconflict.cli profile \
    --dataset ca_vqa --seed "$SEED" --run-id "ca_profile_${JOB_TAG}" --workers 1 \
    >"${RESULT_DIR}/profile.json"
srun env PYTHONPATH=src python -m spaceconflict.cli validate-contract \
    --dataset ca_vqa --seed "$SEED" --run-id "ca_contract_${JOB_TAG}" --workers 1 \
    >"${RESULT_DIR}/contract.json"
srun env PYTHONPATH=src python -m spaceconflict.cli build-canonical \
    --dataset spar,vsi_bench,sti_bench,omnispatial,ca_vqa --resume \
    --seed "$SEED" --run-id "canonical_v3_${JOB_TAG}" --workers 1 \
    >"${RESULT_DIR}/canonical.json"
srun env PYTHONPATH=src python -m spaceconflict.cli reconstruct-source-qa \
    --dataset ca_vqa --seed "$SEED" --run-id "ca_reconstruct_${JOB_TAG}" --workers 1 \
    >"${RESULT_DIR}/source_reconstruction.json"
srun env PYTHONPATH=src python -m spaceconflict.cli build-world-index \
    --resume --seed "$SEED" --run-id "world_index_v5_${JOB_TAG}" --workers 1 \
    >"${RESULT_DIR}/world_index.json"
srun env PYTHONPATH=src python -m spaceconflict.cli split-worlds \
    --resume --seed "$SEED" --run-id "world_split_v5_${JOB_TAG}" --workers 1 \
    >"${RESULT_DIR}/world_split.json"
srun env PYTHONPATH=src python -m spaceconflict.cli build-graphs \
    --dataset spar,vsi_bench,sti_bench,omnispatial,ca_vqa --resume \
    --seed "$SEED" --run-id "world_graph_v4_${JOB_TAG}" --workers 1 \
    >"${RESULT_DIR}/world_graph.json"
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
