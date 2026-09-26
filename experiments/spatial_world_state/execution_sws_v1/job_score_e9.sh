#!/bin/bash
set -euo pipefail
task_code='./experiments/spatial_world_state/execution_sws_v1'
module load python/gpu/3.12.5
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
export OPENBLAS_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
exec python -B "$task_code/score_e9_v1.py" --run-id sws_20260909_v1 --seed 20260909 --resume --model "$1"
