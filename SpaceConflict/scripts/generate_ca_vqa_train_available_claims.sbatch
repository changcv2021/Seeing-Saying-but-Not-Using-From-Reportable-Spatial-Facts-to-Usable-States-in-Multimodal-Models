#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-ca-avail-claims
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=runs/ca_train_available_claims_%j.out
#SBATCH --error=runs/ca_train_available_claims_%j.err

set -euo pipefail
PROJECT_ROOT="./SpaceConflict"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src python -m spaceconflict.cli generate-claim-graphs \
    --config configs/ca_vqa_train_available_v1.yaml --seed 20260826 \
    --run-id "ca_train_available_claims_${SLURM_JOB_ID}" --workers 1 --resume
