#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-ca-vqa
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=4-00:00:00

set -uo pipefail

PROJECT_ROOT="./dataset"
STORAGE_ROOT="external/upstream"
INVENTORY_DIR="${PROJECT_ROOT}/runs/inventory_ca_vqa_slurm_8073075"
REVISION="080812355c21a40f437ed03d4ae558d35bfa2929"
EXPECTED_FILES=6157
EXPECTED_BYTES=11575534117935
DRY_RUN=0
RESUME=0
SEED=20260826
RUN_ID="slurm_${SLURM_JOB_ID:-manual}"
LIMIT=0

usage() {
    printf '%s\n' "Usage: $0 --resume [--dry-run] [--seed N] [--run-id ID] [--limit N]"
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
    printf '%s\n' 'This downloader requires --resume.' >&2
    exit 2
fi
if ! [[ "$LIMIT" =~ ^[0-9]+$ ]]; then
    printf '%s\n' '--limit must be a non-negative integer; 0 means the complete CA-VQA dataset.' >&2
    exit 2
fi
for command_name in curl sha256sum awk sort stat xargs; do
    command -v "$command_name" >/dev/null 2>&1 || { printf 'Missing command: %s\n' "$command_name" >&2; exit 127; }
done

RUN_DIR="${PROJECT_ROOT}/runs/download_ca_vqa_${RUN_ID}"
DESTINATION_ROOT="${STORAGE_ROOT}/data/full_media_incoming/ca_vqa/${REVISION}"
mkdir -p "$RUN_DIR" "$DESTINATION_ROOT"
{
    printf 'dataset=ca_vqa\nrevision=%s\nrun_id=%s\nseed=%s\n' "$REVISION" "$RUN_ID" "$SEED"
    printf 'dry_run=%s\nresume=%s\nlimit=%s\nstorage_root=%s\n' "$DRY_RUN" "$RESUME" "$LIMIT" "$STORAGE_ROOT"
    printf 'expected_files=%s\nexpected_bytes=%s\nstarted_utc=%s\n' "$EXPECTED_FILES" "$EXPECTED_BYTES" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >"${RUN_DIR}/config.snapshot.txt"
git -C "$PROJECT_ROOT" rev-parse HEAD >"${RUN_DIR}/code_commit.txt" 2>/dev/null || printf '%s\n' UNVERSIONED >"${RUN_DIR}/code_commit.txt"

manifest_all="${RUN_DIR}/manifest_all.tsv"
{
    awk -F '\t' 'NR>1 && $1 ~ /\/datasets\/cavqa\// && $2 ~ /^[0-9]+$/ {print $1 "\t" $2 "\t" $3}' \
        "${INVENTORY_DIR}/url_sizes.tsv"
    awk -F '\t' 'NR>1 && $1 ~ /\/datasets\/cavqa\// && $2 ~ /^[0-9]+$/ {print $1 "\t" $2 "\t" $3}' \
        "${INVENTORY_DIR}/missing_url_sizes.tsv"
} | sort -t $'\t' -k1,1 -u >"$manifest_all"

manifest_files="$(wc -l <"$manifest_all")"
manifest_bytes="$(awk -F '\t' '{sum+=$2} END{printf "%.0f",sum}' "$manifest_all")"
if [[ "$manifest_files" != "$EXPECTED_FILES" ]] || [[ "$manifest_bytes" != "$EXPECTED_BYTES" ]]; then
    printf 'Frozen inventory mismatch: files=%s bytes=%s\n' "$manifest_files" "$manifest_bytes" >&2
    exit 1
fi

if ((LIMIT > 0)); then
    head -n "$LIMIT" "$manifest_all" >"${RUN_DIR}/manifest_selected.tsv"
else
    cp "$manifest_all" "${RUN_DIR}/manifest_selected.tsv"
fi
selected_files="$(wc -l <"${RUN_DIR}/manifest_selected.tsv")"
selected_bytes="$(awk -F '\t' '{sum+=$2} END{printf "%.0f",sum}' "${RUN_DIR}/manifest_selected.tsv")"

download_ca_file() {
    local record="$1"
    local url expected_bytes etag relative_path destination partial actual_bytes actual_hash
    IFS=$'\t' read -r url expected_bytes etag <<<"$record"
    relative_path="${url#https://ml-site.cdn-apple.com/datasets/cavqa/}"
    if [[ "$relative_path" == "$url" || "$relative_path" == /* || "$relative_path" == *'../'* ]]; then
        printf '%s\t%s\t%s\t%s\t%s\n' "$url" UNSAFE_PATH 0 NOT_COMPUTED NOT_CREATED
        return 1
    fi
    destination="${DESTINATION_ROOT}/${relative_path}"
    partial="${destination}.part"

    if ((DRY_RUN == 1)); then
        printf '%s\t%s\t%s\t%s\t%s\n' "$url" DRY_RUN "$expected_bytes" NOT_COMPUTED "$destination"
        return 0
    fi
    if [[ -f "$destination" ]]; then
        actual_bytes="$(stat -c '%s' "$destination")"
        if [[ "$actual_bytes" == "$expected_bytes" ]]; then
            actual_hash="$(sha256sum "$destination" | awk '{print $1}')"
            chmod 400 "$destination"
            printf '%s\t%s\t%s\t%s\t%s\n' "$url" ALREADY_VALID "$actual_bytes" "$actual_hash" "$destination"
            return 0
        fi
        printf '%s\t%s\t%s\t%s\t%s\n' "$url" EXISTING_SIZE_MISMATCH "$actual_bytes" NOT_COMPUTED "$destination"
        return 1
    fi

    mkdir -p "$(dirname "$destination")"
    if ! curl --location --fail --silent --show-error \
        --retry 20 --retry-all-errors --retry-delay 10 --connect-timeout 30 \
        --continue-at - --output "$partial" "$url"; then
        actual_bytes="$(stat -c '%s' "$partial" 2>/dev/null || printf 0)"
        printf '%s\t%s\t%s\t%s\t%s\n' "$url" DOWNLOAD_FAILED "$actual_bytes" NOT_COMPUTED "$partial"
        return 1
    fi
    actual_bytes="$(stat -c '%s' "$partial")"
    if [[ "$actual_bytes" != "$expected_bytes" ]]; then
        printf '%s\t%s\t%s\t%s\t%s\n' "$url" SIZE_MISMATCH "$actual_bytes" NOT_COMPUTED "$partial"
        return 1
    fi
    actual_hash="$(sha256sum "$partial" | awk '{print $1}')"
    mv -- "$partial" "$destination"
    chmod 400 "$destination"
    printf '%s\t%s\t%s\t%s\t%s\n' "$url" DOWNLOADED_AND_VERIFIED "$actual_bytes" "$actual_hash" "$destination"
    return 0
}
export -f download_ca_file
export DESTINATION_ROOT DRY_RUN

printf 'url\tstatus\tbytes\tsha256\tlocal_path\n' >"${RUN_DIR}/results.tsv"
set +e
xargs -r -P 8 -d '\n' -n 1 bash -c 'download_ca_file "$1"' _ \
    <"${RUN_DIR}/manifest_selected.tsv" >>"${RUN_DIR}/results.tsv"
xargs_status=$?
set -e

success_count="$(awk -F '\t' 'NR>1 && ($2=="DOWNLOADED_AND_VERIFIED" || $2=="ALREADY_VALID" || $2=="DRY_RUN") {count++} END{print count+0}' "${RUN_DIR}/results.tsv")"
failure_count="$(awk -F '\t' 'NR>1 && !($2=="DOWNLOADED_AND_VERIFIED" || $2=="ALREADY_VALID" || $2=="DRY_RUN") {count++} END{print count+0}' "${RUN_DIR}/results.tsv")"
{
    printf 'selected_files=%s\nselected_bytes=%s\n' "$selected_files" "$selected_bytes"
    printf 'success_count=%s\nfailure_count=%s\nxargs_status=%s\n' "$success_count" "$failure_count" "$xargs_status"
    printf 'finished_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >"${RUN_DIR}/summary.txt"
printf 'CA-VQA download: files=%s bytes=%s success=%s failure=%s\n' \
    "$selected_files" "$selected_bytes" "$success_count" "$failure_count"
((failure_count == 0))
