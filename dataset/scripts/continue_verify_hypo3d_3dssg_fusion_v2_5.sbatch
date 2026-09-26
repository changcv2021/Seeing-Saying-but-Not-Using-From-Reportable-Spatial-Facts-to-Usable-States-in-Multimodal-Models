#!/bin/bash
#SBATCH --job-name=hypo3d_3dssg_v25_continue
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=runs/hypo3d_3dssg_fusion_v2_5_continue_%j.out
#SBATCH --error=runs/hypo3d_3dssg_fusion_v2_5_continue_%j.err

set -euo pipefail

project_dir="./dataset"
catalog="data/canonical/hypo3d_l4_v2_official_3dssg_fusion_v2_5/object_catalog.v2.json"
work="transition_micrographs/hypo3d_l4_v2_official_3dssg_fusion_v2_5"
claims="claim_graphs/hypo3d_l4_v2_official_3dssg_fusion_v2_5"
accepted="accepted/hypo3d_l4_v2_official_3dssg_fusion_v2_5"
media_root="external/upstream/data/full_media_incoming/hypo3d/ffb21ab198e8d666b63e062d931ed33b60c67d0f"

cd "${project_dir}"
module load python/3.12.11

PYTHONPATH=src srun python scripts/merge_hypo3d_resolution_sets.py \
    --fusion-resolutions "${work}/fusion_resolver/target_resolutions.v2_2.jsonl" \
    --preferred-resolutions transition_micrographs/hypo3d_l4_v2_official_all_grounding_v2_4/target_resolutions.v2_4.jsonl \
    --output "${work}/target_resolutions.v2_5.jsonl" \
    --run-id hypo3d_3dssg_resolution_fusion_v2_5

PYTHONPATH=src srun python -m spaceconflict.cli hypo3d-l4 build-prestates \
    --branch-index data/canonical/hypo3d_l4_v2/branches.jsonl \
    --parsed-changes transition_micrographs/hypo3d_l4_v2/parsed_changes.v2_1.jsonl \
    --post-oracles transition_micrographs/hypo3d_l4_v2/post_state_oracles.v2_3.jsonl \
    --target-resolutions "${work}/target_resolutions.v2_5.jsonl" \
    --object-catalog "${catalog}" \
    --output "${work}" \
    --run-id hypo3d_3dssg_fusion_prestates_v2_5

PYTHONPATH=src srun python -m spaceconflict.cli hypo3d-l4 generate-claim-graphs \
    --prestates "${work}/prestates.count_v2.jsonl" \
    --calibration-limit 100 \
    --output "${claims}" \
    --run-id hypo3d_3dssg_fusion_claims_v2_5

PYTHONPATH=src srun python -m spaceconflict.cli hypo3d-l4 verify \
    --branch-index data/canonical/hypo3d_l4_v2/branches.jsonl \
    --post-oracles transition_micrographs/hypo3d_l4_v2/post_state_oracles.v2_3.jsonl \
    --prestates "${work}/prestates.count_v2.jsonl" \
    --pairs "${claims}/pairs.count_l4_core_v2.jsonl" \
    --media-root "${media_root}" \
    --output "${accepted}" \
    --run-id hypo3d_3dssg_fusion_final_verify_v2_5

PYTHONPATH=src srun python scripts/audit_hypo3d_geometry_relation_core.py \
    --parsed transition_micrographs/hypo3d_l4_v2/parsed_changes.v2_1.jsonl \
    --oracles transition_micrographs/hypo3d_l4_v2/post_state_oracles.v2_3.jsonl \
    --resolutions "${work}/target_resolutions.v2_5.jsonl" \
    --catalog "${catalog}" \
    --output-dir reports/hypo3d_l4_v2/3dssg_fusion_geometry_relation_v2_5
