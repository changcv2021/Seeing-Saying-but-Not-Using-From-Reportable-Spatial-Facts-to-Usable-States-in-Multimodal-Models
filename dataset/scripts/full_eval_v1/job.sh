#!/usr/bin/env bash
set -euo pipefail
umask 0007
phase=$1
run=${2:-artifacts/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v1_20260904}
bundle=artifacts
project='./dataset'
code="$run/code"
run_id=$(basename "$run")
export PYTHONPATH="$bundle/software/src"
export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
cd "$bundle"
if [[ "$phase" == prepare || "$phase" == score || "$phase" == final ]]; then
  module load python/3.12.11
else
  module load python/gpu/3.12.5
fi
case "$phase" in
prepare)
  python "$code/test_protocol.py"
  extra=()
  if [[ -f "$run/media_integration_config.json" ]]; then
    python "$code/test_scan_integration.py"
    extra+=(--spar-assets "$(jq -r .assets "$run/media_integration_config.json")")
    extra+=(--checkpoint-source "$(jq -r .checkpoint_source "$run/media_integration_config.json")")
  fi
  python "$code/prepare.py" --bundle "$bundle" --project "$project" --run-root "$run" --run-id "$run_id" --seed 20260904 --resume "${extra[@]}"
  ;;
smoke|infer)
  source external/scratch/industbench_qwen25vl7b/venv/bin/activate
  export HF_HOME=external/scratch/industbench_qwen25vl7b/hf_home
  nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
  if [[ "$phase" == smoke ]]; then
    request=smoke.jsonl; scope=smoke; shard=0; count=1
  else
    request=requests.jsonl; scope=full; shard=$SLURM_ARRAY_TASK_ID; count=8
  fi
  mkdir -p "$run/$scope"
  srun python "$code/infer.py" --requested-samples "$run/$request" \
    --output "$run/$scope/predictions_$(printf '%03d' "$shard").jsonl" \
    --run-id "$run_id" --num-shards "$count" --shard-index "$shard" --seed 20260904 \
    --max-new-tokens 256 --video-frames 16 --resume
  if [[ "$phase" == smoke ]]; then
    python "$code/score.py" --run-root "$run" --run-id "$run_id" --scope smoke --gate
    deactivate
    source external/scratch/industbench_qwen35_judge/venv/bin/activate
    export HF_HOME=external/scratch/industbench_qwen35_judge/hf_home
    srun python "$code/judge.py" --run-root "$run" --run-id "$run_id" --scope smoke --resume
    python "$code/score.py" --run-root "$run" --run-id "$run_id" --scope smoke --gate
  fi
  ;;
judge)
  source external/scratch/industbench_qwen35_judge/venv/bin/activate
  export HF_HOME=external/scratch/industbench_qwen35_judge/hf_home
  srun python "$code/judge.py" --run-root "$run" --run-id "$run_id" --scope full --num-shards 8 --shard-index "$SLURM_ARRAY_TASK_ID" --resume
  ;;
score|final)
  python "$code/score.py" --run-root "$run" --run-id "$run_id" --scope full --resume
  ;;
*) echo "Unknown phase: $phase" >&2; exit 2;;
esac
