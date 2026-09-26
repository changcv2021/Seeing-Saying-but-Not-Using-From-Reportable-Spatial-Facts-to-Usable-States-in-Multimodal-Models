#!/bin/bash
#SBATCH --job-name=sc_rgbd_format_recovery_v2
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=04:00:00
#SBATCH --output=artifacts/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v2_scans_20260905/slurm/rgbd_format_v2_%j.out
#SBATCH --error=artifacts/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v2_scans_20260905/slurm/rgbd_format_v2_%j.err
set -euo pipefail
umask 0007
module load python/3.12.11
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
bundle=artifacts
run="$bundle/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v2_scans_20260905"
acq="$bundle/upstream_media/spar7m_acquisition"
code="$run/code_rgbd_formats_v2"
python "$code/test_rgbd_formats_v2.py"
python "$code/test_media_recovery.py"
srun python -u "$code/extract_official_rgbd_v2.py" \
  --archive-root "$acq/rgbd_recovery_v1_20260905/archives" \
  --checksum-manifest "$acq/rgbd_recovery_v1_20260905/official_sha256.txt" \
  --requirements "$acq/repair_missing_v2_20260905/required_accessible.jsonl" \
  --output "$acq/rgbd_recovery_v2_20260905" --run-id "rgbd_format_recovery_${SLURM_JOB_ID}" --seed 20260905 --resume
