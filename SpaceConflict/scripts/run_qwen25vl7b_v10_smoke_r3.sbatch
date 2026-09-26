#!/bin/bash
#SBATCH --job-name=sc_qwen_v10_r3
#SBATCH --partition=gpu
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --gpus-per-node=1
#SBATCH --time=00:30:00
#SBATCH --output=runs/mllm/qwen2_5_vl_7b/production_available_v10_smoke_r3_20260903/slurm/%x_%j.out
#SBATCH --error=runs/mllm/qwen2_5_vl_7b/production_available_v10_smoke_r3_20260903/slurm/%x_%j.err

set -euo pipefail
module load python/gpu/3.12.5
EVAL_ROOT="external/scratch/industbench_qwen25vl7b"
PROJECT_ROOT="./SpaceConflict"
RUN_ROOT="$PROJECT_ROOT/runs/mllm/qwen2_5_vl_7b/production_available_v10_smoke_r3_20260903"
source "$EVAL_ROOT/venv/bin/activate"
export PYTHONPATH="$PROJECT_ROOT/src"
export HF_HOME="$EVAL_ROOT/hf_home"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"
cd "$PROJECT_ROOT"
nvidia-smi --query-gpu=index,name,memory.total,driver_version --format=csv,noheader
srun python scripts/run_qwen25vl7b_spaceconflict_v10.py \
  --requested-samples "$RUN_ROOT/requested_samples.smoke.jsonl" \
  --output "$RUN_ROOT/raw_responses.smoke.jsonl" \
  --run-id qwen25vl7b_v10_cross_source_smoke_r3_20260903 \
  --seed 20260903 \
  --video-frames 16
