#!/usr/bin/env bash
set -euo pipefail
umask 0007
b0_code='./SpaceConflict/research/spaceconflict_b0'
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"
module load python/gpu/3.12.5
source external/scratch/industbench_qwen_family/venv/bin/activate
cd "$b0_code"
b0_action="$1"
shift
srun python "$b0_code/${b0_action}.py" --config "$b0_code/config.json" --run-id b0_20260908_r1 --seed 20260908 --resume "$@"
