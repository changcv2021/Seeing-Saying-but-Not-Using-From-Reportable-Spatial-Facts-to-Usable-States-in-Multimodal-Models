#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-ca-train-adapt
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:10:00
#SBATCH --output=runs/ca_train_adapter_%j.out
#SBATCH --error=runs/ca_train_adapter_%j.err

set -euo pipefail
PROJECT_ROOT="./SpaceConflict"
DATA_ROOT="external/upstream/data/full_media_incoming/ca_vqa/080812355c21a40f437ed03d4ae558d35bfa2929"
REVISION="080812355c21a40f437ed03d4ae558d35bfa2929"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src python scripts/extract_ca_vqa_train_pilot.py \
    --root "$PROJECT_ROOT" --data-root "$DATA_ROOT" \
    --download-results "$PROJECT_ROOT/runs/download_ca_vqa_slurm_8073172/results.tsv" \
    --download-results "$PROJECT_ROOT/runs/ca_vqa_task_pilot_8074166/results.tsv" \
    --binary "$DATA_ROOT/train/cavqa_binary/1.0.0/cavqa_binary-train.tfrecord-00000-of-01024" \
    --cardinality "$DATA_ROOT/train/cavqa_cardinality/1.0.0/cavqa_cardinality-train.tfrecord-00000-of-01024" \
    --multichoice "$DATA_ROOT/train/cavqa_multichoice/1.0.0/cavqa_multichoice-train.tfrecord-00000-of-01024" \
    --source-revision "$REVISION" \
    --official-readme "$PROJECT_ROOT/upstream/ml-cubifyanything/README.md" \
    --record-limit 4 --seed 20260826 --run-id "ca_train_pilot_${SLURM_JOB_ID}" --resume
