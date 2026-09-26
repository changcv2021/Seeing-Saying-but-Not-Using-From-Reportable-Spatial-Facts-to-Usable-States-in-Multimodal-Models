#!/bin/bash
# Resource parameters and logs are provided explicitly at submission.
set -euo pipefail
module load python/gpu/3.12.5
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false HF_HUB_OFFLINE=1
task_code='./phase8/label_rescore_v2'
task_python='python'
stage="$1"
shift
if [[ "$stage" == prepare ]]; then
    srun --cpu-bind=none "$task_python" -m unittest discover -s "$task_code" -p 'test_*.py' -v
fi
srun --cpu-bind=none "$task_python" "$task_code/run.py" "$stage" "$@"
