#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-p2-fullaudit
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:10:00
#SBATCH --output=runs/production_available_fullaudit_%j.out
#SBATCH --error=runs/production_available_fullaudit_%j.err

set -euo pipefail
PROJECT_ROOT="./dataset"
ANALYSIS="$PROJECT_ROOT/reports/production_available.production_available_v1.json"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src pytest -q
srun env PYTHONPATH=src python scripts/analyze_release.py \
    --root "$PROJECT_ROOT" --release production_available_v1 \
    --quota-version quota_production_available_v1 --seed 20260826 \
    --output "$ANALYSIS"
srun env PYTHONPATH=src python scripts/audit_replay_chain.py \
    --root "$PROJECT_ROOT" --release production_available_v1 \
    --quota-version quota_production_available_v1 --unknown-version unknown_p1_v2 \
    --realization-version realization_p1_v2 --proof-version proof_verification_p1_v2 \
    --canonical-version canonical_v4 --seed 20260826
srun env PYTHONPATH=src python scripts/audit_shortcut_controls.py \
    --root "$PROJECT_ROOT" --release production_available_v1 \
    --quota-version quota_production_available_v1 --seed 20260826 \
    --analysis-report "$ANALYSIS"
