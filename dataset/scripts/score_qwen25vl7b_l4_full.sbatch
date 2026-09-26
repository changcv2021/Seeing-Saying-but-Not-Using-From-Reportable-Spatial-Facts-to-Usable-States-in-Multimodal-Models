#!/bin/bash
#SBATCH --job-name=sc_qwen25vl7b_score
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:20:00
#SBATCH --output=runs/mllm/qwen2_5_vl_7b/l4_balanced_test_v3_20260903/slurm/%x_%j.out
#SBATCH --error=runs/mllm/qwen2_5_vl_7b/l4_balanced_test_v3_20260903/slurm/%x_%j.err

set -euo pipefail
module load python/3.12.11
PROJECT_ROOT="./dataset"
RUN_ROOT="$PROJECT_ROOT/runs/mllm/qwen2_5_vl_7b/l4_balanced_test_v3_20260903"
export PYTHONPATH="$PROJECT_ROOT/src"
cd "$PROJECT_ROOT"
python scripts/score_mllm_l4.py \
  --requested-samples "$RUN_ROOT/requested_samples.jsonl" \
  --predictions "$RUN_ROOT"/shards/predictions_*.jsonl \
  --output-json "$RUN_ROOT/final_score.json" \
  --output-md "$RUN_ROOT/final_score.md"

