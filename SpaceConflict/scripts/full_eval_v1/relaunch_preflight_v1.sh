#!/usr/bin/env bash
set -euo pipefail
umask 0007
run=$1
module load python/3.12.11
export PYTHONPATH="$run/code:artifacts/software/src"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
python "$run/code/test_protocol.py"
python "$run/code/test_scan_integration.py"
srun python "$run/code_relaunch_20260905/preflight_relaunch_v1.py" \
  --run-root "$run" --run-id "$(basename "$run")" --seed 20260904 --resume
