#!/bin/bash
set -euo pipefail
module load python/gpu/3.12.5
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}" OPENBLAS_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
task_code='./experiments/spatial_world_state/execution_sws_v1/m2_repair_v1'
task_python='python'
stage="${1:?prepare or pilot or coarse}"
shift
if [[ "$stage" == prepare ]]; then
 exec "$task_python" -B "$task_code/prepare.py" --resume "$@"
fi
exec "$task_python" -B "$task_code/worker.py" --mode "$stage" --shard "${SLURM_ARRAY_TASK_ID:?array required}" --resume "$@"
