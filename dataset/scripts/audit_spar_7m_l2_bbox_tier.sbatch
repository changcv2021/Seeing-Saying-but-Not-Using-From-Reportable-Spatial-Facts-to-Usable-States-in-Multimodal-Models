#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-spar-l2-audit
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:10:00
#SBATCH --output=runs/spar_7m_l2_bbox_audit_%j.out
#SBATCH --error=runs/spar_7m_l2_bbox_audit_%j.err

set -euo pipefail
PROJECT_ROOT="./dataset"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src python scripts/audit_spar_7m_l2_bbox_tier.py \
    --root "$PROJECT_ROOT" \
    --proof candidates/auto_accepted/pairs.proof_verification_spar_7m_l2_bbox_v1.jsonl \
    --output reports/spar/l2_bbox_tier_audit.v1.json \
    --run-id "spar_7m_l2_bbox_audit_${SLURM_JOB_ID}" --resume
