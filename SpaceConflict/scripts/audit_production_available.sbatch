#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-p2-audit
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=runs/production_available_audit_%j.out
#SBATCH --error=runs/production_available_audit_%j.err

set -euo pipefail
PROJECT_ROOT="./SpaceConflict"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src python scripts/audit_release.py \
    --root "$PROJECT_ROOT" \
    --release production_available_v1 \
    --seed 20260826 \
    --quota-version quota_production_available_v1 \
    --unknown-version unknown_p1_v2 \
    --split-version world_split_v6
