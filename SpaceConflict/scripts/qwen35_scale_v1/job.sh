#!/usr/bin/env bash
set -euo pipefail
umask 0007
phase=$1
campaign=$2
key=${3:-none}
code="$campaign/code"
run="$campaign/$key"
run_id="$(basename "$campaign")_$key"
export PYTHONPATH="$code:artifacts/software/src"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
export TOKENIZERS_PARALLELISM=false HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
if [[ "$phase" == prepare || "$phase" == compare || "$phase" == score || "$phase" == final ]]; then
  module load python/3.12.11
else
  module load python/gpu/3.12.5
  if [[ "$phase" == judge || "$phase" == smoke_judge ]]; then
    source external/scratch/industbench_qwen35_judge/venv/bin/activate
  else
    source external/scratch/industbench_qwen_family/venv/bin/activate
  fi
  nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
fi
case "$phase" in
prepare)
  python "$code/test_scale.py"
  srun python "$code/manage.py" prepare --run-root "$campaign" --run-id "$(basename "$campaign")" --seed 20260904 --resume
  ;;
compare)
  srun python "$code/manage.py" compare --run-root "$campaign" --run-id "$(basename "$campaign")" --seed 20260904 --resume
  ;;
smoke|infer)
  scope=full;count=16;shard=${SLURM_ARRAY_TASK_ID:-0}
  if [[ "$phase" == smoke ]]; then scope=smoke;count=1;shard=0;fi
  srun python "$code/infer_scale.py" --run-root "$run" --run-id "$run_id" --scope "$scope" --num-shards "$count" --shard-index "$shard" --seed 20260904 --resume
  if [[ "$phase" == smoke ]];then python "$code/score.py" --run-root "$run" --run-id "$run_id" --scope smoke --gate;fi
  ;;
judge|smoke_judge)
  scope=full;count=8;shard=${SLURM_ARRAY_TASK_ID:-0}
  if [[ "$phase" == smoke_judge ]]; then scope=smoke;count=1;shard=0;fi
  srun python "$code/judge.py" --run-root "$run" --run-id "$run_id" --scope "$scope" --num-shards "$count" --shard-index "$shard" --seed 20260904 --resume
  if [[ "$phase" == smoke_judge ]];then python "$code/score.py" --run-root "$run" --run-id "$run_id" --scope smoke --gate;fi
  ;;
score|final)
  srun python "$code/score.py" --run-root "$run" --run-id "$run_id" --scope full --seed 20260904 --resume
  ;;
*) exit 2;;
esac
