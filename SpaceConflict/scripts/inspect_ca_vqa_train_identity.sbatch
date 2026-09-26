#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-ca-identity
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:05:00
#SBATCH --output=runs/ca_train_identity_%j.out
#SBATCH --error=runs/ca_train_identity_%j.err

set -euo pipefail
PROJECT_ROOT="./SpaceConflict"
DATA_ROOT="external/upstream/data/full_media_incoming/ca_vqa/080812355c21a40f437ed03d4ae558d35bfa2929/train"
REVISION="080812355c21a40f437ed03d4ae558d35bfa2929"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun python scripts/inspect_ca_vqa_train_identity.py \
    --binary "$DATA_ROOT/cavqa_binary/1.0.0/cavqa_binary-train.tfrecord-00000-of-01024" \
    --multichoice "$DATA_ROOT/cavqa_multichoice/1.0.0/cavqa_multichoice-train.tfrecord-00000-of-01024" \
    --limit 64 --source-revision "$REVISION" \
    --official-readme "$PROJECT_ROOT/upstream/ml-cubifyanything/README.md" \
    --output "$PROJECT_ROOT/reports/ca_vqa/train_identity_preflight.v1.json"
