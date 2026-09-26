#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-spar-l2-graphs
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=runs/spar_7m_l2_bbox_graphs_%j.out
#SBATCH --error=runs/spar_7m_l2_bbox_graphs_%j.err

set -euo pipefail
PROJECT_ROOT="./dataset"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src:scripts python scripts/build_spar_7m_l2_bbox_graphs.py \
    --root "$PROJECT_ROOT" \
    --input data/staging/spar/0fe664cbada1e7c1173fd743e0f781882eebf777/spar_7m_relation_subset_v1/rows.jsonl \
    --scan-report reports/spar/l2_bbox_chain_scan.v1.json \
    --split splits/spar_7m_relation_v2.seed_20260826.jsonl \
    --seed 20260826 --run-id "spar_7m_l2_bbox_graphs_${SLURM_JOB_ID}" --resume
