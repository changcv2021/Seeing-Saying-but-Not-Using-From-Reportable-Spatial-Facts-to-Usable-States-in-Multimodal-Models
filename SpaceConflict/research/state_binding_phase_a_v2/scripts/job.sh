#!/usr/bin/env bash
set -euo pipefail
umask 0007
phase=$1
config=$2
code='./SpaceConflict/research/state_binding_phase_a_v2'
export PYTHONPATH="$code/src:./SpaceConflict/src"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"
export TOKENIZERS_PARALLELISM=false HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
if [[ "$phase" == measure || "$phase" == smoke || "$phase" == run ]]; then
  module load python/gpu/3.12.5
  source external/scratch/industbench_qwen_family/venv/bin/activate
  srun python "$code/src/run.py" --config "$config" --run-id phase_a_20260907_r1 --seed 20260907 --resume --phase "$phase" --model "$3"
else
  module load python/3.12.11
  srun python "$code/src/$phase.py" --config "$config" --run-id phase_a_20260907_r1 --seed 20260907 --resume
fi
