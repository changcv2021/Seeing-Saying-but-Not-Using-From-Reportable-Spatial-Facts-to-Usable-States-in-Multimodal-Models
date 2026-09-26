#!/bin/bash
set -euo pipefail
task_code='./phase4/execution_sws_v1/data_continuation_v1'
task_project='./SpaceConflict'
task_python='python'
module load python/gpu/3.12.5
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$task_project/src${PYTHONPATH:+:$PYTHONPATH}"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
export OPENBLAS_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
task_phase="${1:?prepare, audit, processor, infer, freeze_score, or rescore}"
shift
case "$task_phase" in
 prepare) exec "$task_python" -B "$task_code/prepare.py" --resume "$@" ;;
 audit) exec "$task_python" -B "$task_code/native_audit.py" --resume "$@" ;;
 processor|infer|freeze_score) exec "$task_python" -B "$task_code/runner.py" --stage "$task_phase" --resume "$@" ;;
 rescore)
  "$task_python" -B "$task_code/runner.py" --stage canonicalize --resume "$@"
  exec "$task_python" -B "$task_code/runner.py" --stage score --resume "$@"
  ;;
 *) exit 2 ;;
esac
