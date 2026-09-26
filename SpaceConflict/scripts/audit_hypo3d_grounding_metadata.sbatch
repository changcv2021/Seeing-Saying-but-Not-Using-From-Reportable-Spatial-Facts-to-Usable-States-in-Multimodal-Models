#!/bin/bash
#SBATCH --job-name=hypo3d_grounding_audit
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=01:00:00
#SBATCH --output=runs/hypo3d_grounding_audit_%j.out
#SBATCH --error=runs/hypo3d_grounding_audit_%j.err

set -euo pipefail

project_dir="./SpaceConflict"
metadata="external/upstream/data/full_media_incoming/hypo3d/embodiedscan_grounding/embodiedscan_infos_full_updated.json"
expected_bytes="823155085"

actual_bytes="$(stat -c '%s' "${metadata}")"
if [[ "${actual_bytes}" != "${expected_bytes}" ]]; then
    echo "Grounding metadata has unexpected size: ${actual_bytes}; expected ${expected_bytes}" >&2
    exit 2
fi
sha256sum --check "${metadata}.sha256"

module load python/3.12.11
cd "${project_dir}"
srun env PYTHONPATH=src python -m spaceconflict.cli hypo3d-l4 audit-grounding \
    --grounding-metadata "${metadata}" \
    --output reports/hypo3d_l4_v2/grounding_v2 \
    --run-id grounding_audit_v2
