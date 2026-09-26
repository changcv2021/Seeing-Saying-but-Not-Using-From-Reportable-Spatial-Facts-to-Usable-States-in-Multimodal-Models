#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-ca-size
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=04:00:00

set -uo pipefail

PROJECT_ROOT="./dataset"
STORAGE_ROOT="external/upstream"
REVISION="080812355c21a40f437ed03d4ae558d35bfa2929"
RUNS_ROOT="${PROJECT_ROOT}/runs"
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
    printf '%s\n' 'This inventory requires --resume.' >&2
    exit 2
fi
if ! [[ "$LIMIT" =~ ^[0-9]+$ ]]; then
    printf '%s\n' '--limit must be a non-negative integer; 0 means all URLs.' >&2
    exit 2
fi

RUN_DIR="${RUNS_ROOT}/inventory_ca_vqa_${RUN_ID}"
LIST_ROOT="${STORAGE_ROOT}/data/source_lists/ca_vqa/${REVISION}"
mkdir -p "$RUN_DIR" "$LIST_ROOT"
{
    printf 'dataset=ca_vqa\nrevision=%s\nrun_id=%s\nseed=%s\n' "$REVISION" "$RUN_ID" "$SEED"
    printf 'dry_run=%s\nresume=%s\nlimit=%s\nstorage_root=%s\n' "$DRY_RUN" "$RESUME" "$LIMIT" "$STORAGE_ROOT"
    printf 'started_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >"${RUN_DIR}/config.snapshot.txt"

LIST_FILES=(
    data/train.txt
    data/val.txt
    data/cavqa/val.txt
    data/cavqa/train_binary.txt
    data/cavqa/train_cardinality.txt
    data/cavqa/train_grounding2d.txt
    data/cavqa/train_grounding3d.txt
    data/cavqa/train_multichoice.txt
    data/cavqa/train_regression.txt
)

all_urls="${RUN_DIR}/all_urls.txt"
: >"$all_urls"
failure_count=0
for relative_path in "${LIST_FILES[@]}"; do
    destination="${LIST_ROOT}/${relative_path}"
    mkdir -p "$(dirname "$destination")"
    if ! curl --location --fail --show-error --retry 5 --max-time 120 \
        --output "${destination}.part" \
        "https://raw.githubusercontent.com/apple/ml-cubifyanything/${REVISION}/${relative_path}"; then
        printf 'Failed to download list: %s\n' "$relative_path" >&2
        ((failure_count += 1))
        continue
    fi
    mv -- "${destination}.part" "$destination"
    chmod 400 "$destination"
    sha256sum "$destination" >>"${RUN_DIR}/list_hashes.txt"
    sed '/^[[:space:]]*$/d' "$destination" >>"$all_urls"
    printf '\n' >>"$all_urls"
done

sort -u "$all_urls" -o "${RUN_DIR}/unique_urls.txt"
if ((LIMIT > 0)); then
    head -n "$LIMIT" "${RUN_DIR}/unique_urls.txt" >"${RUN_DIR}/selected_urls.txt"
else
    cp "${RUN_DIR}/unique_urls.txt" "${RUN_DIR}/selected_urls.txt"
fi
url_count="$(wc -l <"${RUN_DIR}/selected_urls.txt")"

if ((DRY_RUN == 1)); then
    printf 'url_count=%s\ntotal_bytes=NOT_COMPUTED\nfailure_count=%s\n' "$url_count" "$failure_count" >"${RUN_DIR}/summary.txt"
    printf 'CA-VQA inventory dry run: URLs=%s\n' "$url_count"
    ((failure_count == 0))
    exit
fi

probe_url() {
    local url="$1"
    local headers
    local content_length
    local etag
    if ! headers="$(curl --location --fail --silent --show-error --head \
        --retry 5 --retry-all-errors --connect-timeout 20 --max-time 90 "$url")"; then
        printf '%s\t%s\t%s\n' "$url" FAILED NOT_AVAILABLE
        return
    fi
    content_length="$(printf '%s\n' "$headers" | tr -d '\r' | awk 'BEGIN{IGNORECASE=1} /^content-length:/ {value=$2} END{print value}')"
    etag="$(printf '%s\n' "$headers" | tr -d '\r' | awk 'BEGIN{IGNORECASE=1} /^etag:/ {$1=""; sub(/^ /,""); value=$0} END{print value}')"
    if [[ "$content_length" =~ ^[0-9]+$ ]]; then
        printf '%s\t%s\t%s\n' "$url" "$content_length" "$etag"
    else
        printf '%s\t%s\t%s\n' "$url" FAILED "$etag"
    fi
}
export -f probe_url

printf 'url\tcontent_length\tetag\n' >"${RUN_DIR}/url_sizes.tsv"
xargs -r -P 8 -n 1 bash -c 'probe_url "$1"' _ \
    <"${RUN_DIR}/selected_urls.txt" >>"${RUN_DIR}/url_sizes.tsv"

probe_failures="$(awk -F '\t' 'NR>1 && $2=="FAILED" {count++} END{print count+0}' "${RUN_DIR}/url_sizes.tsv")"
total_bytes="$(awk -F '\t' 'NR>1 && $2 ~ /^[0-9]+$/ {sum+=$2} END{printf "%.0f",sum}' "${RUN_DIR}/url_sizes.tsv")"
((failure_count += probe_failures))
{
    printf 'url_count=%s\n' "$url_count"
    printf 'total_bytes=%s\n' "$total_bytes"
    printf 'failure_count=%s\n' "$failure_count"
    printf 'finished_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >"${RUN_DIR}/summary.txt"
printf 'CA-VQA inventory: URLs=%s bytes=%s failures=%s\n' "$url_count" "$total_bytes" "$failure_count"
((failure_count == 0))
