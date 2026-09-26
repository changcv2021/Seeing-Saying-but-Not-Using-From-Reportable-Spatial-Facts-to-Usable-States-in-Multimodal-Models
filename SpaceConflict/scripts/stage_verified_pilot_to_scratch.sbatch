#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-stage
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=01:00:00

set -uo pipefail

PROJECT_ROOT="./SpaceConflict"
STORAGE_ROOT="external/upstream"
RUNS_ROOT="${PROJECT_ROOT}/runs"
DRY_RUN=0
RESUME=0
SEED=20260826
RUN_ID="slurm_${SLURM_JOB_ID:-manual}"
LIMIT=2

usage() {
    printf '%s\n' "Usage: $0 --resume [--dry-run] [--seed N] [--run-id ID] [--limit 1|2]"
}

while (($#)); do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        --resume) RESUME=1; shift ;;
        --seed) SEED="$2"; shift 2 ;;
        --run-id) RUN_ID="$2"; shift 2 ;;
        --limit) LIMIT="$2"; shift 2 ;;
        --help|-h) usage; exit 0 ;;
        *) printf 'Unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
done

if ((RESUME == 0)); then
    printf '%s\n' 'This staging script requires --resume.' >&2
    exit 2
fi
if ! [[ "$LIMIT" =~ ^[12]$ ]]; then
    printf '%s\n' '--limit must be 1 or 2.' >&2
    exit 2
fi

RUN_DIR="${RUNS_ROOT}/stage_pilot_${RUN_ID}"
mkdir -p "$RUN_DIR"
printf 'dataset\tstatus\tbytes\tsha256\tdestination\n' >"${RUN_DIR}/results.tsv"
{
    printf 'run_id=%s\nseed=%s\ndry_run=%s\nresume=%s\nlimit=%s\n' \
        "$RUN_ID" "$SEED" "$DRY_RUN" "$RESUME" "$LIMIT"
    printf 'storage_root=%s\nstarted_utc=%s\n' "$STORAGE_ROOT" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >"${RUN_DIR}/config.snapshot.txt"

SOURCES=(
    "${PROJECT_ROOT}/data/pilot_media_incoming/sti_bench/6b1009261689d3d5244bc2338ab5f83e3fb55875/video.zip"
    "${PROJECT_ROOT}/data/pilot_media_incoming/vsi_bench/bdcadb3fea447621a828a24911801faba3587c12/scannetpp.zip"
)
DESTINATIONS=(
    "${STORAGE_ROOT}/data/pilot_media_incoming/sti_bench/6b1009261689d3d5244bc2338ab5f83e3fb55875/video.zip"
    "${STORAGE_ROOT}/data/pilot_media_incoming/vsi_bench/bdcadb3fea447621a828a24911801faba3587c12/scannetpp.zip"
)
DATASETS=(sti_bench vsi_bench)
HASHES=(
    262c3b018fb85723b62d15bbf5bfc319d6848c09dd95dfe7e6ff1847a0e758f2
    164b2314107e070c7d8a652897404904adf36a8868c2293be04382727d9a19be
)

success_count=0
failure_count=0
for ((index = 0; index < LIMIT; index++)); do
    source_file="${SOURCES[$index]}"
    destination="${DESTINATIONS[$index]}"
    expected_hash="${HASHES[$index]}"
    dataset="${DATASETS[$index]}"
    partial="${destination}.part"

    if [[ ! -f "$source_file" ]] || [[ "$(sha256sum "$source_file" | awk '{print $1}')" != "$expected_hash" ]]; then
        printf '%s\t%s\t0\t%s\t%s\n' "$dataset" SOURCE_INVALID "$expected_hash" "$destination" >>"${RUN_DIR}/results.tsv"
        ((failure_count += 1))
        continue
    fi
    if [[ -f "$destination" ]] && [[ "$(sha256sum "$destination" | awk '{print $1}')" == "$expected_hash" ]]; then
        chmod 400 "$destination"
        printf '%s\t%s\t%s\t%s\t%s\n' "$dataset" ALREADY_VALID "$(stat -c '%s' "$destination")" "$expected_hash" "$destination" >>"${RUN_DIR}/results.tsv"
        ((success_count += 1))
        continue
    fi
    if ((DRY_RUN == 1)); then
        printf '%s\t%s\t0\t%s\t%s\n' "$dataset" DRY_RUN "$expected_hash" "$destination" >>"${RUN_DIR}/results.tsv"
        ((success_count += 1))
        continue
    fi

    mkdir -p "$(dirname "$destination")"
    cp --sparse=always -- "$source_file" "$partial"
    if [[ "$(sha256sum "$partial" | awk '{print $1}')" != "$expected_hash" ]]; then
        printf '%s\t%s\t%s\t%s\t%s\n' "$dataset" COPY_HASH_MISMATCH "$(stat -c '%s' "$partial")" "$(sha256sum "$partial" | awk '{print $1}')" "$partial" >>"${RUN_DIR}/results.tsv"
        ((failure_count += 1))
        continue
    fi
    mv -- "$partial" "$destination"
    chmod 400 "$destination"
    printf '%s\t%s\t%s\t%s\t%s\n' "$dataset" COPIED_AND_VERIFIED "$(stat -c '%s' "$destination")" "$expected_hash" "$destination" >>"${RUN_DIR}/results.tsv"
    ((success_count += 1))
done

{
    printf 'success_count=%s\nfailure_count=%s\nfinished_utc=%s\n' \
        "$success_count" "$failure_count" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >"${RUN_DIR}/summary.txt"
printf 'Completed staging: success=%s failure=%s\n' "$success_count" "$failure_count"
((failure_count == 0))
