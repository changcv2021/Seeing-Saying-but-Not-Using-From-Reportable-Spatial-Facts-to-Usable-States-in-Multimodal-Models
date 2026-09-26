#!/bin/bash
#SBATCH --job-name=sc_recover_bench_views
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=artifacts/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v2_scans_20260905/slurm/recover_bench_%j.out
#SBATCH --error=artifacts/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v2_scans_20260905/slurm/recover_bench_%j.err
set -euo pipefail
module load python/3.12.11
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
bundle=artifacts
project='./SpaceConflict'
out="$bundle/upstream_media/spar7m_acquisition/repair_missing_v2_20260905"
python -u "$project/scripts/full_eval_v1/recover_bench_unmarked.py" --bundle "$bundle" --requirements "$out/required_accessible.jsonl" \
  --output "$out/bench_unmarked" --run-id bench_unmarked_recovery_20260905 --seed 20260905 --resume
