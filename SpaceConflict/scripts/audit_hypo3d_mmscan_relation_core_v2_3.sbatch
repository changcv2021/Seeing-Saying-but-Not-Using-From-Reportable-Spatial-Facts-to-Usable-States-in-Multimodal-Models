#!/bin/bash
#SBATCH --job-name=hypo3d_mmscan_relation_audit
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:30:00
#SBATCH --output=runs/hypo3d_mmscan_relation_audit_%j.out
#SBATCH --error=runs/hypo3d_mmscan_relation_audit_%j.err

set -euo pipefail

project_dir="./SpaceConflict"

cd "${project_dir}"
module load python/3.12.11

PYTHONPATH=src srun python scripts/audit_hypo3d_geometry_relation_core.py \
    --parsed transition_micrographs/hypo3d_l4_v2/parsed_changes.v2_1.jsonl \
    --oracles transition_micrographs/hypo3d_l4_v2/post_state_oracles.v2_3.jsonl \
    --resolutions transition_micrographs/hypo3d_l4_v2_official_mmscan_vg_v2_3/target_resolutions.v2_3_mmscan_vg.jsonl \
    --catalog data/canonical/hypo3d_l4_v2_official_geometry_v2_1/object_catalog.v2.json \
    --output-dir reports/hypo3d_l4_v2/mmscan_geometry_relation_feasibility_v2_3
