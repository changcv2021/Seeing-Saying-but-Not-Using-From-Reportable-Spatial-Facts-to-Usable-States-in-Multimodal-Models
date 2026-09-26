#!/bin/bash
#SBATCH --job-name=hypo3d_nr3d_dl
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:30:00
#SBATCH --output=runs/hypo3d_nr3d_download_%j.out
#SBATCH --error=runs/hypo3d_nr3d_download_%j.err

set -euo pipefail

destination="external/upstream/data/full_media_incoming/hypo3d/official/referit3d_725a5d3"
file_id="1qswKclq4BlnHSGMSgzLmUu8iqdUXD8ZC"
archive="${destination}/nr3d_official_download"

mkdir -p "${destination}"
if [[ ! -s "${archive}" ]]; then
    curl --fail --location --retry 8 --retry-all-errors \
        "https://drive.usercontent.google.com/download?id=${file_id}&export=download&confirm=t" \
        --output "${archive}.part"
    mv "${archive}.part" "${archive}"
fi

file "${archive}"
wc -c "${archive}"
sha256sum "${archive}"
