#!/bin/bash
set -euo pipefail
task_code='./experiments/spatial_world_state/execution_sws_v1/breadth_v1'
task_python='python'
module load python/gpu/3.12.5
export PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
export OPENBLAS_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
task_stage="${1:?stage}"
shift
exec "$task_python" -B "$task_code/$task_stage.py" --resume "$@"
