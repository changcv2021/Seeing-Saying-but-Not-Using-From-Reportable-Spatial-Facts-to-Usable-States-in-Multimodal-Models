#!/bin/bash
#SBATCH --job-name=embodiedscan_v2_beta_extract
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:30:00
#SBATCH --output=runs/embodiedscan_v2_beta_extract_%j.out
#SBATCH --error=runs/embodiedscan_v2_beta_extract_%j.err

set -euo pipefail

target_dir="external/upstream/data/full_media_incoming/hypo3d/official/embodiedscan_v2_beta"
archive="${target_dir}/embodiedscan_v2_beta.zip"
extracted="${target_dir}/extracted"

test -f "${archive}"
if awk 'BEGIN {bad=0} /(^|\/)\.\.($|\/)|^\// {bad=1} END {exit bad ? 0 : 1}' "${target_dir}/archive_members.txt"; then
    echo "Unsafe archive member path detected" >&2
    exit 2
fi

if [[ ! -d "${extracted}" ]]; then
    mkdir "${extracted}"
    unzip -q "${archive}" -d "${extracted}"
fi

find "${extracted}" -type f -print0 | sort -z | xargs -0 sha256sum > "${target_dir}/extracted_files.sha256"
find "${extracted}" -type f -printf '%P|%s\n' | sort > "${target_dir}/extracted_files.sizes"
cat "${target_dir}/extracted_files.sizes"
