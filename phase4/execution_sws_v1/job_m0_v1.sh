#!/bin/bash
set -euo pipefail
task_code='./phase4/execution_sws_v1'
task_project='./SpaceConflict'
module load python/gpu/3.12.5
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$task_project/src${PYTHONPATH:+:$PYTHONPATH}"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
export OPENBLAS_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
export HF_HUB_OFFLINE=1
exec python -B "$task_code/m0_v1.py" --run-id sws_20260909_v1 --seed 20260909 --resume
