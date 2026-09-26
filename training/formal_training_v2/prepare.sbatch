#!/bin/bash
#SBATCH --job-name=sc_pss_formal_prepare
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=00:45:00
#SBATCH --output=artifacts/model_results/pss_20260922_v1/approved_v2/logs/%x_%j.out
#SBATCH --error=artifacts/model_results/pss_20260922_v1/approved_v2/logs/%x_%j.err
set -euo pipefail
module load python/gpu/3.12.5
export OMP_NUM_THREADS=2 TOKENIZERS_PARALLELISM=false HF_HUB_OFFLINE=1 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
srun python './training/formal_training_v2/prepare.py'
