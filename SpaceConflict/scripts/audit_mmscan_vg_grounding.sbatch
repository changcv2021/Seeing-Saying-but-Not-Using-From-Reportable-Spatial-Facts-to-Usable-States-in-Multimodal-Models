#!/bin/bash
#SBATCH --job-name=mmscan_vg_grounding_audit
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --output=runs/mmscan_vg_grounding_audit_%j.out
#SBATCH --error=runs/mmscan_vg_grounding_audit_%j.err

set -euo pipefail

project_dir="./SpaceConflict"
v2="external/upstream/data/full_media_incoming/hypo3d/official/embodiedscan_v2_beta/extracted"

cd "${project_dir}"
module load python/3.12.11

PYTHONPATH=src srun python scripts/audit_mmscan_vg_grounding.py \
    --vg "${v2}/MMScan-beta/MMScan_samples/MMScan_VG.json" \
    --parsed transition_micrographs/hypo3d_l4_v2/parsed_changes.v2_1.jsonl \
    --oracles transition_micrographs/hypo3d_l4_v2/post_state_oracles.v2_3.jsonl \
    --resolutions transition_micrographs/hypo3d_l4_v2_official_geometry_v2_2/target_resolutions.v2_2.jsonl \
    --catalog data/canonical/hypo3d_l4_v2_official_geometry_v2_1/object_catalog.v2.json \
    --output-dir reports/hypo3d_l4_v2/mmscan_vg_grounding_v1
