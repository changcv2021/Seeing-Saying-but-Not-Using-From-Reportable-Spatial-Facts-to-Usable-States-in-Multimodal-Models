#!/bin/bash
#SBATCH --job-name=sc_media_inspect
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:20:00
#SBATCH --output=artifacts/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v1_20260904/slurm/media_inspect_%j.out
#SBATCH --error=artifacts/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v1_20260904/slurm/media_inspect_%j.err
set -euo pipefail
module load python/3.12.11
srun python -u './dataset/scripts/full_eval_v1/inspect_downloaded_media.py' --run-id media_inspect_20260905 --seed 20260905
