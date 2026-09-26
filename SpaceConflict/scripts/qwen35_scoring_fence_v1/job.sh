#!/usr/bin/env bash
set -euo pipefail
umask 0007
phase=$1
root=$2
key=${3:-shared}
code="$root/code"
export PYTHONPATH="$code"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
export TOKENIZERS_PARALLELISM=false HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
if [[ "$phase" == judge || "$phase" == smoke_judge ]];then
  module load python/gpu/3.12.5
  source external/scratch/industbench_qwen35_judge/venv/bin/activate
else
  module load python/3.12.11
fi
if [[ "$phase" == prepare || "$phase" == compare ]];then
  if [[ "$phase" == prepare ]];then python "$code/test_fences.py";fi
  srun python "$code/repair_manage.py" "$phase" --run-root "$root" --run-id qwen35_scale_512_fence_v1_20260906 --seed 20260904 --resume
else
  run="$root/$key"
  model_run_id=$(jq -r .run_id "$run/config.json")
  if [[ "$phase" == judge || "$phase" == smoke_judge ]];then
    scope=full;count=8;shard=${SLURM_ARRAY_TASK_ID:-0}
    if [[ "$phase" == smoke_judge ]];then scope=smoke;count=1;shard=0;fi
    srun python "$code/judge.py" --run-root "$run" --run-id "$model_run_id" --scope "$scope" --num-shards "$count" --shard-index "$shard" --seed 20260904 --resume
    if [[ "$phase" == smoke_judge ]];then python "$code/score.py" --run-root "$run" --run-id "$model_run_id" --scope smoke --gate --seed 20260904 --resume;fi
  elif [[ "$phase" == score || "$phase" == final ]];then
    srun python "$code/score.py" --run-root "$run" --run-id "$model_run_id" --scope full --seed 20260904 --resume
  else exit 2;fi
fi
