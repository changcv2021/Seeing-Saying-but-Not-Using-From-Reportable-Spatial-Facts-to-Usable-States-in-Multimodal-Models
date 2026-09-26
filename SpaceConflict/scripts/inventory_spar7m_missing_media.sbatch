#!/bin/bash
#SBATCH --job-name=sc_spar7m_inventory
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:20:00
#SBATCH --output=artifacts/upstream_media/spar7m_acquisition/slurm/%x_%j.out
#SBATCH --error=artifacts/upstream_media/spar7m_acquisition/slurm/%x_%j.err

set -euo pipefail

module load python/3.12.11
BUNDLE_ROOT="artifacts"
PROJECT_ROOT="./SpaceConflict"
OUTPUT_ROOT="$BUNDLE_ROOT/upstream_media/spar7m_acquisition"

srun python "$PROJECT_ROOT/scripts/inventory_spar7m_missing_media.py" \
  --release-dir "$BUNDLE_ROOT/benchmark/l1_l3/release" \
  --unavailable "$BUNDLE_ROOT/benchmark/l1_l3/evaluation/media_unavailable.jsonl" \
  --output-dir "$OUTPUT_ROOT"
