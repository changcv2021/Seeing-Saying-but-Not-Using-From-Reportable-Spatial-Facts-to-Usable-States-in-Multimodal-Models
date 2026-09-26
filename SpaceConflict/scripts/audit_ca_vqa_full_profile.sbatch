#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-ca-full-audit
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=runs/ca_full_audit_%j.out
#SBATCH --error=runs/ca_full_audit_%j.err

set -euo pipefail
PROJECT_ROOT="./SpaceConflict"
module load python/3.12.11
cd "$PROJECT_ROOT"
srun python scripts/audit_ca_vqa_full_profile.py \
    --download-validation "$PROJECT_ROOT/reports/ca_vqa/download_validation.full_v1.json" \
    --profile "$PROJECT_ROOT/reports/ca_vqa/profile.full_download_v1.json" \
    --output "$PROJECT_ROOT/reports/ca_vqa/full_acquisition_profile_audit.v1.json"
