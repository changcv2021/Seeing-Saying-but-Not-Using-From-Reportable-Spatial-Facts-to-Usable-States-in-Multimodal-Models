#!/bin/bash
#SBATCH --job-name=sc_pss_data_audit
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:45:00
#SBATCH --output=artifacts/model_results/pss_20260922_v1/logs/audit_%j.out
#SBATCH --error=artifacts/model_results/pss_20260922_v1/logs/audit_%j.err
set -euo pipefail
module load python/gpu/3.12.5
export OMP_NUM_THREADS=4
exec python './training/execution_pss_v1/audit.py' --run-root artifacts/model_results/pss_20260922_v1 --run-id pss_20260922_v1 --seed 20260922
