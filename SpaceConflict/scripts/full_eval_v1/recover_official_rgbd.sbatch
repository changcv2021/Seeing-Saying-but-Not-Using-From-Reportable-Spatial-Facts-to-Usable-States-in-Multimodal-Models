#!/bin/bash
#SBATCH --job-name=sc_official_rgbd_recovery
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=08:00:00
#SBATCH --output=artifacts/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v2_scans_20260905/slurm/official_rgbd_%j.out
#SBATCH --error=artifacts/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v2_scans_20260905/slurm/official_rgbd_%j.err
set -euo pipefail
umask 0007
module load python/3.12.11
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
bundle=artifacts
run="$bundle/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v2_scans_20260905"
python -u "$run/code_rgbd_recovery_v1/recover_official_rgbd.py" \
  --requirements "$bundle/upstream_media/spar7m_acquisition/repair_missing_v2_20260905/required_accessible.jsonl" \
  --output "$bundle/upstream_media/spar7m_acquisition/rgbd_recovery_v1_20260905" \
  --run-id "official_rgbd_recovery_${SLURM_JOB_ID}" --seed 20260905 --workers 4 --resume
