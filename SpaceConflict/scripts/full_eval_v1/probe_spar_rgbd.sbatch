#!/bin/bash
#SBATCH --job-name=sc_rgbd_probe
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:20:00
#SBATCH --output=artifacts/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v2_scans_20260905/slurm/rgbd_probe_%j.out
#SBATCH --error=artifacts/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v2_scans_20260905/slurm/rgbd_probe_%j.err
set -euo pipefail
module load python/3.12.11
project='./SpaceConflict'
python -u "$project/scripts/full_eval_v1/probe_spar_rgbd.py" --output "artifacts/upstream_media/spar7m_acquisition/rgbd_probe_${SLURM_JOB_ID}" --run-id "rgbd_bounded_probe_${SLURM_JOB_ID}" --seed 20260905
