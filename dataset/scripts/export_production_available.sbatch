#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-p2-available
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=runs/production_available_%j.out
#SBATCH --error=runs/production_available_%j.err

set -euo pipefail
PROJECT_ROOT="./dataset"
CONFIG="$PROJECT_ROOT/configs/production_available_v1.yaml"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src python -m spaceconflict.cli sample-quota \
    --config "$CONFIG" --seed 20260826 --resume \
    --run-id "production_available_quota_${SLURM_JOB_ID}"
srun env PYTHONPATH=src python -m spaceconflict.cli export-benchmark \
    --config "$CONFIG" --seed 20260826 --resume \
    --run-id "production_available_export_${SLURM_JOB_ID}"
