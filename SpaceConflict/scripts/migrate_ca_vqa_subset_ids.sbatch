#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-ca-id-migrate
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:10:00
#SBATCH --output=runs/ca_subset_id_migrate_%j.out
#SBATCH --error=runs/ca_subset_id_migrate_%j.err

set -euo pipefail
PROJECT_ROOT="./SpaceConflict"
REVISION="080812355c21a40f437ed03d4ae558d35bfa2929"
module load python/3.12.11
cd "$PROJECT_ROOT"

for task in binary cardinality; do
    srun env PYTHONPATH=src python scripts/migrate_ca_vqa_subset_ids.py \
        --root "$PROJECT_ROOT" --source-revision "$REVISION" --task "$task" \
        --seed 20260826 --run-id "ca_subset_id_migrate_${task}_${SLURM_JOB_ID}" --resume
done
