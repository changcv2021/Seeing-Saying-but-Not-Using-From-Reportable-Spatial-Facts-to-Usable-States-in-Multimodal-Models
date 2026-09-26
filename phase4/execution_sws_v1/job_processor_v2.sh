#!/bin/bash
set -euo pipefail
task_code='./phase4/execution_sws_v1'
task_project='./SpaceConflict'
module load python/gpu/3.12.5
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$task_project/src${PYTHONPATH:+:$PYTHONPATH}"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
export OPENBLAS_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
task_models=(qwen35_4b qwen35_9b qwen35_27b)
exec python -B "$task_code/prepare_smoke.py" --run-id sws_20260909_v1 --seed 20260909 --resume --model "${task_models[$SLURM_ARRAY_TASK_ID]}"
