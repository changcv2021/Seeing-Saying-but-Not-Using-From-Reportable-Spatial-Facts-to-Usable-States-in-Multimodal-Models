#!/usr/bin/env bash
set -euo pipefail
umask 0007
direct_code='./SpaceConflict/scripts/qwen25vl32_direct_full_v1'
module load python/gpu/3.12.5
source external/scratch/industbench_qwen_family/venv/bin/activate
export PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"
exec python "$direct_code/prepare.py" --run-id full_multimodel_20260908_v1 --seed 20260904 --resume "$@"
