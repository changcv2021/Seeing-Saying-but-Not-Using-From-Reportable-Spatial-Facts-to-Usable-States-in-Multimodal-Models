#!/bin/bash
set -euo pipefail
module load python/3.12.11
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
exec python -B './experiments/spatial_world_state/execution_sws_v1/breadth_v1/compile_mv_v2.py' --resume
