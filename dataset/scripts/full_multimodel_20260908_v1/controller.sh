#!/usr/bin/env bash
set -euo pipefail
multi_code='./dataset/scripts/full_multimodel_20260908_v1'
module load python/gpu/3.12.5
source external/scratch/industbench_qwen_family/venv/bin/activate
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1
export PYTHONPATH="$multi_code:$multi_code/../../src"
unset SLURM_CPU_BIND SLURM_CPU_BIND_LIST SLURM_CPU_BIND_TYPE SLURM_CPU_BIND_VERBOSE
unset SLURM_MEM_BIND SLURM_MEM_BIND_LIST SLURM_MEM_BIND_TYPE SLURM_MEM_BIND_VERBOSE
cd "$multi_code"
python controller.py --run-id full_multimodel_20260908_v1 --seed 20260904 --resume
