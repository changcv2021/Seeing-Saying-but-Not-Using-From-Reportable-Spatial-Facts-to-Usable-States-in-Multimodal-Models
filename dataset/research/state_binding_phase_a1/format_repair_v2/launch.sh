#!/usr/bin/env bash
set -euo pipefail
umask 0007
task=$1
a1='./dataset/research/state_binding_phase_a1'
repair='./dataset/research/state_binding_phase_a1/format_repair_v2'
project='./dataset'
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"
export TOKENIZERS_PARALLELISM=false HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
if [[ "$task" == present ]]; then
  module load python/gpu/3.12.5
  source external/scratch/industbench_qwen_family/venv/bin/activate
else
  module load python/3.12.11
fi
export PYTHONPATH="$repair:$a1/src:$project/src"
shift
case "$task" in
  repair|review_status|present) program="$repair/$task.py" ;;
  prepare_review) program="$a1/src/$task.py" ;;
  *) printf 'Unsupported task: %s\n' "$task" >&2; exit 2 ;;
esac
srun python "$program" --config "$repair/config.json" --run-id phase_a1_20260907_format_v2 --seed 20260907 --resume "$@"
