#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-hypo3d-adapter
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=runs/hypo3d_adapter_%j.out
#SBATCH --error=runs/hypo3d_adapter_%j.err

set -euo pipefail

PROJECT_ROOT="./dataset"
SEED=20260826
RUN_ID="hypo3d_adapter_${SLURM_JOB_ID}"

module load python/3.12.11
cd "$PROJECT_ROOT"

# First pass freezes the complete deterministic adapter output. Canonical
# promotion is expected to report blocked until the media report exists.
set +e
srun env PYTHONPATH=src python -m spaceconflict.cli build-canonical \
    --dataset hypo3d --seed "$SEED" --run-id "${RUN_ID}_adapter" \
    --workers 1 --resume
ADAPTER_RC=$?
set -e
if [[ "$ADAPTER_RC" != 0 && "$ADAPTER_RC" != 2 ]]; then
    exit "$ADAPTER_RC"
fi

srun env PYTHONPATH=src python -m spaceconflict.cli validate-media \
    --dataset hypo3d --seed "$SEED" --run-id "${RUN_ID}_media" \
    --workers 1 --limit 10 --resume

# Resume verifies that adapter bytes are deterministic, then promotes only
# candidates with valid source reconstruction and media mappings.
srun env PYTHONPATH=src python -m spaceconflict.cli build-canonical \
    --dataset hypo3d --seed "$SEED" --run-id "${RUN_ID}_canonical" \
    --workers 1 --media-run-id "${RUN_ID}_media" --resume

srun env PYTHONPATH=src python -m spaceconflict.cli reconstruct-source-qa \
    --dataset hypo3d --seed "$SEED" --run-id "${RUN_ID}_reconstruction" \
    --workers 1 --resume
