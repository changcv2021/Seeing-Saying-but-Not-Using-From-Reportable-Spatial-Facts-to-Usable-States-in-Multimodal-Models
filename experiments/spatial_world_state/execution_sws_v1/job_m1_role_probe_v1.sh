#!/bin/bash
set -euo pipefail
module load python/gpu/3.12.5
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}" OPENBLAS_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
exec python -B './experiments/spatial_world_state/execution_sws_v1/m1_role_probe_v1.py' --resume
