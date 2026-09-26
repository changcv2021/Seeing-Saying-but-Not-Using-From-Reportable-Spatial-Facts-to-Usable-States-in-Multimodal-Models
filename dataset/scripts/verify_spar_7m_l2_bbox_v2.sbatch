#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-spar-l2-proof-v2
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=02:00:00
#SBATCH --output=runs/spar_7m_l2_bbox_proof_v2_%j.out
#SBATCH --error=runs/spar_7m_l2_bbox_proof_v2_%j.err

set -euo pipefail
PROJECT_ROOT="./dataset"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src python -m spaceconflict.cli realize-text \
    --claim-build-version claim_build_spar_7m_l2_bbox_v2 \
    --realization-version realization_spar_7m_l2_bbox_v2 \
    --candidates 3 --seed 20260826 --run-id "spar_7m_l2_bbox_realize_v2_${SLURM_JOB_ID}" \
    --workers 1 --resume
set +e
srun env PYTHONPATH=src python -m spaceconflict.cli verify-text \
    --realization-version realization_spar_7m_l2_bbox_v2 \
    --text-verification-version text_verification_spar_7m_l2_bbox_v2 \
    --seed 20260826 --run-id "spar_7m_l2_bbox_text_verify_v2_${SLURM_JOB_ID}" \
    --workers 1 --resume
TEXT_RC=$?
set -e
if [[ "$TEXT_RC" != 0 && "$TEXT_RC" != 2 ]]; then
    exit "$TEXT_RC"
fi
set +e
srun env PYTHONPATH=src python -m spaceconflict.cli verify-proofs \
    --text-verification-version text_verification_spar_7m_l2_bbox_v2 \
    --world-graph-manifest world_graphs/manifest.world_graph_spar_7m_bbox_identity_l2_v2.jsonl \
    --proof-verification-version proof_verification_spar_7m_l2_bbox_v2 \
    --seed 20260826 --run-id "spar_7m_l2_bbox_proof_verify_v2_${SLURM_JOB_ID}" \
    --workers 1 --resume
PROOF_RC=$?
set -e
if [[ "$PROOF_RC" != 0 && "$PROOF_RC" != 2 ]]; then
    exit "$PROOF_RC"
fi
