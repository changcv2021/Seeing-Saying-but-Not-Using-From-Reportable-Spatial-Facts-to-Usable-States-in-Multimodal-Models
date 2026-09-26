#!/bin/bash
set -euo pipefail
module load python/gpu/3.12.5
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false
export HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
preserved_code='./phase8/pss_full_l4_preserved_v1'
preserved_python='python'
stage="$1"
shift
case "$stage" in
  freeze)
    srun --cpu-bind=none "$preserved_python" -m unittest discover -s "$preserved_code" -p 'test_*.py' -v
    srun --cpu-bind=none "$preserved_python" "$preserved_code/freeze.py"
    "$preserved_python" "$preserved_code/control.py" admit
    ;;
  finish)
    srun --cpu-bind=none "$preserved_python" "$preserved_code/finish.py" "$@"
    ;;
  infer)
    srun --cpu-bind=none --kill-on-bad-exit=1 "$preserved_python" "$preserved_code/evaluate.py" infer "$@"
    ;;
  score)
    srun --cpu-bind=none "$preserved_python" "$preserved_code/evaluate.py" score "$@"
    srun --cpu-bind=none "$preserved_python" "$preserved_code/report.py"
    ;;
  *) exit 2 ;;
esac
