#!/bin/bash
#SBATCH --job-name=hypo3d_3dssg_audit
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=runs/hypo3d_3dssg_audit_%j.out
#SBATCH --error=runs/hypo3d_3dssg_audit_%j.err

set -euo pipefail

project_dir="./SpaceConflict"
source_root="external/upstream/data/full_media_incoming/hypo3d/official/3dssg_20250509/extracted/3DSSG"

cd "${project_dir}"
module load python/3.12.11

PYTHONPATH=src srun python scripts/audit_hypo3d_3dssg_coverage.py \
    --objects "${source_root}/objects.json" \
    --relationships "${source_root}/relationships.json" \
    --branches data/canonical/hypo3d_l4_v2/branches.jsonl \
    --parsed transition_micrographs/hypo3d_l4_v2/parsed_changes.v2_1.jsonl \
    --catalog data/canonical/hypo3d_l4_v2_official_geometry_v2_1/object_catalog.v2.json \
    --output-dir reports/hypo3d_l4_v2/3dssg_coverage_v1 \
    --run-id hypo3d_3dssg_coverage_v1
