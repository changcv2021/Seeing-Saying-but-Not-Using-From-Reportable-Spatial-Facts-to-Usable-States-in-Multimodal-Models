#!/usr/bin/env bash
set -euo pipefail
umask 0007
stage=$1
code='./SpaceConflict/research/state_binding_phase_a1/core_execution_v3'
project='./SpaceConflict'
analysis="$code/analysis_v1"
export PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=2
module load python/gpu/3.12.5
source external/scratch/industbench_qwen_family/venv/bin/activate
export PYTHONPATH="$analysis:$code:$project/src"
cd "$analysis"
case "$stage" in
  lock)
    srun python -m unittest test_analysis -v
    srun python "$analysis/analyze.py" --config "$code/config.json" --run-id phase_a1_20260907_core_v3 --seed 20260907 --resume --lock-only
    ;;
  analyze)
    srun python "$analysis/analyze.py" --config "$code/config.json" --run-id phase_a1_20260907_core_v3 --seed 20260907 --resume
    ;;
  *) exit 2 ;;
esac
