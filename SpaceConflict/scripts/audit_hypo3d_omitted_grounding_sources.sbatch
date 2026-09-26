#!/bin/bash
#SBATCH --job-name=hypo3d_omitted_grounding
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --output=runs/hypo3d_omitted_grounding_%j.out
#SBATCH --error=runs/hypo3d_omitted_grounding_%j.err

set -euo pipefail

project_dir="./SpaceConflict"
scratch_root="external/upstream/data/full_media_incoming/hypo3d/official"
v2="${scratch_root}/embodiedscan_v2_beta/extracted"

cd "${project_dir}"
module load python/3.12.11

PYTHONPATH=src srun python scripts/audit_hypo3d_omitted_grounding_sources.py \
    --axis "${scratch_root}/hypo3d_form_release_20260829/Axis Definition.xlsx" \
    --vg "${v2}/embodiedscan-v2/embodiedscan_train_vg.json" \
    --vg "${v2}/embodiedscan-v2/embodiedscan_val_vg.json" \
    --parsed transition_micrographs/hypo3d_l4_v2/parsed_changes.v2_1.jsonl \
    --oracles transition_micrographs/hypo3d_l4_v2/post_state_oracles.v2_3.jsonl \
    --resolutions transition_micrographs/hypo3d_l4_v2_official_mmscan_vg_v2_3/target_resolutions.v2_3_mmscan_vg.jsonl \
    --catalog data/canonical/hypo3d_l4_v2_official_geometry_v2_1/object_catalog.v2.json \
    --output-dir reports/hypo3d_l4_v2/omitted_grounding_sources_v1 \
    --run-id omitted_grounding_sources_v1
