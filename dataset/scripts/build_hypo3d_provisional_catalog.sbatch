#!/bin/bash
#SBATCH --job-name=hypo3d_provisional_catalog
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=runs/hypo3d_provisional_catalog_%j.out
#SBATCH --error=runs/hypo3d_provisional_catalog_%j.err

set -euo pipefail

project_dir="./dataset"
revision="92dce5f88311537eddbafc0e38fe122a588c9d8a"
mirror_root="external/upstream/data/full_media_incoming/hypo3d/unverified_mirror/PoopBear_3D-IDE-data_${revision}/embodiedscan"

cd "${project_dir}"
module load python/3.12.11

for split in train val test; do
    pkl="${mirror_root}/embodiedscan_infos_${split}.pkl"
    md5_file="${pkl}.md5"
    test -f "${pkl}"
    test -f "${md5_file}"
    md5sum --check "${md5_file}"
done

PYTHONPATH=src srun python -m spaceconflict.cli hypo3d-l4 build-object-catalog \
    --catalog-source-type UNVERIFIED_THIRD_PARTY_MIRROR \
    --embodiedscan-info "${mirror_root}/embodiedscan_infos_train.pkl" \
    --embodiedscan-info "${mirror_root}/embodiedscan_infos_val.pkl" \
    --embodiedscan-info "${mirror_root}/embodiedscan_infos_test.pkl" \
    --output data/canonical/hypo3d_l4_v2_provisional_mirror \
    --run-id hypo3d_provisional_catalog_mirror_v2
