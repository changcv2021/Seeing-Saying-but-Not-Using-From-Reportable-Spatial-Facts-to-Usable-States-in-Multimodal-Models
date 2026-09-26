#!/bin/bash
#SBATCH --job-name=hypo3d_ref3d_v28
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=runs/hypo3d_referit3d_v2_8_%j.out
#SBATCH --error=runs/hypo3d_referit3d_v2_8_%j.err

set -euo pipefail

project_dir="./SpaceConflict"
work="transition_micrographs/hypo3d_l4_v2_official_referit3d_fusion_v2_7"
claims="claim_graphs/hypo3d_l4_v2_official_referit3d_fusion_v2_7"
accepted="accepted/hypo3d_l4_v2_official_referit3d_fusion_v2_8"
media_root="external/upstream/data/full_media_incoming/hypo3d/ffb21ab198e8d666b63e062d931ed33b60c67d0f"

cd "${project_dir}"
module load python/3.12.11

PYTHONPATH=src srun python -m spaceconflict.cli hypo3d-l4 verify \
    --branch-index data/canonical/hypo3d_l4_v2/branches.jsonl \
    --post-oracles transition_micrographs/hypo3d_l4_v2/post_state_oracles.v2_3.jsonl \
    --prestates "${work}/prestates.count_v2.jsonl" \
    --pairs "${claims}/pairs.count_l4_core_v2.jsonl" \
    --media-root "${media_root}" \
    --output "${accepted}" \
    --run-id hypo3d_referit3d_final_verify_v2_8

PYTHONPATH=src srun pytest -q
