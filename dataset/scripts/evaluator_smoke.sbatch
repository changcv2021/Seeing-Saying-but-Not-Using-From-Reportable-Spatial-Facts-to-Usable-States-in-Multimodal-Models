#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-eval-smoke
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:15:00
#SBATCH --output=runs/evaluator_smoke_%j.out
#SBATCH --error=runs/evaluator_smoke_%j.err

set -euo pipefail
PROJECT_ROOT="./dataset"
RUN_DIR="${PROJECT_ROOT}/runs/evaluator_smoke_${SLURM_JOB_ID}"
RELEASE_DIR="${PROJECT_ROOT}/release/pilot_verified_2k_v2"
PREDICTIONS="${RUN_DIR}/oracle_predictions.private_test_only.jsonl"
REPORT="${PROJECT_ROOT}/reports/evaluation.pilot_verified_2k_v2.oracle_smoke.json"

module load python/3.12.11
cd "$PROJECT_ROOT"
mkdir -p "$RUN_DIR"

srun env PYTHONPATH=src pytest -q
srun env PYTHONPATH=src python scripts/make_evaluator_smoke_predictions.py \
    --release-dir "$RELEASE_DIR" \
    --output "$PREDICTIONS"
srun env PYTHONPATH=src python -m spaceconflict.cli evaluate \
    --predictions "$PREDICTIONS" \
    --release-dir "$RELEASE_DIR" \
    --output "$REPORT" \
    --resume \
    --run-id "evaluator_smoke_${SLURM_JOB_ID}"
srun python scripts/audit_evaluator_smoke.py "$REPORT"
