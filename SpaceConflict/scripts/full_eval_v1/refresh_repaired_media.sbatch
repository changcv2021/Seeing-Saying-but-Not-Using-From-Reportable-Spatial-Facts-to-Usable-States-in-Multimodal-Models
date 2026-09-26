#!/bin/bash
#SBATCH --job-name=sc_refresh_repaired_media
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=artifacts/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v2_scans_20260905/slurm/refresh_media_%j.out
#SBATCH --error=artifacts/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v2_scans_20260905/slurm/refresh_media_%j.err
set -euo pipefail
umask 0007
module load python/3.12.11
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
bundle=artifacts
run="$bundle/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v2_scans_20260905"
project='./SpaceConflict'
code="$run/code_refresh_v3"
python "$code/test_protocol.py"
python "$code/test_scan_integration.py"
python -u "$code/refresh_repaired_media.py" --bundle "$bundle" --project "$project" --run-root "$run" \
  --repair-root "$bundle/upstream_media/spar7m_acquisition/repair_missing_v2_20260905" \
  --run-id "media_repair_${SLURM_JOB_ID}" --seed 20260905 --resume "$@"
