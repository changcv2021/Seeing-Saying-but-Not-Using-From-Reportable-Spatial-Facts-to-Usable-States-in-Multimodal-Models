#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --signal=USR1@120
set -euo pipefail

# Resource flags are supplied by sbatch CLI, not interpolated in #SBATCH lines.
# Codex must implement/adapt the worker module in the real repository first.
if [[ $# -ne 4 ]]; then
  echo "usage: $0 REPO_ROOT RUN_ROOT MODEL_ID SHARD_TABLE" >&2
  exit 2
fi
REPO_ROOT=$1
RUN_ROOT=$2
MODEL_ID=$3
SHARD_TABLE=$4
: "${SLURM_ARRAY_TASK_ID:?Must run as a Slurm array task}"
cd "$REPO_ROOT"

# Reuse the already-validated module/venv setup from B0. Never install packages
# or download all weights independently in every array worker.
# The worker must handle SIGUSR1, atomic writes, safe bundle checkpoints,
# and first-retained-response idempotency. No answer-based retry is permitted.
exec srun python -m spatial_world_state_study.worker \
  --run-root "$RUN_ROOT" \
  --model-id "$MODEL_ID" \
  --shard-table "$SHARD_TABLE" \
  --shard-index "$SLURM_ARRAY_TASK_ID" \
  --resume-first-retained-only
