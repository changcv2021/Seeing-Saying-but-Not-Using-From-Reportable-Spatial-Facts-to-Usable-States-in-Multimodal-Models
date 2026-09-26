#!/bin/bash
#SBATCH --job-name=hypo3d_mmscan_vg_v2_3
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:30:00
#SBATCH --output=runs/hypo3d_mmscan_vg_v2_3_%j.out
#SBATCH --error=runs/hypo3d_mmscan_vg_v2_3_%j.err

set -euo pipefail

project_dir="./SpaceConflict"
v2="external/upstream/data/full_media_incoming/hypo3d/official/embodiedscan_v2_beta/extracted"
catalog="data/canonical/hypo3d_l4_v2_official_geometry_v2_1/object_catalog.v2.json"
work="transition_micrographs/hypo3d_l4_v2_official_mmscan_vg_v2_3"
claims="claim_graphs/hypo3d_l4_v2_official_mmscan_vg_v2_3"
accepted="accepted/hypo3d_l4_v2_official_mmscan_vg_v2_3"
media_root="external/upstream/data/full_media_incoming/hypo3d/ffb21ab198e8d666b63e062d931ed33b60c67d0f"

cd "${project_dir}"
module load python/3.12.11

PYTHONPATH=src srun python scripts/merge_mmscan_vg_target_resolutions.py \
    --parsed transition_micrographs/hypo3d_l4_v2/parsed_changes.v2_1.jsonl \
    --base-resolutions transition_micrographs/hypo3d_l4_v2_official_geometry_v2_2/target_resolutions.v2_2.jsonl \
    --mmscan-candidates reports/hypo3d_l4_v2/mmscan_vg_grounding_v1/candidates.mmscan_vg_exact_grounding_v1.jsonl \
    --mmscan-vg "${v2}/MMScan-beta/MMScan_samples/MMScan_VG.json" \
    --output "${work}/target_resolutions.v2_3_mmscan_vg.jsonl"

PYTHONPATH=src srun python -m spaceconflict.cli hypo3d-l4 build-prestates \
    --branch-index data/canonical/hypo3d_l4_v2/branches.jsonl \
    --parsed-changes transition_micrographs/hypo3d_l4_v2/parsed_changes.v2_1.jsonl \
    --post-oracles transition_micrographs/hypo3d_l4_v2/post_state_oracles.v2_3.jsonl \
    --target-resolutions "${work}/target_resolutions.v2_3_mmscan_vg.jsonl" \
    --object-catalog "${catalog}" \
    --output "${work}" \
    --run-id hypo3d_mmscan_vg_prestates_v2_3

PYTHONPATH=src srun python -m spaceconflict.cli hypo3d-l4 generate-claim-graphs \
    --prestates "${work}/prestates.count_v2.jsonl" \
    --calibration-limit 100 \
    --output "${claims}" \
    --run-id hypo3d_mmscan_vg_claims_v2_3

PYTHONPATH=src srun python -m spaceconflict.cli hypo3d-l4 verify \
    --branch-index data/canonical/hypo3d_l4_v2/branches.jsonl \
    --post-oracles transition_micrographs/hypo3d_l4_v2/post_state_oracles.v2_3.jsonl \
    --prestates "${work}/prestates.count_v2.jsonl" \
    --pairs "${claims}/pairs.count_l4_core_v2.jsonl" \
    --media-root "${media_root}" \
    --output "${accepted}" \
    --run-id hypo3d_mmscan_vg_final_verify_v2_3
