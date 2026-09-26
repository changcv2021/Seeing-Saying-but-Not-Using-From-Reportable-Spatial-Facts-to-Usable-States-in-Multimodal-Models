#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-visresult
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=00:45:00
#SBATCH --output=runs/visresult_%j.out
#SBATCH --error=runs/visresult_%j.err

set -euo pipefail
PROJECT_ROOT="./SpaceConflict"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun python scripts/build_visualization_results.py \
    --config configs/visualization_results_v1.yaml \
    --release-version composite_production_v10_l4_v3_3 \
    --output-dir visresult \
    --seed 20260829 \
    --run-id "visresult_${SLURM_JOB_ID}" \
    --resume
