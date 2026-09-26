#!/bin/bash
#SBATCH --job-name=sc_score_v10_r3
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:20:00
#SBATCH --output=runs/mllm/qwen2_5_vl_7b/production_available_v10_smoke_r3_20260903/slurm/%x_%j.out
#SBATCH --error=runs/mllm/qwen2_5_vl_7b/production_available_v10_smoke_r3_20260903/slurm/%x_%j.err

set -euo pipefail
module load python/3.12.11
PROJECT_ROOT="./dataset"
RUN_ROOT="$PROJECT_ROOT/runs/mllm/qwen2_5_vl_7b/production_available_v10_smoke_r3_20260903"
SOURCE_MEDIA_REPORT="$PROJECT_ROOT/runs/mllm/qwen2_5_vl_7b/production_available_v10_smoke_r3_media_20260903/media_resolution_report.smoke.json"
export PYTHONPATH="$PROJECT_ROOT/src"
cd "$PROJECT_ROOT"
srun python scripts/score_mllm_v10_smoke.py \
  --requested-samples "$RUN_ROOT/requested_samples.smoke.jsonl" \
  --predictions "$RUN_ROOT/raw_responses.smoke.jsonl" \
  --media-report "$SOURCE_MEDIA_REPORT" \
  --output-json "$RUN_ROOT/smoke_score.json" \
  --output-md "$RUN_ROOT/smoke_score.md" \
  --run-id qwen25vl7b_v10_cross_source_smoke_r3_20260903 \
  --seed 20260903
