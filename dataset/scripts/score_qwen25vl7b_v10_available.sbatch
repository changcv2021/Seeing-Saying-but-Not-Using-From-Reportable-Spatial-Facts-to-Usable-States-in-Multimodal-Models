#!/bin/bash
#SBATCH --job-name=sc_score_v10_full
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=artifacts/model_results/qwen2_5_vl_7b/production_available_v10_14713_20260904/slurm/%x_%j.out
#SBATCH --error=artifacts/model_results/qwen2_5_vl_7b/production_available_v10_14713_20260904/slurm/%x_%j.err

set -euo pipefail

module load python/3.12.11
BUNDLE_ROOT="artifacts"
PROJECT_ROOT="./dataset"
RUN_ROOT="$BUNDLE_ROOT/model_results/qwen2_5_vl_7b/production_available_v10_14713_20260904"
export PYTHONPATH="$BUNDLE_ROOT/software/src"
cd "$BUNDLE_ROOT"

srun python "$PROJECT_ROOT/scripts/score_mllm_v10_smoke.py" \
  --requested-samples "$BUNDLE_ROOT/benchmark/l1_l3/evaluation/requested_samples.available.portable.jsonl" \
  --predictions "$RUN_ROOT"/shards/predictions_*.jsonl \
  --media-report "$BUNDLE_ROOT/benchmark/l1_l3/evaluation/media_resolution_report.json" \
  --claims "$BUNDLE_ROOT/benchmark/l1_l3/release/claims.jsonl" \
  --unknown "$BUNDLE_ROOT/benchmark/l1_l3/release/unknown_challenge.jsonl" \
  --output-json "$RUN_ROOT/final_score.json" \
  --output-md "$RUN_ROOT/final_score.md" \
  --run-id qwen25vl7b_v10_available_14713_20260904 \
  --evaluation-kind available_media_baseline \
  --seed 20260903
