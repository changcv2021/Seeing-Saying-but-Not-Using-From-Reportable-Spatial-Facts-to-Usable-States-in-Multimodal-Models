#!/bin/bash
#SBATCH --job-name=sc_v10_media_r3
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=00:30:00
#SBATCH --output=runs/mllm/qwen2_5_vl_7b/production_available_v10_smoke_r3_media_20260903/slurm/%x_%j.out
#SBATCH --error=runs/mllm/qwen2_5_vl_7b/production_available_v10_smoke_r3_media_20260903/slurm/%x_%j.err

set -euo pipefail
module load python/gpu/3.12.5
EVAL_ROOT="external/scratch/industbench_qwen25vl7b"
PROJECT_ROOT="./SpaceConflict"
STORAGE_ROOT="external/upstream"
RUN_ROOT="$PROJECT_ROOT/runs/mllm/qwen2_5_vl_7b/production_available_v10_smoke_r3_media_20260903"
CACHE_ROOT="$STORAGE_ROOT/evaluation_cache/qwen2_5_vl_7b/production_available_v10_smoke_r3_20260903"
source "$EVAL_ROOT/venv/bin/activate"
export PYTHONPATH="$PROJECT_ROOT/src"
export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"
cd "$PROJECT_ROOT"
srun python scripts/prepare_mllm_v10_smoke.py \
  --storage-root "$STORAGE_ROOT" \
  --cache-root "$CACHE_ROOT" \
  --output-dir "$RUN_ROOT" \
  --run-id qwen25vl7b_v10_cross_source_smoke_r3_media_20260903 \
  --seed 20260903 \
  --resume \
  --allow-rejects \
  --known-unavailable-revision 0fe664cbada1e7c1173fd743e0f781882eebf777
