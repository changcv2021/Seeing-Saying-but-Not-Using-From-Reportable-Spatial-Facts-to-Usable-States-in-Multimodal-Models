#!/bin/bash
#SBATCH --job-name=embodiedscan_v2_beta_download
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:30:00
#SBATCH --output=runs/embodiedscan_v2_beta_download_%j.out
#SBATCH --error=runs/embodiedscan_v2_beta_download_%j.err

set -euo pipefail

file_id="13EZC2wB_aEQFJJDrOWyWBmojOdLCwpDB"
source_url="https://drive.usercontent.google.com/download?id=${file_id}&export=download&confirm=t"
target_dir="external/upstream/data/full_media_incoming/hypo3d/official/embodiedscan_v2_beta"
archive="${target_dir}/embodiedscan_v2_beta.zip"
partial="${archive}.part"
expected_bytes="367932947"

mkdir -p "${target_dir}"

if [[ ! -f "${archive}" ]]; then
    curl --fail --location --retry 8 --retry-all-errors --continue-at - \
        --dump-header "${target_dir}/download_headers.txt" \
        --output "${partial}" "${source_url}"
    actual_bytes="$(stat -c '%s' "${partial}")"
    if [[ "${actual_bytes}" != "${expected_bytes}" ]]; then
        echo "EmbodiedScan v2 beta archive has unexpected size: ${actual_bytes}; expected ${expected_bytes}" >&2
        exit 2
    fi
    mv "${partial}" "${archive}"
fi

actual_bytes="$(stat -c '%s' "${archive}")"
if [[ "${actual_bytes}" != "${expected_bytes}" ]]; then
    echo "Existing EmbodiedScan v2 beta archive has unexpected size: ${actual_bytes}; expected ${expected_bytes}" >&2
    exit 3
fi
sha256sum "${archive}" > "${archive}.sha256"
unzip -tq "${archive}"
unzip -Z1 "${archive}" > "${target_dir}/archive_members.txt"

printf '%s\n' \
    'source_type=EMBODIEDSCAN_OFFICIAL_ANNOTATION' \
    'release=EmbodiedScan_v2_beta' \
    "google_drive_file_id=${file_id}" \
    "archive_bytes=${expected_bytes}" \
    'access_basis=official_team_email_response_2026-08-29' \
    'initial_use=MMScan_grounding_and_relation_feasibility_audit' \
    > "${target_dir}/SOURCE_RECEIPT.txt"
