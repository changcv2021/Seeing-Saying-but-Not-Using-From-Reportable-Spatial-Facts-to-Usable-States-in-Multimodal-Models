#!/bin/bash
#SBATCH --job-name=hypo3d_official_l4_count
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:30:00
#SBATCH --output=runs/hypo3d_official_l4_count_%j.out
#SBATCH --error=runs/hypo3d_official_l4_count_%j.err

set -euo pipefail

project_dir="./SpaceConflict"
catalog="data/canonical/hypo3d_l4_v2_official/object_catalog.v2.json"
branches="data/canonical/hypo3d_l4_v2/branches.jsonl"
parsed="transition_micrographs/hypo3d_l4_v2/parsed_changes.v2_1.jsonl"
oracles="transition_micrographs/hypo3d_l4_v2/post_state_oracles.v2_3.jsonl"
micrographs="transition_micrographs/hypo3d_l4_v2_official"
targets="${micrographs}/target_resolutions.v2_1.jsonl"
prestates="${micrographs}/prestates.count_v2.jsonl"

cd "${project_dir}"
module load python/3.12.11

PYTHONPATH=src srun python -m spaceconflict.cli hypo3d-l4 resolve-targets \
    --parsed-changes "${parsed}" \
    --object-catalog "${catalog}" \
    --output "${micrographs}" \
    --run-id hypo3d_official_target_resolution_v2

PYTHONPATH=src srun python -m spaceconflict.cli hypo3d-l4 build-prestates \
    --branch-index "${branches}" \
    --parsed-changes "${parsed}" \
    --post-oracles "${oracles}" \
    --target-resolutions "${targets}" \
    --object-catalog "${catalog}" \
    --output "${micrographs}" \
    --run-id hypo3d_official_prestates_count_v2

PYTHONPATH=src srun python -m spaceconflict.cli hypo3d-l4 generate-claim-graphs \
    --prestates "${prestates}" \
    --output claim_graphs/hypo3d_l4_v2_official \
    --run-id hypo3d_official_count_claims_v2
