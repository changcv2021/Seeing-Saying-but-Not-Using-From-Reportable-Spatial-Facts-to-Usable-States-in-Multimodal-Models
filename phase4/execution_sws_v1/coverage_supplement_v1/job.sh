#!/bin/bash
set -euo pipefail
task_code='./phase4/execution_sws_v1/coverage_supplement_v1'
task_python=python
module load python/gpu/3.12.5
export PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}" OPENBLAS_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
task_phase="${1:?compile or runner or rescore}"
shift
if [[ "$task_phase" == rescore ]]; then
  "$task_python" -B "$task_code/runner.py" --resume --stage canonicalize "$@"
  exec "$task_python" -B "$task_code/runner.py" --resume --stage score "$@"
else
  exec "$task_python" -B "$task_code/$task_phase.py" --resume "$@"
fi
