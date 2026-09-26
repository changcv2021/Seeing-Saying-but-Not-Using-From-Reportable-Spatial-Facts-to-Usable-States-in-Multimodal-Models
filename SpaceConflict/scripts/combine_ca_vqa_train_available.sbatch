#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-ca-avail-combine
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:10:00
#SBATCH --output=runs/ca_train_available_combine_%j.out
#SBATCH --error=runs/ca_train_available_combine_%j.err

set -euo pipefail
PROJECT_ROOT="./SpaceConflict"
REVISION="080812355c21a40f437ed03d4ae558d35bfa2929"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src python scripts/combine_ca_vqa_train_subset.py \
    --root "$PROJECT_ROOT" --source-revision "$REVISION" \
    --tasks binary,cardinality --combine-version ca_vqa_train_available_subset_v1 \
    --report-name train_available_subset.combined.v1.json \
    --world-cap 1000 --seed 20260826 --run-id "ca_train_available_combine_${SLURM_JOB_ID}" --resume
