#!/bin/bash
#SBATCH --job-name=sc_qwen25vl7b_smoke
#SBATCH --partition=gpu
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --gpus-per-node=1
#SBATCH --time=00:30:00
#SBATCH --output=runs/mllm/qwen2_5_vl_7b/l4_balanced_test_v3_20260903/slurm/%x_%j.out
#SBATCH --error=runs/mllm/qwen2_5_vl_7b/l4_balanced_test_v3_20260903/slurm/%x_%j.err

set -euo pipefail
module load python/gpu/3.12.5
EVAL_ROOT=external/scratch/industbench_qwen25vl7b
PROJECT_ROOT="./dataset"
RUN_ROOT="$PROJECT_ROOT/runs/mllm/qwen2_5_vl_7b/l4_balanced_test_v3_20260903"
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
srun python scripts/run_qwen25vl7b_spaceconflict_l4.py \
  --requested-samples "$RUN_ROOT/requested_samples.smoke.jsonl" \
  --output "$RUN_ROOT/raw_responses.smoke.jsonl" \
  --run-id qwen25vl7b_l4_smoke_20260903
python scripts/score_mllm_l4.py \
  --requested-samples "$RUN_ROOT/requested_samples.smoke.jsonl" \
  --predictions "$RUN_ROOT/raw_responses.smoke.jsonl" \
  --output-json "$RUN_ROOT/smoke_score.json" \
  --output-md "$RUN_ROOT/smoke_score.md"

