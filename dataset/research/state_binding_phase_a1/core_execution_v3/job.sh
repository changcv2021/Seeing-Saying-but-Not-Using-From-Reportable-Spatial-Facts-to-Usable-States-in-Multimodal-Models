#!/usr/bin/env bash
set -euo pipefail
umask 0007
task=$1
code='./dataset/research/state_binding_phase_a1/core_execution_v3'
project='./dataset'
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"
export TOKENIZERS_PARALLELISM=false HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
module load python/gpu/3.12.5
source external/scratch/industbench_qwen_family/venv/bin/activate
export PYTHONPATH="$code:$project/src"
cd "$code"
common=(--config "$code/config.json" --run-id phase_a1_20260907_core_v3 --seed 20260907 --resume)
case "$task" in
  prepare)
    srun python "$code/prepare_v3.py" "${common[@]}"
    srun python "$code/review_v3.py" "${common[@]}"
    srun python "$code/status_v3.py" "${common[@]}"
    ;;
  precore|core)
    model=$2
    srun python "$code/infer_v3.py" "${common[@]}" --stage "$task" --model "$model"
    ;;
  status|freeze)
    srun python "$code/${task}_v3.py" "${common[@]}"
    ;;
  *) printf 'Unsupported task: %s\n' "$task" >&2; exit 2 ;;
esac
