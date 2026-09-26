#!/bin/bash
set -euo pipefail
task_code='./phase4/execution_sws_v1'
task_project='./SpaceConflict'
task_module="${1:?versioned module required}"
shift
case "$task_module" in continuation_audit_v1|e7_compile_v1|e7_processor_v1|e7_worker_v1|e7_score_v1|m1_compile_v1|m1_worker_v1|m1_collect_v1) ;; *) exit 2 ;; esac
module load python/gpu/3.12.5
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$task_project/src${PYTHONPATH:+:$PYTHONPATH}"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
export OPENBLAS_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
exec python -B "$task_code/$task_module.py" \
  --config "$task_code/config_auto_v2.json" --run-id sws_20260909_v1 --seed 20260909 --resume "$@"
