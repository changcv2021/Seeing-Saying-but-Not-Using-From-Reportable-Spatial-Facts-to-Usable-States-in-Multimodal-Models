#!/usr/bin/env bash
set -euo pipefail
umask 0007
code='./dataset/research/state_binding_phase_a1/core_execution_v3'
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=2
module load python/gpu/3.12.5
source external/scratch/industbench_qwen_family/venv/bin/activate
export PYTHONPATH="$code"
cd "$code"
srun python "$code/publication_v1/publish.py" --config "$code/config.json" --run-id phase_a1_20260907_core_v3 --seed 20260907 --resume
