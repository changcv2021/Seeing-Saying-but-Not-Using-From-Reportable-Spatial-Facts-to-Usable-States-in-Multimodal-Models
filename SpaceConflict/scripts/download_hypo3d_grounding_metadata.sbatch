#!/bin/bash
#SBATCH --job-name=hypo3d_grounding
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:30:00
#SBATCH --output=runs/hypo3d_grounding_%j.out
#SBATCH --error=runs/hypo3d_grounding_%j.err

set -euo pipefail

target_dir="external/upstream/data/full_media_incoming/hypo3d/embodiedscan_grounding"
target_file="${target_dir}/embodiedscan_infos_full_updated.json"
partial_file="${target_file}.part"
source_url="https://drive.usercontent.google.com/download?id=1F9EimpVtAjoGWSH6tH5qD5R9wzpzQPIX&export=download&confirm=t"
expected_bytes="823155085"

mkdir -p "${target_dir}"

if [[ -f "${target_file}" ]]; then
    actual_bytes="$(stat -c '%s' "${target_file}")"
    if [[ "${actual_bytes}" == "${expected_bytes}" ]]; then
        sha256sum "${target_file}" > "${target_file}.sha256"
        exit 0
    fi
    echo "Existing target has unexpected size: ${actual_bytes}" >&2
    exit 2
fi

curl --fail --location --retry 8 --retry-all-errors --continue-at - \
    --output "${partial_file}" "${source_url}"

actual_bytes="$(stat -c '%s' "${partial_file}")"
if [[ "${actual_bytes}" != "${expected_bytes}" ]]; then
    echo "Downloaded file has unexpected size: ${actual_bytes}; expected ${expected_bytes}" >&2
    exit 3
fi

mv "${partial_file}" "${target_file}"
sha256sum "${target_file}" > "${target_file}.sha256"

