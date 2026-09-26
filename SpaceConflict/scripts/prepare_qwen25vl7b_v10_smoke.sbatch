#!/bin/bash
#SBATCH --job-name=sc_v10_media_smoke
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=00:30:00
#SBATCH --output=runs/mllm/qwen2_5_vl_7b/production_available_v10_smoke_20260903/slurm/%x_%j.out
#SBATCH --error=runs/mllm/qwen2_5_vl_7b/production_available_v10_smoke_20260903/slurm/%x_%j.err

set -euo pipefail
module load python/3.12.11
PROJECT_ROOT="./SpaceConflict"
STORAGE_ROOT="external/upstream"
RUN_ROOT="$PROJECT_ROOT/runs/mllm/qwen2_5_vl_7b/production_available_v10_smoke_20260903"
CACHE_ROOT="$STORAGE_ROOT/evaluation_cache/qwen2_5_vl_7b/production_available_v10_smoke_20260903"
export PYTHONPATH="$PROJECT_ROOT/src"
export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"
cd "$PROJECT_ROOT"
mkdir -p "$RUN_ROOT/slurm"
srun python scripts/prepare_mllm_v10_smoke.py \
  --storage-root "$STORAGE_ROOT" \
  --cache-root "$CACHE_ROOT" \
  --output-dir "$RUN_ROOT" \
  --run-id qwen25vl7b_v10_cross_source_smoke_20260903 \
  --seed 20260903
