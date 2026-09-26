#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-proof-regression
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=runs/proof_regression_%j.out
#SBATCH --error=runs/proof_regression_%j.err

set -euo pipefail
PROJECT_ROOT="./SpaceConflict"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src pytest -q
srun env PYTHONPATH=src python -m spaceconflict.cli verify-proofs \
    --resume \
    --run-id "proof_regression_${SLURM_JOB_ID}"
