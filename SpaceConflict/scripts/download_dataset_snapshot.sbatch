#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-data
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=04:00:00

set -uo pipefail

PROJECT_ROOT="./SpaceConflict"
RUNS_ROOT="${PROJECT_ROOT}/runs"
STORAGE_ROOT="$PROJECT_ROOT"
DATASET=""
DRY_RUN=0
RESUME=0
SEED=20260826
RUN_ID="slurm_${SLURM_JOB_ID:-manual}"
LIMIT=0

usage() {
    printf '%s\n' \
        "Usage: $0 --dataset {spar|vsi_bench|hypo3d|omnispatial} --resume" \
        "          [--storage-root PATH] [--dry-run] [--seed N] [--run-id ID] [--limit N]"
}

while (($#)); do
    case "$1" in
        --dataset)
            DATASET="$2"
            shift 2
            ;;
        --storage-root)
            STORAGE_ROOT="$2"
            shift 2
            ;;
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

case "$DATASET" in
    spar|vsi_bench|hypo3d|omnispatial) ;;
    *)
        printf 'Unsupported or missing dataset: %s\n' "$DATASET" >&2
        usage >&2
        exit 2
        ;;
esac

if ((RESUME == 0)); then
    printf '%s\n' 'This downloader requires --resume.' >&2
    exit 2
fi
if [[ "$STORAGE_ROOT" != /* ]]; then
    printf '%s\n' '--storage-root must be an absolute path.' >&2
    exit 2
fi
if ! [[ "$LIMIT" =~ ^[0-9]+$ ]]; then
    printf '%s\n' '--limit must be a non-negative integer; 0 means all selected files.' >&2
    exit 2
fi

for required_command in curl jq sha256sum awk stat; do
    if ! command -v "$required_command" >/dev/null 2>&1; then
        printf 'Required command is unavailable: %s\n' "$required_command" >&2
        exit 127
    fi
done

RUN_DIR="${RUNS_ROOT}/download_${DATASET}_${RUN_ID}"
mkdir -p "$RUN_DIR"
printf 'repository\trevision\tpath\texpected_bytes\texpected_sha256\n' >"${RUN_DIR}/source_files.tsv"
printf 'repository\tpath\tstatus\tbytes\tsha256\tlocal_path\n' >"${RUN_DIR}/results.tsv"

{
    printf 'dataset=%s\n' "$DATASET"
    printf 'storage_root=%s\n' "$STORAGE_ROOT"
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

declare -a REPOSITORIES=()
declare -a REVISIONS=()
declare -a FILTERS=()
declare -a DESTINATIONS=()

case "$DATASET" in
    spar)
        REPOSITORIES=(jasonzhango/SPAR-Bench jasonzhango/SPAR-7M)
        REVISIONS=(ee122877c25c8bb08539b07e06d872152c9968f1 0fe664cbada1e7c1173fd743e0f781882eebf777)
        FILTERS=('all' 'all')
        DESTINATIONS=(
            "${STORAGE_ROOT}/data/full_media_incoming/spar/ee122877c25c8bb08539b07e06d872152c9968f1/SPAR-Bench"
            "${STORAGE_ROOT}/data/full_media_incoming/spar/0fe664cbada1e7c1173fd743e0f781882eebf777/SPAR-7M"
        )
        ;;
    vsi_bench)
        REPOSITORIES=(nyu-visionx/VSI-Bench)
        REVISIONS=(bdcadb3fea447621a828a24911801faba3587c12)
        FILTERS=('vsi_remaining')
        DESTINATIONS=(
            "${STORAGE_ROOT}/data/pilot_media_incoming/vsi_bench/bdcadb3fea447621a828a24911801faba3587c12"
        )
        ;;
    hypo3d)
        REPOSITORIES=(MatchLab/Hypo3D)
        REVISIONS=(ffb21ab198e8d666b63e062d931ed33b60c67d0f)
        FILTERS=('all')
        DESTINATIONS=(
            "${STORAGE_ROOT}/data/full_media_incoming/hypo3d/ffb21ab198e8d666b63e062d931ed33b60c67d0f"
        )
        ;;
    omnispatial)
        REPOSITORIES=(qizekun/OmniSpatial)
        REVISIONS=(6691f3288bb1ff207d6ead4d841b505de08a6fd8)
        FILTERS=('omnispatial_full')
        DESTINATIONS=(
            "${STORAGE_ROOT}/data/full_media_incoming/omnispatial/6691f3288bb1ff207d6ead4d841b505de08a6fd8"
        )
        ;;
esac

selected_count=0
selected_bytes=0
success_count=0
failure_count=0
skipped_count=0

download_file() {
    local repository="$1"
    local revision="$2"
    local remote_path="$3"
    local expected_bytes="$4"
    local expected_sha256="$5"
    local destination_root="$6"
    local destination="${destination_root}/${remote_path}"
    local partial="${destination}.part"
    local url="https://huggingface.co/datasets/${repository}/resolve/${revision}/${remote_path}?download=true"
    local actual_bytes
    local actual_sha256

    if [[ "$remote_path" == /* || "$remote_path" == *'../'* || "$remote_path" == '..' ]]; then
        printf 'Unsafe repository path rejected: %s\n' "$remote_path" >&2
        return 1
    fi

    if [[ -f "$destination" ]]; then
        actual_bytes="$(stat -c '%s' "$destination")"
        actual_sha256="$(sha256sum "$destination" | awk '{print $1}')"
        if [[ "$actual_bytes" == "$expected_bytes" ]] && \
           { [[ -z "$expected_sha256" ]] || [[ "$actual_sha256" == "$expected_sha256" ]]; }; then
            chmod 400 "$destination"
            printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
                "$repository" "$remote_path" ALREADY_VALID "$actual_bytes" "$actual_sha256" "$destination" \
                >>"${RUN_DIR}/results.tsv"
            return 0
        fi
        printf 'Refusing to overwrite invalid existing file: %s\n' "$destination" >&2
        printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
            "$repository" "$remote_path" EXISTING_MISMATCH "$actual_bytes" "$actual_sha256" "$destination" \
            >>"${RUN_DIR}/results.tsv"
        return 1
    fi

    if ((DRY_RUN == 1)); then
        printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
            "$repository" "$remote_path" DRY_RUN 0 NOT_COMPUTED "$destination" \
            >>"${RUN_DIR}/results.tsv"
        return 0
    fi

    mkdir -p "$(dirname "$destination")"
    printf 'Downloading %s/%s\n' "$repository" "$remote_path"
    if ! curl \
        --location --fail --show-error \
        --retry 20 --retry-all-errors --retry-delay 10 \
        --connect-timeout 30 --continue-at - \
        --output "$partial" "$url"; then
        actual_bytes="$(stat -c '%s' "$partial" 2>/dev/null || printf 0)"
        printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
            "$repository" "$remote_path" DOWNLOAD_FAILED "$actual_bytes" NOT_COMPUTED "$partial" \
            >>"${RUN_DIR}/results.tsv"
        return 1
    fi

    actual_bytes="$(stat -c '%s' "$partial")"
    actual_sha256="$(sha256sum "$partial" | awk '{print $1}')"
    if [[ "$actual_bytes" != "$expected_bytes" ]] || \
       { [[ -n "$expected_sha256" ]] && [[ "$actual_sha256" != "$expected_sha256" ]]; }; then
        printf 'Integrity mismatch: %s\n' "$partial" >&2
        printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
            "$repository" "$remote_path" INTEGRITY_MISMATCH "$actual_bytes" "$actual_sha256" "$partial" \
            >>"${RUN_DIR}/results.tsv"
        return 1
    fi

    mv -- "$partial" "$destination"
    chmod 400 "$destination"
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$repository" "$remote_path" DOWNLOADED_AND_VERIFIED "$actual_bytes" "$actual_sha256" "$destination" \
        >>"${RUN_DIR}/results.tsv"
    return 0
}

for ((repo_index = 0; repo_index < ${#REPOSITORIES[@]}; repo_index++)); do
    repository="${REPOSITORIES[$repo_index]}"
    revision="${REVISIONS[$repo_index]}"
    filter="${FILTERS[$repo_index]}"
    destination_root="${DESTINATIONS[$repo_index]}"
    api_file="${RUN_DIR}/$(printf '%s' "$repository" | tr '/' '_').api.json"

    if ! curl --location --fail --show-error --retry 5 --max-time 120 \
        --output "$api_file" \
        "https://huggingface.co/api/datasets/${repository}/revision/${revision}?blobs=true"; then
        printf 'Unable to obtain repository metadata: %s@%s\n' "$repository" "$revision" >&2
        ((failure_count += 1))
        continue
    fi

    reported_revision="$(jq -r '.sha' "$api_file")"
    if [[ "$reported_revision" != "$revision" ]]; then
        printf 'Revision mismatch for %s: expected %s, got %s\n' \
            "$repository" "$revision" "$reported_revision" >&2
        ((failure_count += 1))
        continue
    fi

    case "$filter" in
        all)
            jq_filter='.siblings[]'
            ;;
        vsi_remaining)
            jq_filter='.siblings[] | select(.rfilename == "arkitscenes.zip" or .rfilename == "scannet.zip")'
            ;;
        omnispatial_full)
            jq_filter='.siblings[] | select(.rfilename == "OmniSpatial-full.zip" or .rfilename == "README.md")'
            ;;
    esac

    while IFS=$'\t' read -r remote_path expected_bytes expected_sha256; do
        [[ -n "$remote_path" ]] || continue
        if ((LIMIT > 0 && selected_count >= LIMIT)); then
            break
        fi
        ((selected_count += 1))
        ((selected_bytes += expected_bytes))
        printf '%s\t%s\t%s\t%s\t%s\n' \
            "$repository" "$revision" "$remote_path" "$expected_bytes" "$expected_sha256" \
            >>"${RUN_DIR}/source_files.tsv"
        if download_file "$repository" "$revision" "$remote_path" "$expected_bytes" "$expected_sha256" "$destination_root"; then
            ((success_count += 1))
        else
            ((failure_count += 1))
        fi
    done < <(jq -r "$jq_filter | [.rfilename, (.size | tostring), (.lfs.sha256 // \"\")] | @tsv" "$api_file")
done

{
    printf 'selected_count=%s\n' "$selected_count"
    printf 'selected_bytes=%s\n' "$selected_bytes"
    printf 'success_count=%s\n' "$success_count"
    printf 'failure_count=%s\n' "$failure_count"
    printf 'skipped_count=%s\n' "$skipped_count"
    printf 'finished_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >"${RUN_DIR}/summary.txt"

printf 'Completed %s: selected=%s bytes=%s success=%s failure=%s\n' \
    "$DATASET" "$selected_count" "$selected_bytes" "$success_count" "$failure_count"
if ((failure_count > 0)); then
    exit 1
fi
