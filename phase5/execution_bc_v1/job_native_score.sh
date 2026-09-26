#!/bin/bash
set -euo pipefail
module load python/gpu/3.12.5
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
export OPENBLAS_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
BC_STAGE_CODE='./phase5/execution_bc_v1'
python -B "$BC_STAGE_CODE/native_score.py" --stage normalize "$@"
python -B "$BC_STAGE_CODE/native_score.py" --stage score "$@"
