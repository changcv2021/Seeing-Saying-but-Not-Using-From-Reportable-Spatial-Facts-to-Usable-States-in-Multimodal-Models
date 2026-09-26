#!/bin/bash
#SBATCH --job-name=l4_three_part_pilot
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=runs/l4_three_part_pilot_%j.out
#SBATCH --error=runs/l4_three_part_pilot_%j.err

set -euo pipefail

project_dir="./SpaceConflict"
cd "${project_dir}"
module load python/3.12.11

PYTHONPATH=src srun pytest -q tests/test_l4_three_part_v3.py

PYTHONPATH=src srun python scripts/build_l4_three_part.py freeze-native \
    --run-id l4_v3_freeze_native_20260829

PYTHONPATH=src srun python scripts/build_l4_three_part.py build-native \
    --run-id l4_v3_build_native_20260829

PYTHONPATH=src srun python scripts/build_l4_three_part.py build-controlled-pilot \
    --run-id l4_v3_controlled_pilot_20260829
