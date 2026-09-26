#!/bin/bash
set -euo pipefail
umask 077
module load python/gpu/3.12.5
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
runner='./dataset/scripts/azure_gpt54_batch_20260920_v1/batch.py'
interpreter=python
if [[ "$1" == prepare ]]; then unset SPACECONFLICT_AZURE_API_KEY; fi
rc=0
"$interpreter" -B "$runner" "$1" --resume || rc=$?
if [[ "$1" == control ]]; then
    unset SPACECONFLICT_AZURE_API_KEY
    "$interpreter" -B "$runner" score --resume
fi
exit "$rc"
