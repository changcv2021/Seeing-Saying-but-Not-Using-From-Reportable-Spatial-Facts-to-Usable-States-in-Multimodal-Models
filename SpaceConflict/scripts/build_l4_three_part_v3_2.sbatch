#!/bin/bash
#SBATCH --job-name=l4_three_part_v32
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=runs/l4_three_part_v3_2_%j.out
#SBATCH --error=runs/l4_three_part_v3_2_%j.err

set -euo pipefail

project_dir="./SpaceConflict"
output_root="${project_dir}/l4/v3_2"
cd "${project_dir}"
module load python/3.12.11

PYTHONPATH=src srun pytest -q tests/test_l4_three_part_v3.py

PYTHONPATH=src srun python scripts/build_l4_three_part.py freeze-native \
    --output-root "${output_root}" \
    --run-id l4_v3_2_freeze_native_20260829

PYTHONPATH=src srun python scripts/build_l4_three_part.py build-native \
    --output-root "${output_root}" \
    --run-id l4_v3_2_build_native_20260829

PYTHONPATH=src srun python scripts/build_l4_three_part.py build-controlled-full \
    --output-root "${output_root}" \
    --run-id l4_v3_2_controlled_full_20260829

PYTHONPATH=src srun python scripts/build_l4_three_part.py build-unknown \
    --output-root "${output_root}" \
    --run-id l4_v3_2_unknown_20260829

PYTHONPATH=src srun python scripts/build_l4_three_part.py build-release \
    --output-root "${output_root}" \
    --run-id l4_v3_2_release_20260829

PYTHONPATH=src srun pytest -q tests/test_l4_three_part_v3.py
