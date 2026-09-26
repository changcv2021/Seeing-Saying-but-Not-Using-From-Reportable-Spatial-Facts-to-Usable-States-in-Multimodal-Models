#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-dl
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=02:00:00

set -uo pipefail

PROJECT_ROOT="./dataset"
INCOMING_ROOT="${PROJECT_ROOT}/data/pilot_media_incoming"
RUNS_ROOT="${PROJECT_ROOT}/runs"

DRY_RUN=0
RESUME=0
SEED=20260826
RUN_ID="slurm_${SLURM_JOB_ID:-manual}"
LIMIT=2

usage() {
    printf '%s\n' \
        "Usage: $0 [--dry-run] [--resume] [--seed N] [--run-id ID] [--limit N]" \
        "" \
        "Downloads the frozen STI-Bench and VSI-Bench pilot media artifacts."
}

while (($#)); do
    case "$1" in
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --resume)
            RESUME=1
            shift
            ;;
        --seed)
            SEED="$2"
            shift 2
            ;;
        --run-id)
            RUN_ID="$2"
            shift 2
            ;;
        --limit)
            LIMIT="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            printf 'Unknown argument: %s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if ! [[ "$LIMIT" =~ ^[0-9]+$ ]] || ((LIMIT < 1 || LIMIT > 2)); then
    printf '%s\n' '--limit must be 1 or 2' >&2
    exit 2
fi

if ((RESUME == 0)); then
    printf '%s\n' 'This downloader requires --resume so interrupted .part files are handled explicitly.' >&2
    exit 2
fi

for required_command in curl sha256sum git; do
    if ! command -v "$required_command" >/dev/null 2>&1; then
        printf 'Required command is unavailable: %s\n' "$required_command" >&2
        exit 127
    fi
done

RUN_DIR="${RUNS_ROOT}/download_${RUN_ID}"
mkdir -p "$RUN_DIR"

{
    printf 'run_id=%s\n' "$RUN_ID"
    printf 'seed=%s\n' "$SEED"
    printf 'dry_run=%s\n' "$DRY_RUN"
    printf 'resume=%s\n' "$RESUME"
    printf 'limit=%s\n' "$LIMIT"
    printf 'hostname=%s\n' "$(hostname)"
    printf 'slurm_job_id=%s\n' "${SLURM_JOB_ID:-NONE}"
    printf 'slurm_partition=%s\n' "${SLURM_JOB_PARTITION:-NONE}"
    printf 'started_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >"${RUN_DIR}/config.snapshot.txt"

git -C "$PROJECT_ROOT" rev-parse HEAD >"${RUN_DIR}/code_commit.txt" 2>/dev/null || printf '%s\n' UNVERSIONED >"${RUN_DIR}/code_commit.txt"
printf '%s\n' "$SEED" >"${RUN_DIR}/seed.txt"
printf 'dataset\trevision\tfilename\turl_sha256\texpected_content_sha256\n' >"${RUN_DIR}/source_revisions.tsv"
printf 'dataset\tstatus\tbytes\tcontent_sha256\tpath\n' >"${RUN_DIR}/results.tsv"

DATASETS=(
    sti_bench
    vsi_bench
)
REVISIONS=(
    6b1009261689d3d5244bc2338ab5f83e3fb55875
    bdcadb3fea447621a828a24911801faba3587c12
)
FILENAMES=(
    video.zip
    scannetpp.zip
)
EXPECTED_HASHES=(
    262c3b018fb85723b62d15bbf5bfc319d6848c09dd95dfe7e6ff1847a0e758f2
    164b2314107e070c7d8a652897404904adf36a8868c2293be04382727d9a19be
)
URLS=(
    'https://huggingface.co/datasets/MINT-SJTU/STI-Bench/resolve/6b1009261689d3d5244bc2338ab5f83e3fb55875/video.zip?download=true'
    'https://huggingface.co/datasets/nyu-visionx/VSI-Bench/resolve/bdcadb3fea447621a828a24911801faba3587c12/scannetpp.zip?download=true'
)

download_one() {
    local dataset="$1"
    local revision="$2"
    local filename="$3"
    local expected_hash="$4"
    local url="$5"
    local destination_dir="${INCOMING_ROOT}/${dataset}/${revision}"
    local destination="${destination_dir}/${filename}"
    local partial="${destination}.part"
    local actual_hash
    local byte_count
    local url_hash

    url_hash="$(printf '%s' "$url" | sha256sum | awk '{print $1}')"
    printf '%s\t%s\t%s\t%s\t%s\n' \
        "$dataset" "$revision" "$filename" "$url_hash" "$expected_hash" \
        >>"${RUN_DIR}/source_revisions.tsv"

    if [[ -f "$destination" ]]; then
        actual_hash="$(sha256sum "$destination" | awk '{print $1}')"
        byte_count="$(stat -c '%s' "$destination")"
        if [[ "$actual_hash" == "$expected_hash" ]]; then
            chmod 400 "$destination"
            printf '%s\t%s\t%s\t%s\t%s\n' \
                "$dataset" ALREADY_VALID "$byte_count" "$actual_hash" "$destination" \
                >>"${RUN_DIR}/results.tsv"
            return 0
        fi

        printf 'Refusing to overwrite an existing file with a wrong hash: %s\n' "$destination" >&2
        printf '%s\t%s\t%s\t%s\t%s\n' \
            "$dataset" EXISTING_HASH_MISMATCH "$byte_count" "$actual_hash" "$destination" \
            >>"${RUN_DIR}/results.tsv"
        return 1
    fi

    mkdir -p "$destination_dir"

    if ((DRY_RUN == 1)); then
        printf 'DRY RUN: curl -> %s\n' "$partial"
        printf '%s\t%s\t%s\t%s\t%s\n' \
            "$dataset" DRY_RUN 0 NOT_COMPUTED "$destination" \
            >>"${RUN_DIR}/results.tsv"
        return 0
    fi

    printf 'Downloading %s/%s to %s\n' "$dataset" "$filename" "$partial"
    if ! curl \
        --location \
        --fail \
        --show-error \
        --retry 20 \
        --retry-all-errors \
        --retry-delay 10 \
        --connect-timeout 30 \
        --continue-at - \
        --output "$partial" \
        "$url"; then
        byte_count="$(stat -c '%s' "$partial" 2>/dev/null || printf 0)"
        printf '%s\t%s\t%s\t%s\t%s\n' \
            "$dataset" DOWNLOAD_FAILED "$byte_count" NOT_COMPUTED "$partial" \
            >>"${RUN_DIR}/results.tsv"
        return 1
    fi

    actual_hash="$(sha256sum "$partial" | awk '{print $1}')"
    byte_count="$(stat -c '%s' "$partial")"
    if [[ "$actual_hash" != "$expected_hash" ]]; then
        printf 'Checksum mismatch for %s: expected %s, got %s\n' \
            "$partial" "$expected_hash" "$actual_hash" >&2
        printf '%s\t%s\t%s\t%s\t%s\n' \
            "$dataset" CHECKSUM_MISMATCH "$byte_count" "$actual_hash" "$partial" \
            >>"${RUN_DIR}/results.tsv"
        return 1
    fi

    mv -- "$partial" "$destination"
    chmod 400 "$destination"
    printf '%s\t%s\t%s\t%s\t%s\n' \
        "$dataset" DOWNLOADED_AND_VERIFIED "$byte_count" "$actual_hash" "$destination" \
        >>"${RUN_DIR}/results.tsv"
    return 0
}

success_count=0
failure_count=0

for ((index = 0; index < LIMIT; index++)); do
    if download_one \
        "${DATASETS[$index]}" \
        "${REVISIONS[$index]}" \
        "${FILENAMES[$index]}" \
        "${EXPECTED_HASHES[$index]}" \
        "${URLS[$index]}"; then
        ((success_count += 1))
    else
        ((failure_count += 1))
    fi
done

{
    printf 'success_count=%s\n' "$success_count"
    printf 'failure_count=%s\n' "$failure_count"
    printf 'finished_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >"${RUN_DIR}/summary.txt"

printf 'Completed: success=%s failure=%s\n' "$success_count" "$failure_count"
if ((failure_count > 0)); then
    exit 1
fi
