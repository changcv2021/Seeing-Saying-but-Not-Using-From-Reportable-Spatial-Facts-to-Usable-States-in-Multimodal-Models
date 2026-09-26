#!/bin/bash
set -euo pipefail
umask 077
module load python/gpu/3.12.5
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
recovery_python=python
recovery_code='./SpaceConflict/scripts/evaluation_recovery_20260921_v1/api_recovery.py'
rc=0
if [[ "$1" == gpt54 ]]; then
    unset SPACECONFLICT_CLAUDE_API_KEY
    "$recovery_python" -B "$recovery_code" batch-control --resume || rc=$?
    unset SPACECONFLICT_AZURE_API_KEY
    "$recovery_python" -B "$recovery_code" batch-score --resume
elif [[ "$1" == claude ]]; then
    unset SPACECONFLICT_AZURE_API_KEY
    "$recovery_python" -B "$recovery_code" claude-prepare --resume
    "$recovery_python" -B "$recovery_code" claude-infer --resume || rc=$?
    unset SPACECONFLICT_CLAUDE_API_KEY
    "$recovery_python" -B "$recovery_code" claude-score --resume
else
    exit 2
fi
exit "$rc"
