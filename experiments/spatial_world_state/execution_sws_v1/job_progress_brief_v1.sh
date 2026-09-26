#!/bin/bash
set -euo pipefail
task_code='./experiments/spatial_world_state/execution_sws_v1'
module load python/gpu/3.12.5
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
exec python -B "$task_code/progress_brief_v1.py" --config "$task_code/config_auto_v2.json" --run-id sws_20260909_v1 --seed 20260909
