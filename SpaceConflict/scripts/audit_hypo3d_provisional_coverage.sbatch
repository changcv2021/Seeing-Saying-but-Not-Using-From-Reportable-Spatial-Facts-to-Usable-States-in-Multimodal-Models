#!/bin/bash
#SBATCH --job-name=hypo3d_provisional_coverage
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:30:00
#SBATCH --output=runs/hypo3d_provisional_coverage_%j.out
#SBATCH --error=runs/hypo3d_provisional_coverage_%j.err

set -euo pipefail

project_dir="./SpaceConflict"
catalog="data/canonical/hypo3d_l4_v2_provisional_mirror/object_catalog.provisional_mirror_v2.json"
parsed="transition_micrographs/hypo3d_l4_v2/parsed_changes.v2_1.jsonl"
targets="transition_micrographs/hypo3d_l4_v2_provisional_mirror/target_resolutions.provisional_mirror_v2.jsonl"

cd "${project_dir}"
module load python/3.12.11

PYTHONPATH=src srun python -m spaceconflict.cli hypo3d-l4 resolve-targets \
    --parsed-changes "${parsed}" \
    --object-catalog "${catalog}" \
    --output transition_micrographs/hypo3d_l4_v2_provisional_mirror \
    --run-id hypo3d_provisional_target_resolution_v2

PYTHONPATH=src srun python -m spaceconflict.cli hypo3d-l4 audit-provisional-coverage \
    --branch-index data/canonical/hypo3d_l4_v2/branches.jsonl \
    --parsed-changes "${parsed}" \
    --post-oracles transition_micrographs/hypo3d_l4_v2/post_state_oracles.v2_3.jsonl \
    --target-resolutions "${targets}" \
    --object-catalog "${catalog}" \
    --output reports/hypo3d_l4_v2/provisional_mirror_v2 \
    --run-id hypo3d_provisional_coverage_v2
