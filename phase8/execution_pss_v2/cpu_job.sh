#!/bin/bash
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:45:00
#SBATCH --output=artifacts/model_results/pss_20260922_v1/approved_v2/logs/%x_%j.out
#SBATCH --error=artifacts/model_results/pss_20260922_v1/approved_v2/logs/%x_%j.err
set -euo pipefail
module load python/gpu/3.12.5
export OMP_NUM_THREADS=2
export PIP_CACHE_DIR=artifacts/model_results/pss_20260922_v1/approved_v2/environment/pip_cache
case "$1" in
  split) step=freeze_split.py;;
  environment) step=prepare_environment.py;;
  supervision) step=build_supervision.py;;
  *) exit 2;;
esac
exec python "./phase8/execution_pss_v2/${step}" --resume
