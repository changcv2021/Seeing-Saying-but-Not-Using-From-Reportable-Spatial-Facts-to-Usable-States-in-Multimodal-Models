#!/bin/bash
#SBATCH --job-name=hypo3d_sr3d_audit
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=runs/hypo3d_sr3d_audit_%j.out
#SBATCH --error=runs/hypo3d_sr3d_audit_%j.err

set -euo pipefail

project_dir="./SpaceConflict"
source_root="external/upstream/data/full_media_incoming/hypo3d/official/referit3d_725a5d3"

cd "${project_dir}"
module load python/3.12.11

PYTHONPATH=src srun python scripts/audit_hypo3d_sr3d_coverage.py \
    --sr3d "${source_root}/sr3d_plus.csv" \
    --branches data/canonical/hypo3d_l4_v2/branches.jsonl \
    --parsed transition_micrographs/hypo3d_l4_v2/parsed_changes.v2_1.jsonl \
    --oracles transition_micrographs/hypo3d_l4_v2/post_state_oracles.v2_3.jsonl \
    --resolutions transition_micrographs/hypo3d_l4_v2_official_3dssg_fusion_v2_5/target_resolutions.v2_5.jsonl \
    --current-prestates transition_micrographs/hypo3d_l4_v2_official_3dssg_fusion_v2_5/prestates.count_v2.jsonl \
    --nr3d-target-candidates reports/hypo3d_l4_v2/nr3d_coverage_v1/target_candidates.nr3d_v1.jsonl \
    --nr3d-count-candidates reports/hypo3d_l4_v2/nr3d_coverage_v1/count_candidates.nr3d_v1.jsonl \
    --catalog data/canonical/hypo3d_l4_v2_official_3dssg_fusion_v2_5/object_catalog.v2.json \
    --output-dir reports/hypo3d_l4_v2/sr3d_coverage_v1 \
    --run-id hypo3d_sr3d_coverage_v1 \
    --resume
