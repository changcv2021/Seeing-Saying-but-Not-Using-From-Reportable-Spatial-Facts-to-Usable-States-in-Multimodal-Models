#!/usr/bin/env bash
set -euo pipefail
umask 0007
split_code='./dataset/scripts/full_multimodel_split_v3'
split_original='./dataset/scripts/full_multimodel_20260908_v1'
module load python/gpu/3.12.5
source external/scratch/industbench_qwen_family/venv/bin/activate
export PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"
export PYTHONPATH="$split_original:$split_original/../../src"
export HF_HOME=artifacts/model_cache/hf_home
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
unset SLURM_CPU_BIND SLURM_CPU_BIND_LIST SLURM_CPU_BIND_TYPE SLURM_CPU_BIND_VERBOSE
unset SLURM_MEM_BIND SLURM_MEM_BIND_LIST SLURM_MEM_BIND_TYPE SLURM_MEM_BIND_VERBOSE
cd "$split_code"
split_action="$1"
case "$split_action" in
validate) python tests.py --run-id full_multimodel_20260908_v1 --seed 20260904 --resume ;;
controller) exec python controller.py --run-id full_multimodel_20260908_v1 --seed 20260904 --resume ;;
candidate|judge) exec python worker.py "$split_action" --model "$2" --run-id full_multimodel_20260908_v1 --seed 20260904 --resume ;;
handoff|finish) python orchestration.py "$split_action" --model "$2" --run-id full_multimodel_20260908_v1 --seed 20260904 --resume ;;
*) exit 2 ;;
esac
