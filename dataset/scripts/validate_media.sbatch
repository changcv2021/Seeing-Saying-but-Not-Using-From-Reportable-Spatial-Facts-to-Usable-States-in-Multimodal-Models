#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-media
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=04:00:00

set -euo pipefail

PROJECT_ROOT="./dataset"
STORAGE_ROOT="external/upstream"
DATASET=""
DRY_RUN=0
RESUME=0
SEED=20260826
RUN_ID="media_slurm_${SLURM_JOB_ID:-manual}"
LIMIT=""
WORKERS=1

usage() {
    printf '%s\n' \
        "Usage: $0 --dataset {sti_bench|vsi_bench|spar|omnispatial} --resume" \
        "          [--storage-root PATH] [--dry-run] [--seed N] [--run-id ID]" \
        "          [--limit N] [--workers N]"
}

while (($#)); do
    case "$1" in
        --dataset) DATASET="$2"; shift 2 ;;
        --storage-root) STORAGE_ROOT="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        --resume) RESUME=1; shift ;;
        --seed) SEED="$2"; shift 2 ;;
        --run-id) RUN_ID="$2"; shift 2 ;;
        --limit) LIMIT="$2"; shift 2 ;;
        --workers) WORKERS="$2"; shift 2 ;;
        --help|-h) usage; exit 0 ;;
        *) printf 'Unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
done

case "$DATASET" in
    sti_bench|vsi_bench|spar|omnispatial) ;;
    *) printf 'Unsupported or missing dataset: %s\n' "$DATASET" >&2; exit 2 ;;
esac
if ((RESUME == 0)); then
    printf '%s\n' 'Media validation requires --resume.' >&2
    exit 2
fi
if [[ -n "$LIMIT" ]] && ! [[ "$LIMIT" =~ ^[1-9][0-9]*$ ]]; then
    printf '%s\n' '--limit must be a positive integer.' >&2
    exit 2
fi
if ! [[ "$WORKERS" =~ ^[1-9][0-9]*$ ]]; then
    printf '%s\n' '--workers must be a positive integer.' >&2
    exit 2
fi

module load python/3.12.11 ffmpeg/7.7.1
cd "$PROJECT_ROOT"
export PYTHONPATH="${PROJECT_ROOT}/src"

arguments=(
    validate-media
    --dataset "$DATASET"
    --storage-root "$STORAGE_ROOT"
    --resume
    --seed "$SEED"
    --workers "$WORKERS"
    --run-id "$RUN_ID"
)
if [[ -n "$LIMIT" ]]; then
    arguments+=(--limit "$LIMIT")
fi
if ((DRY_RUN == 1)); then
    arguments+=(--dry-run)
fi

python -m spaceconflict.cli "${arguments[@]}"
