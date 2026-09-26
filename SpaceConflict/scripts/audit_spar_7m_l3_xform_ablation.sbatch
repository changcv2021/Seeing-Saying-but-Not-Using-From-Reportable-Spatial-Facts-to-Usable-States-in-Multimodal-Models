#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-spar7m-xaudit
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=runs/spar_7m_l3_xform_audit_%j.out
#SBATCH --error=runs/spar_7m_l3_xform_audit_%j.err

set -euo pipefail
PROJECT_ROOT="./SpaceConflict"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src python scripts/audit_spar_7m_l3_xform_ablation.py \
    --root "$PROJECT_ROOT" \
    --proofs "$PROJECT_ROOT/candidates/auto_accepted/pairs.proof_verification_spar_7m_l3_xform_v1.jsonl" \
    --allowlist "$PROJECT_ROOT/data/staging/spar/0fe664cbada1e7c1173fd743e0f781882eebf777/strict_multiview_v1/source_items.jsonl" \
    --media-index "$PROJECT_ROOT/data/media_index/spar/0fe664cbada1e7c1173fd743e0f781882eebf777/qualitative_relation_media.v2.jsonl" \
    --output "$PROJECT_ROOT/reports/spar/l3_xform_ablation.v1.json" \
    --details "$PROJECT_ROOT/verifier_outputs/spar_7m_l3_xform_ablation.v1.jsonl" --resume
