#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-level-audit
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:15:00
#SBATCH --output=runs/level_feasibility_%j.out
#SBATCH --error=runs/level_feasibility_%j.err

set -euo pipefail
PROJECT_ROOT="./SpaceConflict"
SEED=20260826
RUN_ID="level_feasibility_${SLURM_JOB_ID:-manual}"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun python scripts/audit_level_feasibility.py \
    --root "$PROJECT_ROOT" \
    --l2-manifest "$PROJECT_ROOT/world_graphs/manifest.world_graph_v5.jsonl" \
    --l4-manifest "$PROJECT_ROOT/world_graphs/manifest.world_graph_hypo3d_v1.jsonl" \
    --output "$PROJECT_ROOT/reports/level_feasibility.v1.json" \
    --seed "$SEED" --run-id "$RUN_ID" --resume
