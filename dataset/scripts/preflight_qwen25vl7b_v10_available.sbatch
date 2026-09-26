#!/bin/bash
#SBATCH --job-name=sc_qwen_v10_preflight
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
cd "$BUNDLE_ROOT"

srun python "$PROJECT_ROOT/scripts/run_qwen25vl7b_spaceconflict_v10.py" \
  --requested-samples "$BUNDLE_ROOT/benchmark/l1_l3/evaluation/requested_samples.available.portable.jsonl" \
  --output "$RUN_ROOT/preflight_unused.jsonl" \
  --run-id qwen25vl7b_v10_available_14713_20260904 \
  --num-shards 1 \
  --shard-index 0 \
  --dry-run \
  > "$RUN_ROOT/preflight.json"

jq -e '.status == "PLANNED" and .sample_count == 14713' "$RUN_ROOT/preflight.json" >/dev/null
echo "status=PASS"
echo "preflight=$RUN_ROOT/preflight.json"
