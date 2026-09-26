#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-spar-l2-scan
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:15:00
#SBATCH --output=runs/spar_7m_l2_bbox_scan_%j.out
#SBATCH --error=runs/spar_7m_l2_bbox_scan_%j.err

set -euo pipefail
PROJECT_ROOT="./dataset"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src python scripts/scan_spar_7m_l2_bbox_chains.py \
    --root "$PROJECT_ROOT" \
    --input data/staging/spar/0fe664cbada1e7c1173fd743e0f781882eebf777/spar_7m_relation_subset_v1/rows.jsonl \
    --report reports/spar/l2_bbox_chain_scan.v1.json \
    --candidates data/staging/spar/0fe664cbada1e7c1173fd743e0f781882eebf777/l2_bbox_chain_v1/candidates.jsonl \
    --run-id "spar_7m_l2_bbox_scan_${SLURM_JOB_ID}" --resume
