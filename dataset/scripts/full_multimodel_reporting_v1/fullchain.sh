#!/usr/bin/env bash
set -euo pipefail
umask 0007
multi_original='./dataset/scripts/full_multimodel_20260908_v1'
multi_reporting='./dataset/scripts/full_multimodel_reporting_v1'
module load python/gpu/3.12.5
source external/scratch/industbench_qwen_family/venv/bin/activate
export PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=4
export PYTHONPATH="$multi_original:$multi_original/../../src"
export HF_HOME=artifacts/model_cache/hf_home
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
unset SLURM_CPU_BIND SLURM_CPU_BIND_LIST SLURM_CPU_BIND_TYPE SLURM_CPU_BIND_VERBOSE
unset SLURM_MEM_BIND SLURM_MEM_BIND_LIST SLURM_MEM_BIND_TYPE SLURM_MEM_BIND_VERBOSE
multi_key="$1"
python "$multi_original/node.py" full "$multi_key"
python "$multi_original/node.py" full_judge "$multi_key"
python "$multi_original/campaign.py" final --model "$multi_key" --run-id full_multimodel_20260908_v1 --seed 20260904 --resume
python "$multi_reporting/report.py" --model "$multi_key" --run-id full_multimodel_20260908_v1 --seed 20260904 --resume
python "$multi_original/summary.py" --run-id full_multimodel_20260908_v1 --seed 20260904 --resume
