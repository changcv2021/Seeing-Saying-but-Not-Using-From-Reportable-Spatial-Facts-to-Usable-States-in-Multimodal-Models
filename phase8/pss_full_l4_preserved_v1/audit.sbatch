#!/bin/bash
#SBATCH --job-name=sc_pss_preserve_audit
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=01:00:00
#SBATCH --output=artifacts/model_results/pss_20260922_v1/approved_v2/pss_full_l4_preserved_v1/logs/%x_%j.out
#SBATCH --error=artifacts/model_results/pss_20260922_v1/approved_v2/pss_full_l4_preserved_v1/logs/%x_%j.err
set -euo pipefail
module load python/gpu/3.12.5
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
srun --cpu-bind=none python './phase8/pss_full_l4_preserved_v1/audit.py'
