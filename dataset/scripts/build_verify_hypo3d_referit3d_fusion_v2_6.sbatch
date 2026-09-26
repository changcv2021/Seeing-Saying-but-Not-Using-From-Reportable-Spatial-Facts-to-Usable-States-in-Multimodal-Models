#!/bin/bash
#SBATCH --job-name=hypo3d_ref3d_v26
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=12G
#SBATCH --time=00:45:00
#SBATCH --output=runs/hypo3d_referit3d_fusion_v2_6_%j.out
#SBATCH --error=runs/hypo3d_referit3d_fusion_v2_6_%j.err

set -euo pipefail

project_dir="./dataset"
source_root="external/upstream/data/full_media_incoming/hypo3d/official/referit3d_725a5d3"
catalog="data/canonical/hypo3d_l4_v2_official_referit3d_fusion_v2_6/object_catalog.v2.json"
work="transition_micrographs/hypo3d_l4_v2_official_referit3d_fusion_v2_6"
claims="claim_graphs/hypo3d_l4_v2_official_referit3d_fusion_v2_6"
accepted="accepted/hypo3d_l4_v2_official_referit3d_fusion_v2_6"
media_root="external/upstream/data/full_media_incoming/hypo3d/ffb21ab198e8d666b63e062d931ed33b60c67d0f"

cd "${project_dir}"
module load python/3.12.11

PYTHONPATH=src srun python scripts/build_hypo3d_nr3d_fusion_artifacts.py \
    --nr3d "${source_root}/nr3d_official_download" \
    --sr3d "${source_root}/sr3d_plus.csv" \
    --sr3d-target-candidates reports/hypo3d_l4_v2/sr3d_coverage_v1/target_candidates.sr3d_v1.jsonl \
    --base-catalog data/canonical/hypo3d_l4_v2_official_3dssg_fusion_v2_5/object_catalog.v2.json \
    --branches data/canonical/hypo3d_l4_v2/branches.jsonl \
    --parsed transition_micrographs/hypo3d_l4_v2/parsed_changes.v2_1.jsonl \
    --existing-resolutions transition_micrographs/hypo3d_l4_v2_official_3dssg_fusion_v2_5/target_resolutions.v2_5.jsonl \
    --output-catalog "${catalog}" \
    --output-resolutions "${work}/referit3d_resolver/target_resolutions.referit3d_v1.jsonl" \
    --run-id hypo3d_referit3d_fusion_catalog_v2_6

PYTHONPATH=src srun python scripts/merge_hypo3d_resolution_sets.py \
    --fusion-resolutions "${work}/referit3d_resolver/target_resolutions.referit3d_v1.jsonl" \
    --preferred-resolutions transition_micrographs/hypo3d_l4_v2_official_3dssg_fusion_v2_5/target_resolutions.v2_5.jsonl \
    --output "${work}/target_resolutions.v2_6.jsonl" \
    --run-id hypo3d_referit3d_resolution_fusion_v2_6

PYTHONPATH=src srun python -m spaceconflict.cli hypo3d-l4 build-prestates \
    --branch-index data/canonical/hypo3d_l4_v2/branches.jsonl \
    --parsed-changes transition_micrographs/hypo3d_l4_v2/parsed_changes.v2_1.jsonl \
    --post-oracles transition_micrographs/hypo3d_l4_v2/post_state_oracles.v2_3.jsonl \
    --target-resolutions "${work}/target_resolutions.v2_6.jsonl" \
    --object-catalog "${catalog}" \
    --output "${work}" \
    --run-id hypo3d_referit3d_fusion_prestates_v2_6

PYTHONPATH=src srun python -m spaceconflict.cli hypo3d-l4 generate-claim-graphs \
    --prestates "${work}/prestates.count_v2.jsonl" \
    --calibration-limit 100 \
    --output "${claims}" \
    --run-id hypo3d_referit3d_fusion_claims_v2_6

PYTHONPATH=src srun python -m spaceconflict.cli hypo3d-l4 verify \
    --branch-index data/canonical/hypo3d_l4_v2/branches.jsonl \
    --post-oracles transition_micrographs/hypo3d_l4_v2/post_state_oracles.v2_3.jsonl \
    --prestates "${work}/prestates.count_v2.jsonl" \
    --pairs "${claims}/pairs.count_l4_core_v2.jsonl" \
    --media-root "${media_root}" \
    --output "${accepted}" \
    --run-id hypo3d_referit3d_fusion_final_verify_v2_6

PYTHONPATH=src srun python scripts/audit_hypo3d_geometry_relation_core.py \
    --parsed transition_micrographs/hypo3d_l4_v2/parsed_changes.v2_1.jsonl \
    --oracles transition_micrographs/hypo3d_l4_v2/post_state_oracles.v2_3.jsonl \
    --resolutions "${work}/target_resolutions.v2_6.jsonl" \
    --catalog "${catalog}" \
    --output-dir reports/hypo3d_l4_v2/referit3d_fusion_geometry_relation_v2_6
