#!/usr/bin/env bash
set -euo pipefail
umask 0007
module load python/gpu/3.12.5
source external/scratch/industbench_qwen_family/venv/bin/activate
export PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}" OPENBLAS_NUM_THREADS=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
unset SLURM_CPU_BIND SLURM_CPU_BIND_LIST SLURM_CPU_BIND_TYPE SLURM_CPU_BIND_VERBOSE
unset SLURM_MEM_BIND SLURM_MEM_BIND_LIST SLURM_MEM_BIND_TYPE SLURM_MEM_BIND_VERBOSE
q368_code='./dataset/scripts/qwen36_38_20260920_v1'
if [[ "$1" == full ]]; then
    exec python -B "$q368_code/run.py" "$@" --shard-index "$SLURM_ARRAY_TASK_ID" --resume
else
    exec python -B "$q368_code/run.py" "$@" --resume
fi
