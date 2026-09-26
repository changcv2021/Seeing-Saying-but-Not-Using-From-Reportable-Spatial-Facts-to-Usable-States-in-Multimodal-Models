#!/bin/bash
#SBATCH --job-name=hypo3d_sr3d_dl
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:30:00
#SBATCH --output=runs/hypo3d_sr3d_download_%j.out
#SBATCH --error=runs/hypo3d_sr3d_download_%j.err

set -euo pipefail

destination="external/upstream/data/full_media_incoming/hypo3d/official/referit3d_725a5d3"
mkdir -p "${destination}"

download_file() {
    local file_id="$1"
    local name="$2"
    local output="${destination}/${name}"
    if [[ ! -s "${output}" ]]; then
        curl --fail --location --retry 8 --retry-all-errors \
            "https://drive.usercontent.google.com/download?id=${file_id}&export=download&confirm=t" \
            --output "${output}.part"
        mv "${output}.part" "${output}"
    fi
    file "${output}"
    wc -c "${output}"
    sha256sum "${output}"
}

download_file "1pTmzEuE8PxSRR1gYY8o7AKc9E9BrLDDU" "sr3d.csv"
download_file "1kcxscHp8yA_iKLT3BdTNghlY3SBfKAQI" "sr3d_plus.csv"
