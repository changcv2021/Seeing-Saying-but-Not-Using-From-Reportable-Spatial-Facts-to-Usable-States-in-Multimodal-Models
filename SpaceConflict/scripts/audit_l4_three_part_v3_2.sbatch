#!/bin/bash
#SBATCH --job-name=l4_three_part_audit
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=runs/l4_three_part_audit_%j.out
#SBATCH --error=runs/l4_three_part_audit_%j.err

set -euo pipefail

project_dir="./SpaceConflict"
media_root="external/upstream/data/full_media_incoming/hypo3d/ffb21ab198e8d666b63e062d931ed33b60c67d0f"
cd "${project_dir}"
module load python/3.12.11

PYTHONPATH=src srun pytest -q

PYTHONPATH=src srun python scripts/audit_l4_three_part_release.py \
    --release-root "${project_dir}/l4/v3_2/release" \
    --media-root "${media_root}" \
    --output "${project_dir}/reports/hypo3d_l4_v3/final_audit.v3_2.json"
