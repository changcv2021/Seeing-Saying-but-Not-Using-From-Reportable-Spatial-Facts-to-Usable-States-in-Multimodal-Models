#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-spar7m-relaudit
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=runs/spar_7m_relation_audit_%j.out
#SBATCH --error=runs/spar_7m_relation_audit_%j.err

set -euo pipefail
PROJECT_ROOT="./dataset"
module load python/3.12.11
cd "$PROJECT_ROOT"

set +e
srun env PYTHONPATH=src python scripts/audit_spar_7m_relation_semantics.py \
    --root "$PROJECT_ROOT" \
    --candidates "$PROJECT_ROOT/data/staging/adapters/spar/0fe664cbada1e7c1173fd743e0f781882eebf777/spar_7m_qualitative_relation_v2/fact_candidates.jsonl" \
    --output "$PROJECT_ROOT/reports/spar/relation_semantics_audit.v1.json" \
    --details "$PROJECT_ROOT/rejected/verification/spar_7m_relation_semantics.v1.jsonl" --resume
RC=$?
set -e
if [[ "$RC" != 0 && "$RC" != 2 ]]; then
    exit "$RC"
fi
exit 0
