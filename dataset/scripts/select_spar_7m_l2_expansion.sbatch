#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-spar-l2-expand
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=runs/spar_7m_l2_expansion_select_%j.out
#SBATCH --error=runs/spar_7m_l2_expansion_select_%j.err

set -euo pipefail
PROJECT_ROOT="./dataset"
SCRATCH_ROOT="external/upstream"
PARQUET="$SCRATCH_ROOT/data/full_media_incoming/spar/0fe664cbada1e7c1173fd743e0f781882eebf777/SPAR-7M/spar-dataset-train.parquet"
OUTPUT="$SCRATCH_ROOT/derived/spar_l2_bbox_expansion_v2/rows.jsonl"
module load python/3.12.11
cd "$PROJECT_ROOT"
srun python scripts/select_spar_7m_l2_expansion.py \
    --parquet "$PARQUET" --output "$OUTPUT" \
    --report "$PROJECT_ROOT/reports/spar/l2_expansion_selection.v2.json" \
    --per-scene 128 --seed 20260826 \
    --run-id "spar_7m_l2_expansion_select_${SLURM_JOB_ID}" --resume
