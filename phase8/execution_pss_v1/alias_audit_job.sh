#!/bin/bash
#SBATCH --job-name=sc_pss_alias_audit
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=artifacts/model_results/pss_20260922_v1/logs/alias_%j.out
#SBATCH --error=artifacts/model_results/pss_20260922_v1/logs/alias_%j.err
set -euo pipefail
module load python/gpu/3.12.5
export OMP_NUM_THREADS=2
exec python './phase8/execution_pss_v1/verify_world_aliases.py' --run-root artifacts/model_results/pss_20260922_v1
