#!/bin/bash
set -euo pipefail
task_code='./phase4/execution_sws_v1'
module load python/gpu/3.12.5
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
export OPENBLAS_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
exec python -B "$task_code/$1.py" --run-id sws_20260909_v1 --seed 20260909 --resume
