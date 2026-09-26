#!/bin/bash
#SBATCH --job-name=embodiedscan_v1_catalog
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --output=runs/embodiedscan_v1_catalog_%j.out
#SBATCH --error=runs/embodiedscan_v1_catalog_%j.err

set -euo pipefail

project_dir="./dataset"
annotation_root="external/upstream/data/full_media_incoming/hypo3d/official/embodiedscan_v1/annotations"

cd "${project_dir}"
module load python/3.12.11

for split in train val test; do
    sha256sum --check "${annotation_root}/embodiedscan_infos_${split}.pkl.sha256"
done

PYTHONPATH=src srun python -m spaceconflict.cli hypo3d-l4 build-object-catalog \
    --catalog-source-type EMBODIEDSCAN_OFFICIAL_ANNOTATION \
    --embodiedscan-info "${annotation_root}/embodiedscan_infos_train.pkl" \
    --embodiedscan-info "${annotation_root}/embodiedscan_infos_val.pkl" \
    --embodiedscan-info "${annotation_root}/embodiedscan_infos_test.pkl" \
    --output data/canonical/hypo3d_l4_v2_official \
    --run-id embodiedscan_v1_official_catalog_v2
