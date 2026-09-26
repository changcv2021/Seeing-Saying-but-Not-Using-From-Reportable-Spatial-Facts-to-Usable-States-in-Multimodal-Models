#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-shortcut-audit
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=runs/shortcut_controls_%j.out
#SBATCH --error=runs/shortcut_controls_%j.err

set -euo pipefail
PROJECT_ROOT="./dataset"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src python scripts/audit_shortcut_controls.py \
    --root "$PROJECT_ROOT" \
    --release pilot_verified_2k_v2 \
    --quota-version quota_pilot_2k_v2 \
    --seed 20260826
