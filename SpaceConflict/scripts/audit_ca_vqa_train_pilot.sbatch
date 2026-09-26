#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-ca-train-audit
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:10:00
#SBATCH --output=runs/ca_train_pilot_audit_%j.out
#SBATCH --error=runs/ca_train_pilot_audit_%j.err

set -euo pipefail
PROJECT_ROOT="./SpaceConflict"
DATA_ROOT="external/upstream/data/full_media_incoming/ca_vqa/080812355c21a40f437ed03d4ae558d35bfa2929"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src python scripts/audit_ca_vqa_train_pilot.py \
    --root "$PROJECT_ROOT" --data-root "$DATA_ROOT" \
    --extract-report "$PROJECT_ROOT/reports/ca_vqa/train_adapter_pilot.v2.json" \
    --seed 20260826 --run-id "ca_train_pilot_audit_${SLURM_JOB_ID}" \
    --resume
