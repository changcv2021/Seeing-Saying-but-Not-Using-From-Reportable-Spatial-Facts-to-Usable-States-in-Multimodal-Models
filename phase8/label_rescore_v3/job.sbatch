#!/bin/bash
# CPU-only, resources supplied explicitly by sbatch.
set -euo pipefail
module load python/gpu/3.12.5
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 HF_HUB_OFFLINE=1
rescore_code='./phase8/label_rescore_v3'
rescore_python='python'
if [[ "$1" == freeze ]]; then
    "$rescore_python" -m unittest discover -s "$rescore_code" -p 'test_*.py' -v
fi
# Direct execution on the assigned CPU batch node avoids inherited GPU srun selectors.
exec "$rescore_python" "$rescore_code/run_v3.py" "$@"
