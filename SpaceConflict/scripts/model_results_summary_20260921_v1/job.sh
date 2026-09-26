#!/usr/bin/env bash
#SBATCH --job-name=sc_model_result_summary
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --partition=general
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:45:00
#SBATCH --output=artifacts/model_results/model_results_summary_20260921_v1/logs/%x_%j.out
#SBATCH --error=artifacts/model_results/model_results_summary_20260921_v1/logs/%x_%j.err
set -euo pipefail
umask 0007
module load python/gpu/3.12.5
export PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
exec python -B './SpaceConflict/scripts/model_results_summary_20260921_v1/build.py' "$@"
