#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-ca-avail-audit
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=runs/ca_train_available_audit_%j.out
#SBATCH --error=runs/ca_train_available_audit_%j.err

set -euo pipefail
PROJECT_ROOT="./dataset"
DATA_ROOT="external/upstream/data/full_media_incoming/ca_vqa/080812355c21a40f437ed03d4ae558d35bfa2929"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src python scripts/audit_ca_vqa_train_pilot.py \
    --root "$PROJECT_ROOT" --data-root "$DATA_ROOT" \
    --extract-report "$PROJECT_ROOT/reports/ca_vqa/train_available_subset.combined.v1.json" \
    --audit-version ca_vqa_train_available_subset_closure_v1 \
    --canonical-version canonical_train_available_subset_v1 \
    --graph-version world_graph_train_available_subset_v1 \
    --split-version ca_vqa_train_available_subset_v1 \
    --valid-status TRAIN_AVAILABLE_SUBSET_CLOSURE_VALID \
    --validation-scope decoded_train_available_binary_cardinality_subset \
    --next-gate CLAIM_CONSTRUCTION_LANGUAGE_AND_PROOF_VERIFICATION \
    --output "$PROJECT_ROOT/reports/ca_vqa/train_available_subset_closure.v1.json" \
    --seed 20260826 --run-id "ca_train_available_audit_${SLURM_JOB_ID}" --resume
