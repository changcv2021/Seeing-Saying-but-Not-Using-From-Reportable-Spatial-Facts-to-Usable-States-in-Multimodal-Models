#!/bin/bash
#SBATCH --job-name=sc_qwen_summary
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:10:00
#SBATCH --output=artifacts/model_results/qwen2_5_vl_7b/production_available_v10_14713_20260904/slurm/%x_%j.out
#SBATCH --error=artifacts/model_results/qwen2_5_vl_7b/production_available_v10_14713_20260904/slurm/%x_%j.err

set -euo pipefail

module load python/3.12.11
BUNDLE_ROOT="artifacts"
PROJECT_ROOT="./SpaceConflict"
RUN_ROOT="$BUNDLE_ROOT/model_results/qwen2_5_vl_7b/production_available_v10_14713_20260904"

srun python "$PROJECT_ROOT/scripts/summarize_qwen25vl7b_spaceconflict.py" \
  --l1-l3-score "$RUN_ROOT/final_score.json" \
  --l4-score "$BUNDLE_ROOT/model_results/qwen2_5_vl_7b/l4_balanced_test_v3_20260903/final_score.json" \
  --output-json "$RUN_ROOT/SpaceConflict_Qwen25VL7B_Composite_Evaluation_20260904.json" \
  --output-md "$RUN_ROOT/SpaceConflict_Qwen25VL7B_Composite_Evaluation_Report_CN.md"
