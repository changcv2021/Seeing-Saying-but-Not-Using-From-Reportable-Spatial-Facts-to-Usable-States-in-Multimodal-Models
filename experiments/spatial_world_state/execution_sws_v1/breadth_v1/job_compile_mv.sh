#!/bin/bash
set -euo pipefail
# The source-proof compiler uses the supported CPU module's jsonschema/PyYAML.
# The already-running GPU environment is neither changed nor installed into.
module load python/3.12.11
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
exec python -B './experiments/spatial_world_state/execution_sws_v1/breadth_v1/compile_mv.py' --resume
