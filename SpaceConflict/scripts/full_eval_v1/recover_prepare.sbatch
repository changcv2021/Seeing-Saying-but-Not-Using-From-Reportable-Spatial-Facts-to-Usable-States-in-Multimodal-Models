#!/usr/bin/env bash
#SBATCH --job-name=sc_prepare_r2
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=artifacts/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v1_20260904/slurm/recovery_prepare_%j.out
#SBATCH --error=artifacts/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v1_20260904/slurm/recovery_prepare_%j.err
set -euo pipefail
umask 0007
module load python/3.12.11
run=artifacts/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v1_20260904
project='./SpaceConflict'
python "$run/code_prepare_r4/test_protocol.py"
extra=()
if [[ "${1:-prepare}" == metadata ]]; then extra+=(--metadata-only); fi
python -u "$run/code_prepare_r4/prepare.py" \
  --bundle artifacts \
  --project "$project" --run-root "$run" \
  --run-id full_release_qwen35judge_v1_20260904 --seed 20260904 --resume "${extra[@]}"
