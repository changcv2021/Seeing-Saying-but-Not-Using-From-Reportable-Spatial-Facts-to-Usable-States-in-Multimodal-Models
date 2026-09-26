#!/usr/bin/env bash
set -euo pipefail
umask 0007
module load python/3.12.11
code='./dataset/research/state_binding_phase_a_v2'
export PYTHONPATH="$code/src:./dataset/src"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"
for phase in build verify report; do
  srun python "$code/src/$phase.py" --config "$code/configs/phase_a.json" --run-id phase_a_20260907_r1 --seed 20260907 --resume
done
