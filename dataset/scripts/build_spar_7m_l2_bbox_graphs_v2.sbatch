#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-spar-l2-graphs-v2
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=02:00:00
#SBATCH --output=runs/spar_7m_l2_bbox_graphs_v2_%j.out
#SBATCH --error=runs/spar_7m_l2_bbox_graphs_v2_%j.err

set -euo pipefail
PROJECT_ROOT="./dataset"
SCRATCH_ROOT="external/upstream"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src:scripts python scripts/build_spar_7m_l2_bbox_graphs.py \
    --root "$PROJECT_ROOT" \
    --input "$SCRATCH_ROOT/derived/spar_l2_bbox_expansion_v2/rows.jsonl" \
    --scan-report reports/spar/l2_expansion_selection.v2.json \
    --split splits/spar_7m_relation_v2.seed_20260826.jsonl \
    --artifact-version v2 --seed 20260826 \
    --run-id "spar_7m_l2_bbox_graphs_v2_${SLURM_JOB_ID}" --resume
