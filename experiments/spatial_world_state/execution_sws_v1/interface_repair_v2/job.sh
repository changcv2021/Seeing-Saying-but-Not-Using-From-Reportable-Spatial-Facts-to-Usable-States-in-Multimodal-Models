#!/bin/bash
set -euo pipefail
task_code='./experiments/spatial_world_state/execution_sws_v1'
task_phase="${1:?freeze, rescore, or summary}"
shift
module load python/gpu/3.12.5
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
export OPENBLAS_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
task_python=python
task_args=(--config "$task_code/config_auto_v2.json" --run-id sws_20260909_v1 --seed 20260909 --resume)
case "$task_phase" in
 freeze|summary)
  exec "$task_python" -B "$task_code/interface_repair_v2/rescore.py" "${task_args[@]}" --stage "$task_phase" "$@" ;;
 rescore)
  "$task_python" -B "$task_code/interface_repair_v2/rescore.py" "${task_args[@]}" --stage canonicalize "$@"
  exec "$task_python" -B "$task_code/interface_repair_v2/rescore.py" "${task_args[@]}" --stage score "$@" ;;
 *) exit 2 ;;
esac
