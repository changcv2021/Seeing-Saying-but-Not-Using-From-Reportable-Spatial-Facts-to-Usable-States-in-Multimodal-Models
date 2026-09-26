#!/usr/bin/env bash
# Operational retry only: unchanged scientific runner, requests, model and scorer.
#SBATCH --job-name=sc_qwen38_shard9_repair
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=128G
#SBATCH --gpus-per-node=2
#SBATCH --time=2-00:00:00
#SBATCH --array=9
#SBATCH --exclude=nid0642,nid0653,nid0661,nid0674,nid0684,nid0685,nid0687,nid0688,nid0694,nid0698
#SBATCH --chdir="./SpaceConflict/scripts/qwen38_shard9_recovery_20260921_v1"
#SBATCH --output=artifacts/model_results/qwen38_shard9_recovery_20260921_v1/logs/%x_%A_%a.out
#SBATCH --error=artifacts/model_results/qwen38_shard9_recovery_20260921_v1/logs/%x_%A_%a.err
set -euo pipefail
umask 0007
[[ "${SLURM_ARRAY_TASK_ID:?Slurm array required}" == 9 ]]
exec bash './SpaceConflict/scripts/qwen36_38_20260920_v1/job.sh' full --model qwen38_27b_direct "$@"
