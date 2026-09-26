#!/bin/bash
#SBATCH --job-name=sc_qwen_v10_full
#SBATCH --partition=gpu
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --gpus-per-node=1
#SBATCH --time=02:00:00
#SBATCH --array=0-7
#SBATCH --output=artifacts/model_results/qwen2_5_vl_7b/production_available_v10_14713_20260904/slurm/%x_%A_%a.out
#SBATCH --error=artifacts/model_results/qwen2_5_vl_7b/production_available_v10_14713_20260904/slurm/%x_%A_%a.err

set -euo pipefail

module load python/gpu/3.12.5
EVAL_ROOT="external/scratch/industbench_qwen25vl7b"
BUNDLE_ROOT="artifacts"
PROJECT_ROOT="./dataset"
RUN_ROOT="$BUNDLE_ROOT/model_results/qwen2_5_vl_7b/production_available_v10_14713_20260904"
source "$EVAL_ROOT/venv/bin/activate"
export PYTHONPATH="$BUNDLE_ROOT/software/src"
export HF_HOME="$EVAL_ROOT/hf_home"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"
cd "$BUNDLE_ROOT"

nvidia-smi --query-gpu=index,name,memory.total,driver_version --format=csv,noheader
mkdir -p "$RUN_ROOT/shards"
srun python "$PROJECT_ROOT/scripts/run_qwen25vl7b_spaceconflict_v10.py" \
  --requested-samples "$BUNDLE_ROOT/benchmark/l1_l3/evaluation/requested_samples.available.portable.jsonl" \
  --output "$RUN_ROOT/shards/predictions_$(printf '%03d' "$SLURM_ARRAY_TASK_ID").jsonl" \
  --run-id qwen25vl7b_v10_available_14713_20260904 \
  --num-shards "$SLURM_ARRAY_TASK_COUNT" \
  --shard-index "$SLURM_ARRAY_TASK_ID" \
  --seed 20260903 \
  --video-frames 16 \
  --resume
