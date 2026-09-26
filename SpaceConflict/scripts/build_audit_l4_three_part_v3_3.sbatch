#!/bin/bash
#SBATCH --job-name=l4_three_part_v33
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=runs/l4_three_part_v3_3_%j.out
#SBATCH --error=runs/l4_three_part_v3_3_%j.err

set -euo pipefail

project_dir="./SpaceConflict"
output_root="${project_dir}/l4/v3_3"
media_root="external/upstream/data/full_media_incoming/hypo3d/ffb21ab198e8d666b63e062d931ed33b60c67d0f"
cd "${project_dir}"
module load python/3.12.11

PYTHONPATH=src srun pytest -q

PYTHONPATH=src srun python scripts/build_l4_three_part.py freeze-native \
    --output-root "${output_root}" \
    --run-id l4_v3_3_freeze_native_20260829

PYTHONPATH=src srun python scripts/build_l4_three_part.py build-native \
    --output-root "${output_root}" \
    --run-id l4_v3_3_build_native_20260829

PYTHONPATH=src srun python scripts/build_l4_three_part.py build-controlled-full \
    --output-root "${output_root}" \
    --run-id l4_v3_3_controlled_full_20260829

PYTHONPATH=src srun python scripts/build_l4_three_part.py build-unknown \
    --output-root "${output_root}" \
    --run-id l4_v3_3_unknown_20260829

PYTHONPATH=src srun python scripts/build_l4_three_part.py build-release \
    --output-root "${output_root}" \
    --run-id l4_v3_3_release_20260829

PYTHONPATH=src srun python scripts/audit_l4_three_part_release.py \
    --release-root "${output_root}/release" \
    --media-root "${media_root}" \
    --output "${project_dir}/reports/hypo3d_l4_v3/final_audit.v3_3.json"

PYTHONPATH=src srun pytest -q
