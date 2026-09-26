#!/usr/bin/env bash
set -euo pipefail
umask 0007
code='./SpaceConflict/research/state_binding_phase_a1/core_execution_v3'
project='./SpaceConflict'
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=2 TOKENIZERS_PARALLELISM=false
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
module load python/gpu/3.12.5
source external/scratch/industbench_qwen_family/venv/bin/activate
export PYTHONPATH="$code:$project/src"
cd "$code"
srun python "$code/review_gate_v3.py" --config "$code/config.json" --run-id phase_a1_20260907_core_v3 --seed 20260907 --resume "$@"
