#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-spar7m-l3select
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=runs/spar_7m_l3_select_%j.out
#SBATCH --error=runs/spar_7m_l3_select_%j.err

set -euo pipefail
PROJECT_ROOT="./dataset"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src python scripts/select_spar_7m_strict_multiview.py \
    --root "$PROJECT_ROOT" \
    --candidates "$PROJECT_ROOT/data/staging/adapters/spar/0fe664cbada1e7c1173fd743e0f781882eebf777/spar_7m_qualitative_relation_v2/fact_candidates.jsonl" \
    --media-index "$PROJECT_ROOT/data/media_index/spar/0fe664cbada1e7c1173fd743e0f781882eebf777/qualitative_relation_media.v2.jsonl" \
    --output "$PROJECT_ROOT/data/staging/spar/0fe664cbada1e7c1173fd743e0f781882eebf777/strict_multiview_v1/source_items.jsonl" \
    --report "$PROJECT_ROOT/reports/spar/strict_multiview_selection.v1.json" --resume
