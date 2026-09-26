#!/bin/bash
#SBATCH --job-name=sc_score_v10_smoke
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:20:00
#SBATCH --output=runs/mllm/qwen2_5_vl_7b/production_available_v10_smoke_r1_20260903/slurm/%x_%j.out
#SBATCH --error=runs/mllm/qwen2_5_vl_7b/production_available_v10_smoke_r1_20260903/slurm/%x_%j.err

set -euo pipefail
module load python/3.12.11
PROJECT_ROOT="./SpaceConflict"
RUN_ROOT="$PROJECT_ROOT/runs/mllm/qwen2_5_vl_7b/production_available_v10_smoke_r1_20260903"
export PYTHONPATH="$PROJECT_ROOT/src"
cd "$PROJECT_ROOT"
srun python scripts/score_mllm_v10_smoke.py \
  --requested-samples "$RUN_ROOT/requested_samples.smoke.jsonl" \
  --predictions "$RUN_ROOT/raw_responses.smoke.jsonl" \
  --media-report "$RUN_ROOT/media_resolution_report.smoke.json" \
  --output-json "$RUN_ROOT/smoke_score.json" \
  --output-md "$RUN_ROOT/smoke_score.md" \
  --run-id qwen25vl7b_v10_cross_source_smoke_r1_20260903 \
  --seed 20260903
