#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-spar-l2-audit-v2
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=runs/spar_7m_l2_bbox_audit_v2_%j.out
#SBATCH --error=runs/spar_7m_l2_bbox_audit_v2_%j.err

set -euo pipefail
PROJECT_ROOT="./dataset"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src python scripts/audit_spar_7m_l2_bbox_tier.py \
    --root "$PROJECT_ROOT" \
    --proof candidates/auto_accepted/pairs.proof_verification_spar_7m_l2_bbox_v2.jsonl \
    --output reports/spar/l2_bbox_tier_audit.v2.json \
    --audit-version spar_7m_l2_bbox_tier_audit_v2 \
    --run-id "spar_7m_l2_bbox_audit_v2_${SLURM_JOB_ID}" --resume
