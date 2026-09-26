#!/bin/bash
#SBATCH --job-name=sc_frame_identity
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:20:00
#SBATCH --output=artifacts/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v1_20260904/slurm/frame_identity_%j.out
#SBATCH --error=artifacts/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v1_20260904/slurm/frame_identity_%j.err
set -euo pipefail
module load python/3.12.11
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
srun python -u './SpaceConflict/scripts/full_eval_v1/inspect_frame_identity.py' --run-id frame_identity_20260905 --seed 20260905
