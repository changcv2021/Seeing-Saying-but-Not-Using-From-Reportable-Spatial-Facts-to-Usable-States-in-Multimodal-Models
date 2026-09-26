#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-ca-meta
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=runs/ca_vqa_meta_%j.out
#SBATCH --error=runs/ca_vqa_meta_%j.err

set -euo pipefail

PROJECT_ROOT="./SpaceConflict"
SOURCE_REVISION="080812355c21a40f437ed03d4ae558d35bfa2929"
VAL_ROOT="external/upstream/data/full_media_incoming/ca_vqa/${SOURCE_REVISION}/val"
EXTRACTED="${VAL_ROOT}/cavqa_val_extracted"
ARCHIVE="${VAL_ROOT}/cavqa_val.tar.gz"
ARCHIVE_SHA="${PROJECT_ROOT}/runs/ca_vqa_val_8074254/archive.sha256"

module load python/3.12.11
cd "$PROJECT_ROOT"
srun python scripts/extract_ca_vqa_val_metadata.py \
    --extracted-root "$EXTRACTED" \
    --project-root "$PROJECT_ROOT" \
    --source-revision "$SOURCE_REVISION" \
    --archive "$ARCHIVE" \
    --archive-sha256-file "$ARCHIVE_SHA" \
    --resume
