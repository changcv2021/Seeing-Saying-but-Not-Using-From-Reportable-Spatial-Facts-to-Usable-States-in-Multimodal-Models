#!/bin/bash
#SBATCH --job-name=hypo3d_official_l4_verify
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:30:00
#SBATCH --output=runs/hypo3d_official_l4_verify_%j.out
#SBATCH --error=runs/hypo3d_official_l4_verify_%j.err

set -euo pipefail

project_dir="./dataset"
media_root="external/upstream/data/full_media_incoming/hypo3d/ffb21ab198e8d666b63e062d931ed33b60c67d0f"

cd "${project_dir}"
module load python/3.12.11

PYTHONPATH=src srun python -m spaceconflict.cli hypo3d-l4 verify \
    --branch-index data/canonical/hypo3d_l4_v2/branches.jsonl \
    --post-oracles transition_micrographs/hypo3d_l4_v2/post_state_oracles.v2_3.jsonl \
    --prestates transition_micrographs/hypo3d_l4_v2_official/prestates.count_v2.jsonl \
    --pairs claim_graphs/hypo3d_l4_v2_official/pairs.count_l4_core_v2.jsonl \
    --media-root "${media_root}" \
    --output accepted/hypo3d_l4_v2_official \
    --run-id hypo3d_official_l4_final_verify_v2
