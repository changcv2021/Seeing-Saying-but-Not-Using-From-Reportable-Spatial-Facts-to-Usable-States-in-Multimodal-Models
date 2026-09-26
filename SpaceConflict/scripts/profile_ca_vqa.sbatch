#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-ca-profile
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:10:00
#SBATCH --output=runs/ca_vqa_profile_%j.out
#SBATCH --error=runs/ca_vqa_profile_%j.err

set -euo pipefail

PROJECT_ROOT="./SpaceConflict"
DATA_ROOT="external/upstream/data/full_media_incoming/ca_vqa/080812355c21a40f437ed03d4ae558d35bfa2929"
DOWNLOAD_RUN="${PROJECT_ROOT}/runs/download_ca_vqa_slurm_8073172"
OUTPUT="${PROJECT_ROOT}/reports/ca_vqa/profile.full_download_v1.json"

module load python/3.12.11
cd "$PROJECT_ROOT"
srun python scripts/profile_ca_vqa.py --data-root "$DATA_ROOT" --download-run "$DOWNLOAD_RUN" --output "$OUTPUT"
