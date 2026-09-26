#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-spar7m-rel
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=12G
#SBATCH --time=01:00:00
#SBATCH --output=runs/spar_7m_relation_select_%j.out
#SBATCH --error=runs/spar_7m_relation_select_%j.err

set -euo pipefail
PROJECT_ROOT="./dataset"
PARQUET="external/upstream/data/full_media_incoming/spar/0fe664cbada1e7c1173fd743e0f781882eebf777/SPAR-7M/spar-dataset-train.parquet"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun python scripts/select_spar_7m_relation_subset.py \
    --root "$PROJECT_ROOT" --parquet "$PARQUET" \
    --output "$PROJECT_ROOT/data/staging/spar/0fe664cbada1e7c1173fd743e0f781882eebf777/spar_7m_relation_subset_v1/rows.jsonl" \
    --report "$PROJECT_ROOT/reports/spar/relation_subset.v1.json" \
    --per-scene-task 8 --seed 20260826 --run-id "spar_7m_relation_select_${SLURM_JOB_ID}" \
    --limit 0 --resume
