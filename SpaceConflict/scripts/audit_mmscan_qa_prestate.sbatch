#!/bin/bash
#SBATCH --job-name=mmscan_qa_prestate
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=64G
#SBATCH --time=00:30:00
#SBATCH --output=runs/mmscan_qa_prestate_%j.out
#SBATCH --error=runs/mmscan_qa_prestate_%j.err

set -euo pipefail

project_dir="./SpaceConflict"
qa="external/upstream/data/full_media_incoming/hypo3d/official/embodiedscan_v2_beta/extracted/MMScan-beta/MMScan_samples/MMScan_QA.json"

cd "${project_dir}"
module load python/3.12.11

PYTHONPATH=src srun python scripts/audit_mmscan_qa_prestate.py \
    --qa "${qa}" \
    --catalog data/canonical/hypo3d_l4_v2_official_geometry_v2_1/object_catalog.v2.json \
    --output-dir reports/hypo3d_l4_v2/mmscan_qa_prestate_v1 \
    --run-id mmscan_qa_prestate_v1
