#!/bin/bash
#SBATCH --job-name=hypo3d_l4_tier_a_v2_1
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:30:00
#SBATCH --output=runs/hypo3d_official_l4_tier_a_v2_1_%j.out
#SBATCH --error=runs/hypo3d_official_l4_tier_a_v2_1_%j.err

set -euo pipefail

project_dir="./SpaceConflict"
media_root="external/upstream/data/full_media_incoming/hypo3d/ffb21ab198e8d666b63e062d931ed33b60c67d0f"
micrographs="transition_micrographs/hypo3d_l4_v2_official_tier_a_v2_1"
claims="claim_graphs/hypo3d_l4_v2_official_tier_a_v2_1"
accepted="accepted/hypo3d_l4_v2_official_tier_a_v2_1"

cd "${project_dir}"
module load python/3.12.11

PYTHONPATH=src srun python -m spaceconflict.cli hypo3d-l4 build-prestates \
    --branch-index data/canonical/hypo3d_l4_v2/branches.jsonl \
    --parsed-changes transition_micrographs/hypo3d_l4_v2/parsed_changes.v2_1.jsonl \
    --post-oracles transition_micrographs/hypo3d_l4_v2/post_state_oracles.v2_3.jsonl \
    --target-resolutions transition_micrographs/hypo3d_l4_v2_official/target_resolutions.v2_1.jsonl \
    --object-catalog data/canonical/hypo3d_l4_v2_official/object_catalog.v2.json \
    --output "${micrographs}" \
    --run-id hypo3d_official_tier_a_v2_1_prestates

PYTHONPATH=src srun python -m spaceconflict.cli hypo3d-l4 generate-claim-graphs \
    --prestates "${micrographs}/prestates.count_v2.jsonl" \
    --output "${claims}" \
    --run-id hypo3d_official_tier_a_v2_1_claims

PYTHONPATH=src srun python -m spaceconflict.cli hypo3d-l4 verify \
    --branch-index data/canonical/hypo3d_l4_v2/branches.jsonl \
    --post-oracles transition_micrographs/hypo3d_l4_v2/post_state_oracles.v2_3.jsonl \
    --prestates "${micrographs}/prestates.count_v2.jsonl" \
    --pairs "${claims}/pairs.count_l4_core_v2.jsonl" \
    --media-root "${media_root}" \
    --output "${accepted}" \
    --run-id hypo3d_official_tier_a_v2_1_verify
