#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-ca-val
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=04:00:00
#SBATCH --output=runs/ca_vqa_val_%j.out
#SBATCH --error=runs/ca_vqa_val_%j.err

set -euo pipefail

PROJECT_ROOT="./SpaceConflict"
DATA_ROOT="external/upstream/data/full_media_incoming/ca_vqa/080812355c21a40f437ed03d4ae558d35bfa2929"
DOWNLOAD_RUN="${PROJECT_ROOT}/runs/download_ca_vqa_slurm_8073172"
RUN_DIR="${PROJECT_ROOT}/runs/ca_vqa_val_${SLURM_JOB_ID:-manual}"
URL="https://ml-site.cdn-apple.com/datasets/cavqa/val/cavqa_val.tar.gz"
EXPECTED=31650263144
ARCHIVE="${DATA_ROOT}/val/cavqa_val.tar.gz"
PARTIAL="${ARCHIVE}.valpilot.part"
EXTRACTED="${DATA_ROOT}/val/cavqa_val_extracted"
TEMP_EXTRACT="${DATA_ROOT}/val/cavqa_val_extracted.${SLURM_JOB_ID:-manual}.tmp"
OUTPUT="${PROJECT_ROOT}/reports/ca_vqa/profile.val_v1.json"
mkdir -p "$RUN_DIR" "$(dirname "$ARCHIVE")"

if [[ ! -f "$ARCHIVE" ]] || [[ "$(stat -c '%s' "$ARCHIVE")" != "$EXPECTED" ]]; then
    curl --location --fail --silent --show-error --retry 20 --retry-all-errors --retry-delay 10 \
        --connect-timeout 30 --continue-at - --output "$PARTIAL" "$URL"
    [[ "$(stat -c '%s' "$PARTIAL")" == "$EXPECTED" ]]
    sha256sum "$PARTIAL" >"${RUN_DIR}/archive.sha256"
    mv -- "$PARTIAL" "$ARCHIVE"
    chmod 400 "$ARCHIVE"
else
    sha256sum "$ARCHIVE" >"${RUN_DIR}/archive.sha256"
fi

tar -tzf "$ARCHIVE" >"${RUN_DIR}/inventory.txt"
if awk 'BEGIN{bad=0} /^\// || /(^|\/)\.\.($|\/)/ {bad=1} END{exit bad}' "${RUN_DIR}/inventory.txt"; then :; else
    printf '%s\n' 'Unsafe archive member detected.' >&2
    exit 1
fi
if [[ ! -d "$EXTRACTED" ]]; then
    mkdir -p "$TEMP_EXTRACT"
    tar -xzf "$ARCHIVE" -C "$TEMP_EXTRACT"
    mv -- "$TEMP_EXTRACT" "$EXTRACTED"
fi

module load python/3.12.11
cd "$PROJECT_ROOT"
python scripts/profile_ca_vqa_val.py --extracted-root "$EXTRACTED" --archive "$ARCHIVE" \
    --inventory "${RUN_DIR}/inventory.txt" --output "$OUTPUT"
