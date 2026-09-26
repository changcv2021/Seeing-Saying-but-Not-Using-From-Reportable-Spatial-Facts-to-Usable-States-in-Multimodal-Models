#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-final-report
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:10:00
#SBATCH --output=runs/final_report_%j.out
#SBATCH --error=runs/final_report_%j.err

set -euo pipefail
PROJECT_ROOT="./dataset"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src python -m spaceconflict.cli report \
    --release-dir "$PROJECT_ROOT/release/pilot_verified_2k_v2" \
    --output-json "$PROJECT_ROOT/reports/final.pilot_verified_2k_v2.json" \
    --output-markdown "$PROJECT_ROOT/reports/final.pilot_verified_2k_v2.md" \
    --resume \
    --run-id "final_report_${SLURM_JOB_ID}"
