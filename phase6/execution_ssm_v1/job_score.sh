#!/bin/bash
set -euo pipefail
module load python/gpu/3.12.5
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}" OPENBLAS_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
task_code='./phase6/execution_ssm_v1/score.py'
task_python=python
"$task_python" -B "$task_code" --resume --stage normalize "$@"
exec "$task_python" -B "$task_code" --resume --stage score "$@"
