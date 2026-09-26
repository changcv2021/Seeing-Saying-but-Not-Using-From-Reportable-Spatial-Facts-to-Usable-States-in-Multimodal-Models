#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-p2-v6-report
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:10:00
#SBATCH --output=runs/production_available_v6_report_%j.out
#SBATCH --error=runs/production_available_v6_report_%j.err

set -euo pipefail
PROJECT_ROOT="./SpaceConflict"
GUIDE="$PROJECT_ROOT/../SpaceConflict_Codex_Benchmark_Build_Guide_CN.md"
AUDIT_JOB_ID="${AUDIT_JOB_ID:?AUDIT_JOB_ID must identify the completed v6 full-audit job}"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src python scripts/audit_guide_compliance.py \
    --root "$PROJECT_ROOT" --guide "$GUIDE" \
    --release production_available_v6 --quota-version quota_production_available_v6 \
    --proof-report reports/proof_verification.proof_verification_p1_v2.json \
    --proof-report reports/proof_verification.proof_verification_ca_train_production_v1.json \
    --proof-report reports/proof_verification.proof_verification_l2_relation_graph_v1.json \
    --proof-report reports/proof_verification.proof_verification_spar_7m_l1_v1.json \
    --proof-report reports/proof_verification.proof_verification_spar_7m_l3_xform_v1.json \
    --unknown-report reports/unknown_generation.unknown_p1_v2.json \
    --unknown-report reports/unknown_generation.unknown_ca_train_production_v1.json \
    --test-count 81 --test-job-id "$AUDIT_JOB_ID" --seed 20260826 \
    --output-json "$PROJECT_ROOT/reports/guide_compliance.production_available_v6.json" \
    --output-markdown "$PROJECT_ROOT/reports/guide_compliance.production_available_v6.md"
srun env PYTHONPATH=src python scripts/build_final_available_report.py \
    --root "$PROJECT_ROOT" --release production_available_v6 \
    --quota-version quota_production_available_v6 --seed 20260826 \
    --proof-report reports/proof_verification.proof_verification_p1_v2.json \
    --proof-report reports/proof_verification.proof_verification_ca_train_production_v1.json \
    --proof-report reports/proof_verification.proof_verification_l2_relation_graph_v1.json \
    --proof-report reports/proof_verification.proof_verification_spar_7m_l1_v1.json \
    --proof-report reports/proof_verification.proof_verification_spar_7m_l3_xform_v1.json \
    --unknown-report reports/unknown_generation.unknown_p1_v2.json \
    --unknown-report reports/unknown_generation.unknown_ca_train_production_v1.json \
    --guide-compliance "$PROJECT_ROOT/reports/guide_compliance.production_available_v6.json" \
    --test-count 81 --test-job-id "$AUDIT_JOB_ID" \
    --output-json "$PROJECT_ROOT/reports/final.production_available_v6.json" \
    --output-markdown "$PROJECT_ROOT/reports/final.production_available_v6.md"
