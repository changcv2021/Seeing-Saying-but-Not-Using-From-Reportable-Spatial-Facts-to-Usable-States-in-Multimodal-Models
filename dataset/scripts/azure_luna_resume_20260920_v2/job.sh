#!/bin/bash
#SBATCH --job-name=sc_luna_resume_v2
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=24:00:00
#SBATCH --output=artifacts/model_results/azure_luna_resume_20260920_v2/logs/%x_%j.out
#SBATCH --error=artifacts/model_results/azure_luna_resume_20260920_v2/logs/%x_%j.err
set -euo pipefail
umask 077
module load python/gpu/3.12.5
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
runner='./dataset/scripts/azure_luna_resume_20260920_v2/resume.py'
interpreter=python
"$interpreter" -B "$runner" prepare --resume
infer_status=0
"$interpreter" -B "$runner" infer --resume || infer_status=$?
unset SPACECONFLICT_AZURE_API_KEY
"$interpreter" -B "$runner" score --resume
exit "$infer_status"
