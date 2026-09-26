#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-ca-prod-lang
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=runs/ca_train_production_language_%j.out
#SBATCH --error=runs/ca_train_production_language_%j.err

set -euo pipefail
PROJECT_ROOT="./dataset"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src python -m spaceconflict.cli realize-text \
    --claim-build-version claim_build_ca_train_production_v1 \
    --realization-version realization_ca_train_production_v1 \
    --candidates 3 --seed 20260826 --run-id "ca_train_production_realize_${SLURM_JOB_ID}" \
    --workers 1 --resume
set +e
srun env PYTHONPATH=src python -m spaceconflict.cli verify-text \
    --realization-version realization_ca_train_production_v1 \
    --text-verification-version text_verification_ca_train_production_v1 \
    --seed 20260826 --run-id "ca_train_production_text_verify_${SLURM_JOB_ID}" \
    --workers 1 --resume
TEXT_RC=$?
set -e
if [[ "$TEXT_RC" != 0 && "$TEXT_RC" != 2 ]]; then
    exit "$TEXT_RC"
fi
srun env PYTHONPATH=src python -m spaceconflict.cli verify-proofs \
    --text-verification-version text_verification_ca_train_production_v1 \
    --world-graph-manifest world_graphs/manifest.world_graph_train_production_subset_v1.jsonl \
    --proof-verification-version proof_verification_ca_train_production_v1 \
    --seed 20260826 --run-id "ca_train_production_proof_verify_${SLURM_JOB_ID}" \
    --workers 1 --resume
