#!/usr/bin/env bash
set -euo pipefail
umask 0007
b0_code='./SpaceConflict/research/spaceconflict_b0_launchfix_v1'
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"
module load python/gpu/3.12.5
source external/scratch/industbench_qwen_family/venv/bin/activate
cd "$b0_code"
b0_action="$1"
shift
unset SLURM_CPU_BIND SLURM_CPU_BIND_LIST SLURM_CPU_BIND_TYPE SLURM_CPU_BIND_VERBOSE
unset SLURM_MEM_BIND SLURM_MEM_BIND_LIST SLURM_MEM_BIND_TYPE SLURM_MEM_BIND_VERBOSE
srun --cpu-bind=cores python "$b0_code/${b0_action}.py" --config "$b0_code/config.json" --run-id b0_20260908_r1_launchfix1 --seed 20260908 --resume "$@"
