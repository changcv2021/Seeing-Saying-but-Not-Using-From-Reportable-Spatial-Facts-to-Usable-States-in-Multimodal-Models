#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-ca-full-validate
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=runs/ca_full_validate_%j.out
#SBATCH --error=runs/ca_full_validate_%j.err

set -euo pipefail
PROJECT_ROOT="./dataset"
DATA_ROOT="external/upstream/data/full_media_incoming/ca_vqa/080812355c21a40f437ed03d4ae558d35bfa2929"
module load python/3.12.11
cd "$PROJECT_ROOT"
srun python scripts/validate_ca_vqa_full_download.py \
    --download-run "$PROJECT_ROOT/runs/download_ca_vqa_slurm_8073172" \
    --data-root "$DATA_ROOT" \
    --output "$PROJECT_ROOT/reports/ca_vqa/download_validation.full_v1.json"
