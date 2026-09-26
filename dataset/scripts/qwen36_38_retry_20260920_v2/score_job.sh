#!/usr/bin/env bash
set -euo pipefail
umask 0007
module load python/gpu/3.12.5
source external/scratch/industbench_qwen_family/venv/bin/activate
export PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}" OPENBLAS_NUM_THREADS=1
exec python -B './dataset/scripts/qwen36_38_retry_20260920_v2/retry.py' score "$@"
