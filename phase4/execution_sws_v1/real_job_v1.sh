#!/bin/bash
set -euo pipefail
task_code='./phase4/execution_sws_v1'
task_project='./SpaceConflict'
task_phase="${1:?compile, processor, infer, or score}"
shift
module load python/gpu/3.12.5
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$task_project/src${PYTHONPATH:+:$PYTHONPATH}"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
export OPENBLAS_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
case "$task_phase" in
 compile) task_module=real_compile_v1 ;;
 processor) task_module=real_processor_v1 ;;
 infer) task_module=real_worker_v1 ;;
 score) task_module=real_score_v1 ;;
 *) exit 2 ;;
esac
exec python -B "$task_code/$task_module.py" \
  --config "$task_code/config_auto_v2.json" --run-id sws_20260909_v1 --seed 20260909 --resume "$@"
