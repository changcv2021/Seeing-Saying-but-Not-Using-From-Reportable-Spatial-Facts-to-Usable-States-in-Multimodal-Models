#!/bin/bash
#SBATCH --job-name=hypo3d_annotation_mirror
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=01:00:00
#SBATCH --output=runs/hypo3d_annotation_mirror_%j.out
#SBATCH --error=runs/hypo3d_annotation_mirror_%j.err

set -euo pipefail

revision="92dce5f88311537eddbafc0e38fe122a588c9d8a"
source_url="https://huggingface.co/datasets/PoopBear/3D-IDE-data/resolve/${revision}/3d_ide_data.zip"
target_dir="external/upstream/data/full_media_incoming/hypo3d/unverified_mirror/PoopBear_3D-IDE-data_${revision}"
archive="${target_dir}/3d_ide_data.zip"
partial="${archive}.part"
expected_bytes="4560256278"
expected_sha256="caeaae48613dfb3ded4ef3a06f63d89341e009a1dbf8f197e473fade2a485c21"

mkdir -p "${target_dir}/embodiedscan"

if [[ ! -f "${archive}" ]]; then
    curl --fail --location --retry 8 --retry-all-errors --continue-at - \
        --output "${partial}" "${source_url}"
    actual_bytes="$(stat -c '%s' "${partial}")"
    if [[ "${actual_bytes}" != "${expected_bytes}" ]]; then
        echo "Mirror archive has unexpected size: ${actual_bytes}; expected ${expected_bytes}" >&2
        exit 2
    fi
    actual_sha256="$(sha256sum "${partial}" | cut -d' ' -f1)"
    if [[ "${actual_sha256}" != "${expected_sha256}" ]]; then
        echo "Mirror archive SHA256 mismatch" >&2
        exit 3
    fi
    mv "${partial}" "${archive}"
else
    echo "${expected_sha256}  ${archive}" | sha256sum --check
fi
unzip -Z1 "${archive}" > "${target_dir}/archive_members.txt"

extract_one() {
    local basename="$1"
    local expected_md5="$2"
    local member
    local count
    count="$(awk -v suffix="/${basename}" '{pos=index($0, suffix)} pos > 0 && pos == length($0) - length(suffix) + 1 {n++} END {print n+0}' "${target_dir}/archive_members.txt")"
    if [[ "${count}" != "1" ]]; then
        echo "Expected exactly one ${basename} archive member; found ${count}" >&2
        exit 4
    fi
    member="$(awk -v suffix="/${basename}" '{pos=index($0, suffix)} pos > 0 && pos == length($0) - length(suffix) + 1 {print}' "${target_dir}/archive_members.txt")"
    unzip -p "${archive}" "${member}" > "${target_dir}/embodiedscan/${basename}.part"
    actual_md5="$(md5sum "${target_dir}/embodiedscan/${basename}.part" | cut -d' ' -f1)"
    if [[ "${actual_md5}" != "${expected_md5}" ]]; then
        echo "${basename} MD5 mismatch" >&2
        exit 5
    fi
    mv "${target_dir}/embodiedscan/${basename}.part" "${target_dir}/embodiedscan/${basename}"
    echo "${expected_md5}  ${target_dir}/embodiedscan/${basename}" > "${target_dir}/embodiedscan/${basename}.md5"
}

extract_one "embodiedscan_infos_train.pkl" "c5762140b0d8e625d890ef47f75b14be"
extract_one "embodiedscan_infos_val.pkl" "2ac5abf65d8b56dec5347d279c470b56"
extract_one "embodiedscan_infos_test.pkl" "b9693cf5e4ae5fd4fb23f27f7d1e7050"

echo "Downloaded from an unverified third-party mirror; do not unpickle or promote as official source truth until official checksums match." > "${target_dir}/QUARANTINE.txt"
