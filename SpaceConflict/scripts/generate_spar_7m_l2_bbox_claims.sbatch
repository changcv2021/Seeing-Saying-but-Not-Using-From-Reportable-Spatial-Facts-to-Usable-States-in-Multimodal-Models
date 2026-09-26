#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-spar-l2-claims
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=runs/spar_7m_l2_bbox_claims_%j.out
#SBATCH --error=runs/spar_7m_l2_bbox_claims_%j.err

set -euo pipefail
PROJECT_ROOT="./SpaceConflict"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src python -m spaceconflict.cli generate-claim-graphs \
    --config configs/spar_7m_l2_bbox_v1.yaml --seed 20260826 \
    --run-id "spar_7m_l2_bbox_claims_${SLURM_JOB_ID}" --workers 1 --resume
