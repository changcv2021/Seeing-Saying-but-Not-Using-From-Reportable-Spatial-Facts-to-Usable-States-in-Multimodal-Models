#!/bin/bash
#SBATCH --job-name=l4_three_part_full
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=runs/l4_three_part_full_%j.out
#SBATCH --error=runs/l4_three_part_full_%j.err

set -euo pipefail

project_dir="./dataset"
cd "${project_dir}"
module load python/3.12.11

PYTHONPATH=src srun python scripts/build_l4_three_part.py build-controlled-full \
    --run-id l4_v3_controlled_full_20260829

PYTHONPATH=src srun python scripts/build_l4_three_part.py build-unknown \
    --run-id l4_v3_unknown_20260829

PYTHONPATH=src srun python scripts/build_l4_three_part.py build-release \
    --run-id l4_v3_release_20260829

PYTHONPATH=src srun pytest -q tests/test_l4_three_part_v3.py
