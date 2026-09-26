#!/bin/bash
set -euo pipefail
task_code='./experiments/spatial_world_state/execution_sws_v1'
task_phase="${1:?freeze or rescore}"
shift
module load python/gpu/3.12.5
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}" OPENBLAS_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
task_python=python
task_args=(--config "$task_code/config_auto_v2.json" --run-id sws_20260909_v1 --seed 20260909 --resume)
if [[ "$task_phase" == rescore ]]; then
  task_cases=(D01 E7 E9 D02 D03 D04 E8 NONCOUNT MULTIVIEW)
  task_models=(qwen35_4b qwen35_9b qwen35_27b)
  task_index="${SLURM_ARRAY_TASK_ID:?array index}"
  task_args+=(--batch "${task_cases[$((task_index / 3))]}" --model "${task_models[$((task_index % 3))]}")
  "$task_python" -B "$task_code/interface_repair_v3/rescore.py" "${task_args[@]}" --stage canonicalize
  exec "$task_python" -B "$task_code/interface_repair_v3/rescore.py" "${task_args[@]}" --stage score
else
  exec "$task_python" -B "$task_code/interface_repair_v3/rescore.py" "${task_args[@]}" --stage "$task_phase" "$@"
fi
