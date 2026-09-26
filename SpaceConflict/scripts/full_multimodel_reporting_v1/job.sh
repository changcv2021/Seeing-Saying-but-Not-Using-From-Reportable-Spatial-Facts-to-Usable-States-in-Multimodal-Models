#!/usr/bin/env bash
set -euo pipefail
multi_original='./SpaceConflict/scripts/full_multimodel_20260908_v1'
multi_reporting='./SpaceConflict/scripts/full_multimodel_reporting_v1'
module load python/gpu/3.12.5
source external/scratch/industbench_qwen_family/venv/bin/activate
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 PYTHONPATH="$multi_original:$multi_original/../../src"
unset SLURM_CPU_BIND SLURM_CPU_BIND_LIST SLURM_CPU_BIND_TYPE SLURM_CPU_BIND_VERBOSE
unset SLURM_MEM_BIND SLURM_MEM_BIND_LIST SLURM_MEM_BIND_TYPE SLURM_MEM_BIND_VERBOSE
if [[ "${1:-controller}" == validate ]]; then
  python "$multi_reporting/report.py" --validate-extension --run-id full_multimodel_20260908_v1 --seed 20260904 --resume
else
  python "$multi_reporting/coordinator.py" --run-id full_multimodel_20260908_v1 --seed 20260904 --resume
fi
