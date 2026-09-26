#!/bin/bash
#SBATCH --job-name=embodiedscan_v2_catalog_audit
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=24G
#SBATCH --time=00:30:00
#SBATCH --output=runs/embodiedscan_v2_catalog_audit_%j.out
#SBATCH --error=runs/embodiedscan_v2_catalog_audit_%j.err

set -euo pipefail

project_dir="./SpaceConflict"
v2_root="external/upstream/data/full_media_incoming/hypo3d/official/embodiedscan_v2_beta/extracted/embodiedscan-v2"

cd "${project_dir}"
module load python/3.12.11

PYTHONPATH=src srun python -m spaceconflict.cli hypo3d-l4 build-object-catalog \
    --catalog-source-type EMBODIEDSCAN_OFFICIAL_ANNOTATION \
    --embodiedscan-info "${v2_root}/embodiedscan_infos_train.pkl" \
    --embodiedscan-info "${v2_root}/embodiedscan_infos_val.pkl" \
    --embodiedscan-info "${v2_root}/embodiedscan_infos_test.pkl" \
    --output data/canonical/hypo3d_l4_v2_official_v2_beta_catalog_audit_v1 \
    --run-id embodiedscan_v2_beta_official_catalog_audit_v1
