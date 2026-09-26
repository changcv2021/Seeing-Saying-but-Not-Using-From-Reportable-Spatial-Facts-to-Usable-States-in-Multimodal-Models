#!/bin/bash
#SBATCH --job-name=sc_pss_v4_ddp_smoke
#SBATCH --partition=gpu
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --exclude=nid0642,nid0653,nid0661,nid0674,nid0684,nid0685,nid0687,nid0688,nid0694,nid0698
#SBATCH --cpus-per-task=8
#SBATCH --mem=128G
#SBATCH --gpus-per-node=2
#SBATCH --time=01:00:00
#SBATCH --output=artifacts/model_results/pss_20260922_v1/approved_v2/logs/%x_%j.out
#SBATCH --error=artifacts/model_results/pss_20260922_v1/approved_v2/logs/%x_%j.err
set -euo pipefail
module load python/gpu/3.12.5
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false
export HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
srun --cpu-bind=none --kill-on-bad-exit=1 python './training/formal_training_v4/smoke.py'

