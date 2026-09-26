#!/bin/bash
set -euo pipefail
task_code='./experiments/spatial_world_state/execution_sws_v1'
task_name="${1:?Specify a new versioned CPU module}"
# Frozen historical producers must not be rerun into their old output paths.
case "$task_name" in
  activate_review_policy_v2) ;;
  *) echo 'Module not registered for this versioned entry; preserve historical workers.' >&2; exit 2 ;;
esac
module load python/gpu/3.12.5
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
export OPENBLAS_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
exec python -B "$task_code/$task_name.py" \
  --config "$task_code/config_auto_v2.json" --run-id sws_20260909_v1 --seed 20260909 --resume
