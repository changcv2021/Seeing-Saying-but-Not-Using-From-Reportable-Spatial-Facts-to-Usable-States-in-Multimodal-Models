#!/bin/bash
set -euo pipefail
umask 077
module load python/gpu/3.12.5
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
runner='./dataset/scripts/azure_claude_opus47_20260920_v1/run.py'
interpreter=python
"$interpreter" -B "$runner" freeze --resume
rc=0
"$interpreter" -B "$runner" infer --resume || rc=$?
unset SPACECONFLICT_CLAUDE_API_KEY SPACECONFLICT_AZURE_API_KEY
"$interpreter" -B "$runner" score --resume
exit "$rc"
