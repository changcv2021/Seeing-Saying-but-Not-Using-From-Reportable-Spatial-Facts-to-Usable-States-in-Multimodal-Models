#!/bin/bash
#SBATCH --job-name=sc_bundle_final
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=02:00:00
#SBATCH --output=runs/evaluation_bundle_v1_20260903/slurm/%x_%j.out
#SBATCH --error=runs/evaluation_bundle_v1_20260903/slurm/%x_%j.err

set -euo pipefail
module load python/3.12.11
PROJECT_ROOT="./dataset"
BUNDLE_ROOT="external/project/iclr/spacebenchmark/SpaceConflict_Evaluation_Bundle_v1_20260903"
export PYTHONPATH="$PROJECT_ROOT/src"
export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"
cd "$PROJECT_ROOT"
srun python scripts/finalize_evaluation_bundle_v1.py \
  --bundle-root "$BUNDLE_ROOT" \
  --run-id spaceconflict_evaluation_bundle_v1_20260903 \
  --seed 20260903 \
  --resume
