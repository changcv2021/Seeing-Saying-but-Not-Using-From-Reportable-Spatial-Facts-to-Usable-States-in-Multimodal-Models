#!/bin/bash
#SBATCH --job-name=hypo3d_llm_profile
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:15:00
#SBATCH --output=runs/hypo3d_llm_profile_%j.out
#SBATCH --error=runs/hypo3d_llm_profile_%j.err

set -euo pipefail

project_dir="./SpaceConflict"
llm_root="external/upstream/data/full_media_incoming/hypo3d/official/matchlab_dataset_fb6101e/LLM_data"

cd "${project_dir}"
module load python/3.12.11

PYTHONPATH=src srun python scripts/profile_hypo3d_llm_data.py \
    --rscan "${llm_root}/3rscan_scene_cap.json" \
    --nr3d "${llm_root}/nr3d_captions_by_scene.pkl" \
    --scanrefer "${llm_root}/scanrefer_captions_by_scene.pkl" \
    --output reports/hypo3d_l4_v2/llm_data_profile_v1/report.llm_data_profile_v1.json \
    --run-id hypo3d_llm_data_profile_v1
