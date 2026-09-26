#!/bin/bash
#SBATCH --job-name=embodiedscan_v1_download
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:30:00
#SBATCH --output=runs/embodiedscan_v1_download_%j.out
#SBATCH --error=runs/embodiedscan_v1_download_%j.err

set -euo pipefail

file_id="12LDl994fi7YyDcOXErMv-0s7LT2DxFoS"
source_url="https://drive.usercontent.google.com/download?id=${file_id}&export=download&confirm=t"
target_dir="external/upstream/data/full_media_incoming/hypo3d/official/embodiedscan_v1"
archive="${target_dir}/embodiedscan.zip"
partial="${archive}.part"
expected_bytes="304465812"

mkdir -p "${target_dir}/annotations"

if [[ ! -f "${archive}" ]]; then
    curl --fail --location --retry 8 --retry-all-errors --continue-at - \
        --dump-header "${target_dir}/download_headers.txt" \
        --output "${partial}" "${source_url}"
    actual_bytes="$(stat -c '%s' "${partial}")"
    if [[ "${actual_bytes}" != "${expected_bytes}" ]]; then
        echo "EmbodiedScan v1 archive has unexpected size: ${actual_bytes}; expected ${expected_bytes}" >&2
        exit 2
    fi
    mv "${partial}" "${archive}"
fi

actual_bytes="$(stat -c '%s' "${archive}")"
if [[ "${actual_bytes}" != "${expected_bytes}" ]]; then
    echo "Existing EmbodiedScan v1 archive has unexpected size: ${actual_bytes}; expected ${expected_bytes}" >&2
    exit 3
fi
sha256sum "${archive}" > "${archive}.sha256"
unzip -Z1 "${archive}" > "${target_dir}/archive_members.txt"

extract_one() {
    local basename="$1"
    local member
    local count
    count="$(awk -v suffix="/${basename}" -v exact="${basename}" '{pos=index($0, suffix)} ($0 == exact) || (pos > 0 && pos == length($0) - length(suffix) + 1) {n++} END {print n+0}' "${target_dir}/archive_members.txt")"
    if [[ "${count}" != "1" ]]; then
        echo "Expected exactly one ${basename} archive member; found ${count}" >&2
        exit 4
    fi
    member="$(awk -v suffix="/${basename}" -v exact="${basename}" '{pos=index($0, suffix)} ($0 == exact) || (pos > 0 && pos == length($0) - length(suffix) + 1) {print}' "${target_dir}/archive_members.txt")"
    unzip -p "${archive}" "${member}" > "${target_dir}/annotations/${basename}.part"
    test -s "${target_dir}/annotations/${basename}.part"
    mv "${target_dir}/annotations/${basename}.part" "${target_dir}/annotations/${basename}"
    sha256sum "${target_dir}/annotations/${basename}" > "${target_dir}/annotations/${basename}.sha256"
}

extract_one "embodiedscan_infos_train.pkl"
extract_one "embodiedscan_infos_val.pkl"
extract_one "embodiedscan_infos_test.pkl"

printf '%s\n' \
    'source_type=EMBODIEDSCAN_OFFICIAL_ANNOTATION' \
    'release=EmbodiedScan_v1' \
    "google_drive_file_id=${file_id}" \
    "archive_bytes=${expected_bytes}" \
    'access_basis=official_team_email_response_2026-08-29' \
    > "${target_dir}/SOURCE_RECEIPT.txt"
