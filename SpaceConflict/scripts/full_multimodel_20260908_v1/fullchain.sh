#!/usr/bin/env bash
set -euo pipefail
umask 0007
multi_code='./SpaceConflict/scripts/full_multimodel_20260908_v1'
module load python/gpu/3.12.5
source external/scratch/industbench_qwen_family/venv/bin/activate
export PYTHONPATH="$multi_code:$multi_code/../../src"
export PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=4
export HF_HOME=artifacts/model_cache/hf_home
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
unset SLURM_CPU_BIND SLURM_CPU_BIND_LIST SLURM_CPU_BIND_TYPE SLURM_CPU_BIND_VERBOSE
unset SLURM_MEM_BIND SLURM_MEM_BIND_LIST SLURM_MEM_BIND_TYPE SLURM_MEM_BIND_VERBOSE
multi_model="$1"
cd "$multi_code"
python node.py full "$multi_model"
python node.py full_judge "$multi_model"
python campaign.py final --model "$multi_model" --run-id full_multimodel_20260908_v1 --seed 20260904 --resume
python summary.py --run-id full_multimodel_20260908_v1 --seed 20260904 --resume
