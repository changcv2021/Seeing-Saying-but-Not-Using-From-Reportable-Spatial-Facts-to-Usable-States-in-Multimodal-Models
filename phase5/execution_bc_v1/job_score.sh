#!/bin/bash
set -euo pipefail
module load python/gpu/3.12.5
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}" OPENBLAS_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
task_code='./phase5/execution_bc_v1/content_score.py'
task_python=python
"$task_python" -B "$task_code" --stage normalize --resume "$@"
exec "$task_python" -B "$task_code" --stage score --resume "$@"
