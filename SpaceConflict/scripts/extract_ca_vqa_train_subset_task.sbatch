#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-ca-subset-task
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=runs/ca_train_subset_task_%j.out
#SBATCH --error=runs/ca_train_subset_task_%j.err

set -euo pipefail
: "${TASK:?submit with --export=ALL,TASK=binary|cardinality|multichoice}"
PROJECT_ROOT="./SpaceConflict"
DATA_ROOT="external/upstream/data/full_media_incoming/ca_vqa/080812355c21a40f437ed03d4ae558d35bfa2929"
REVISION="080812355c21a40f437ed03d4ae558d35bfa2929"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src python scripts/extract_ca_vqa_train_subset.py \
    --root "$PROJECT_ROOT" --data-root "$DATA_ROOT" \
    --selection-manifest "$PROJECT_ROOT/data/manifests/ca_vqa/$REVISION/production_subset_shards_v1.jsonl" \
    --download-results "$PROJECT_ROOT/runs/download_ca_vqa_slurm_8073172/results.tsv" \
    --source-revision "$REVISION" --task "$TASK" --candidate-cap-per-world 8 \
    --seed 20260826 --run-id "ca_train_subset_${TASK}_${SLURM_JOB_ID}" --resume
