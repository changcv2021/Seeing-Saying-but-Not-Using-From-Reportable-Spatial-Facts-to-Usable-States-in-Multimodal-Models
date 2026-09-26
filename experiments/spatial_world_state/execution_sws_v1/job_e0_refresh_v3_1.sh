#!/bin/bash
set -euo pipefail
task_code='./experiments/spatial_world_state/execution_sws_v1'
module load python/gpu/3.12.5
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:?CPU Slurm allocation required}"
export OPENBLAS_NUM_THREADS="$OMP_NUM_THREADS"
task_python=python
task_args=(--config "$task_code/config_auto_v2.json" --run-id sws_20260909_v1 --seed 20260909 --resume)
if [[ "${1:-}" == --verify ]]; then
  exec "$task_python" -B "$task_code/e0_refresh_v3_1.py" "${task_args[@]}" --verify
fi
"$task_python" -B "$task_code/e0_refresh_v3_1.py" "${task_args[@]}"
exec "$task_python" -B "$task_code/e0_refresh_v3_1.py" "${task_args[@]}" --verify
