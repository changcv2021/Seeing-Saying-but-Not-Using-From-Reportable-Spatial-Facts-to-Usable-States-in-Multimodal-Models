#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-ca-avail-unknown
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=runs/ca_train_available_unknown_%j.out
#SBATCH --error=runs/ca_train_available_unknown_%j.err

set -euo pipefail
PROJECT_ROOT="./SpaceConflict"
CONFIG="$PROJECT_ROOT/configs/ca_vqa_train_available_unknown_v1.yaml"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src python -m spaceconflict.cli generate-unknown \
    --config "$CONFIG" --seed 20260826 --resume \
    --run-id "ca_train_available_unknown_${SLURM_JOB_ID}" --workers 1
