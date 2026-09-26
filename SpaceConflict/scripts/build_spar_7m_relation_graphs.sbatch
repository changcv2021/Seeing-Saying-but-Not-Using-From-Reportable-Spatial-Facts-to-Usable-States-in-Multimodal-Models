#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-spar7m-relgraph
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=24G
#SBATCH --time=02:00:00
#SBATCH --output=runs/spar_7m_relation_graph_%j.out
#SBATCH --error=runs/spar_7m_relation_graph_%j.err

set -euo pipefail
PROJECT_ROOT="./SpaceConflict"
SOURCE_REVISION="0fe664cbada1e7c1173fd743e0f781882eebf777"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src python scripts/build_spar_7m_relation_graphs.py \
    --root "$PROJECT_ROOT" \
    --input "$PROJECT_ROOT/data/staging/spar/${SOURCE_REVISION}/spar_7m_relation_subset_v1/rows.jsonl" \
    --selection-report "$PROJECT_ROOT/reports/spar/relation_subset.v1.json" \
    --output "$PROJECT_ROOT/reports/spar/relation_graph_build.v2.json" \
    --seed 20260826 --run-id "spar_7m_relation_graph_${SLURM_JOB_ID}" --resume
