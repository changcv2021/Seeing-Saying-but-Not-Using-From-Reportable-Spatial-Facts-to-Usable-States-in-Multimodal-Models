#!/bin/bash
set -euo pipefail
module load python/gpu/3.12.5
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false
export HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
entry_dir='./phase8/heldout_test_full_pss_v1'
phase8_python='python'
stage="$1"
shift
if [[ "$stage" == summarize ]]; then
    srun --cpu-bind=none "$phase8_python" "$entry_dir/summarize.py" "$@"
else
    if [[ "$stage" == prepare ]]; then
        srun --cpu-bind=none "$phase8_python" -m unittest discover -s "$entry_dir" -p 'test_*.py' -v
    fi
    srun --cpu-bind=none "$phase8_python" "$entry_dir/execute.py" "$stage" "$@"
fi
