#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-ca-prod-extract
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=3
#SBATCH --mem=24G
#SBATCH --time=02:00:00
#SBATCH --output=runs/ca_train_production_extract_%j.out
#SBATCH --error=runs/ca_train_production_extract_%j.err

set -euo pipefail
PROJECT_ROOT="./SpaceConflict"
DATA_ROOT="external/upstream/data/full_media_incoming/ca_vqa/080812355c21a40f437ed03d4ae558d35bfa2929"
REVISION="080812355c21a40f437ed03d4ae558d35bfa2929"
MANIFEST="$PROJECT_ROOT/data/manifests/ca_vqa/$REVISION/production_subset_shards_v1.jsonl"
RESULTS="$PROJECT_ROOT/runs/download_ca_vqa_slurm_8073172/results.tsv"
module load python/3.12.11
cd "$PROJECT_ROOT"

pids=()
for task in binary cardinality multichoice; do
    srun --exclusive -N1 -n1 -c1 env PYTHONPATH=src python scripts/extract_ca_vqa_train_subset.py \
        --root "$PROJECT_ROOT" --data-root "$DATA_ROOT" --selection-manifest "$MANIFEST" \
        --download-results "$RESULTS" --source-revision "$REVISION" --task "$task" \
        --candidate-cap-per-world 8 --seed 20260826 \
        --run-id "ca_train_production_${task}_${SLURM_JOB_ID}" --resume &
    pids+=("$!")
done
for pid in "${pids[@]}"; do
    wait "$pid"
done

srun -N1 -n1 -c1 env PYTHONPATH=src python scripts/combine_ca_vqa_train_subset.py \
    --root "$PROJECT_ROOT" --source-revision "$REVISION" --world-cap 1000 --seed 20260826 \
    --run-id "ca_train_production_combine_${SLURM_JOB_ID}" --resume
