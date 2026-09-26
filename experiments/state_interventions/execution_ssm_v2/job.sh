#!/bin/bash
set -euo pipefail
module load python/gpu/3.12.5
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}" OPENBLAS_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
task_code='./experiments/state_interventions/execution_ssm_v2'
exec python -B "$task_code/${1:?script name}.py" --resume "${@:2}"
