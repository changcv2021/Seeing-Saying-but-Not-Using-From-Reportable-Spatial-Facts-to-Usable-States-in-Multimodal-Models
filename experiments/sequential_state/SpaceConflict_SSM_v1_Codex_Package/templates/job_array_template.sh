#!/usr/bin/env bash
# TEMPLATE ONLY. Supply actual institution SBATCH resource options at submission.
# Example interface for the runner Codex must implement; this is not that runner.
set -euo pipefail
: "${SSM_RUN_DIR:?Set an isolated run directory}"
: "${SSM_PYTHON:?Set the frozen environment python executable}"
: "${SSM_STAGE_RUNNER:?Set the implemented and validated stage runner path}"
: "${SSM_STAGE:?Set stage name}"
: "${SSM_MODEL:?Set checkpoint alias or NONE for CPU}"
: "${SLURM_ARRAY_TASK_ID:?Use a frozen task-to-shard manifest}"
[[ -f "$SSM_STAGE_RUNNER" ]] || { echo 'Missing implemented runner' >&2; exit 2; }
[[ -f "$SSM_RUN_DIR/RESOURCE_PLAN.json" ]] || { echo 'Missing resource lock' >&2; exit 2; }
[[ -f "$SSM_RUN_DIR/PROTOCOL_LOCK.json" ]] || { echo 'Missing protocol lock' >&2; exit 2; }
# Runner must verify semantic gate status and lock hashes, not just file existence.
# No sleep/polling loop on an allocated GPU; no answer-dependent retries.
exec "$SSM_PYTHON" "$SSM_STAGE_RUNNER" \
  --run-dir "$SSM_RUN_DIR" --stage "$SSM_STAGE" \
  --model "$SSM_MODEL" --shard-index "$SLURM_ARRAY_TASK_ID"
