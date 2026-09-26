#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-p2-v10-fullaudit
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=runs/production_available_v10_audit_%j.out
#SBATCH --error=runs/production_available_v10_audit_%j.err

set -euo pipefail
PROJECT_ROOT="./SpaceConflict"
ANALYSIS="$PROJECT_ROOT/reports/production_available.production_available_v10.json"
module load python/3.12.11
cd "$PROJECT_ROOT"
srun env PYTHONPATH=src pytest -q
srun env PYTHONPATH=src python scripts/analyze_release.py \
    --root "$PROJECT_ROOT" --release production_available_v10 \
    --quota-version quota_production_available_v10 --seed 20260826 \
    --language-report reports/language_realization.realization_p1_v2.json \
    --language-report reports/language_realization.realization_ca_train_production_v1.json \
    --language-report reports/language_realization.realization_l2_relation_graph_v1.json \
    --language-report reports/language_realization.realization_spar_7m_l1_v1.json \
    --language-report reports/language_realization.realization_spar_7m_l2_bbox_v3.json \
    --language-report reports/language_realization.realization_spar_7m_l3_xform_v1.json \
    --output "$ANALYSIS"
srun env PYTHONPATH=src python scripts/audit_release.py \
    --root "$PROJECT_ROOT" --release production_available_v10 \
    --quota-version quota_production_available_v10 --seed 20260826 \
    --unknown-path candidates/unknown/claims.unknown_p1_v2.jsonl \
    --unknown-path candidates/unknown/claims.unknown_ca_train_production_v1.jsonl \
    --unknown-path candidates/unknown/claims.unknown_spar_view_ablation_v4.jsonl \
    --split-path splits/world_split_v6.seed_20260826.jsonl \
    --split-path splits/ca_vqa_train_production_subset_v1.seed_20260826.jsonl \
    --split-path splits/spar_7m_relation_v2.seed_20260826.jsonl
srun env PYTHONPATH=src python scripts/audit_replay_chain.py \
    --root "$PROJECT_ROOT" --release production_available_v10 \
    --quota-version quota_production_available_v10 --seed 20260826 \
    --proof-path candidates/auto_accepted/pairs.proof_verification_p1_v2.jsonl \
    --proof-path candidates/auto_accepted/pairs.proof_verification_ca_train_production_v1.jsonl \
    --proof-path candidates/auto_accepted/pairs.proof_verification_l2_relation_graph_v1.jsonl \
    --proof-path candidates/auto_accepted/pairs.proof_verification_spar_7m_l1_v1.jsonl \
    --proof-path candidates/auto_accepted/pairs.proof_verification_spar_7m_l2_bbox_v3.jsonl \
    --proof-path candidates/auto_accepted/pairs.proof_verification_spar_7m_l3_xform_v1.jsonl \
    --realization-path realization_traces/traces.realization_p1_v2.jsonl \
    --realization-path realization_traces/traces.realization_ca_train_production_v1.jsonl \
    --realization-path realization_traces/traces.realization_l2_relation_graph_v1.jsonl \
    --realization-path realization_traces/traces.realization_spar_7m_l1_v1.jsonl \
    --realization-path realization_traces/traces.realization_spar_7m_l2_bbox_v3.jsonl \
    --realization-path realization_traces/traces.realization_spar_7m_l3_xform_v1.jsonl \
    --unknown-path candidates/unknown/claims.unknown_p1_v2.jsonl \
    --unknown-path candidates/unknown/claims.unknown_ca_train_production_v1.jsonl \
    --unknown-path candidates/unknown/claims.unknown_spar_view_ablation_v4.jsonl \
    --canonical-version canonical_v4 \
    --additional-canonical-path data/canonical/ca_vqa_train/080812355c21a40f437ed03d4ae558d35bfa2929/canonical_train_production_subset_v1/records.jsonl \
    --additional-canonical-path data/canonical/spar/0fe664cbada1e7c1173fd743e0f781882eebf777/canonical_spar_7m_relation_v2/records.jsonl \
    --additional-canonical-path data/canonical/spar/0fe664cbada1e7c1173fd743e0f781882eebf777/canonical_spar_7m_bbox_identity_l2_v2/records.jsonl
srun env PYTHONPATH=src python scripts/audit_shortcut_controls.py \
    --root "$PROJECT_ROOT" --release production_available_v10 \
    --quota-version quota_production_available_v10 --seed 20260826 \
    --analysis-report "$ANALYSIS" --control-version shortcut_controls_v10
