#!/usr/bin/env bash
# Infrastructure-only repair. Frozen inference/config/scorer are unchanged.
set -euo pipefail
umask 0007
task=$1
code='./SpaceConflict/research/state_binding_phase_a1'
project='./SpaceConflict'
config="$code/configs/a1.json"
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"
export TOKENIZERS_PARALLELISM=false HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
if [[ "$task" == infer || "$task" == present || "$task" == launcher_preflight_v3 ]]; then
  module load python/gpu/3.12.5
  source external/scratch/industbench_qwen_family/venv/bin/activate
else
  module load python/3.12.11
fi
export PYTHONPATH="$code/src:$project/src"
shift
srun python "$code/src/$task.py" --config "$config" --run-id phase_a1_20260907_r1 --seed 20260907 --resume "$@"
