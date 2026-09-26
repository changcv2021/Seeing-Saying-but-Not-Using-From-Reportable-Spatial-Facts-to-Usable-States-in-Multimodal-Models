#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-ca-taskpilot
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=6
#SBATCH --mem=24G
#SBATCH --time=02:00:00
#SBATCH --output=runs/ca_vqa_task_pilot_%j.out
#SBATCH --error=runs/ca_vqa_task_pilot_%j.err

set -euo pipefail

PROJECT_ROOT="./SpaceConflict"
DATA_ROOT="external/upstream/data/full_media_incoming/ca_vqa/080812355c21a40f437ed03d4ae558d35bfa2929"
DOWNLOAD_RUN="${PROJECT_ROOT}/runs/download_ca_vqa_slurm_8073172"
RUN_DIR="${PROJECT_ROOT}/runs/ca_vqa_task_pilot_${SLURM_JOB_ID:-manual}"
OUTPUT="${PROJECT_ROOT}/reports/ca_vqa/profile.all_tasks_pilot_v1.json"
mkdir -p "$RUN_DIR"

awk -F '\t' '$1 ~ /train\/cavqa_(cardinality|grounding2d|grounding3d|multichoice|regression)\/1.0.0\/(cavqa_.*-train.tfrecord-00000-of-01024|dataset_info.json|features.json)$/ {print}' \
    "${DOWNLOAD_RUN}/manifest_selected.tsv" >"${RUN_DIR}/manifest.tsv"
[[ "$(wc -l <"${RUN_DIR}/manifest.tsv")" == 15 ]]

download_one() {
    local row="$1" url expected relative destination partial actual hash
    IFS=$'\t' read -r url expected _ <<<"$row"
    relative="${url#https://ml-site.cdn-apple.com/datasets/cavqa/}"
    destination="${DATA_ROOT}/${relative}"
    partial="${destination}.pilot.part"
    mkdir -p "$(dirname "$destination")"
    if [[ -f "$destination" ]] && [[ "$(stat -c '%s' "$destination")" == "$expected" ]]; then
        hash="$(sha256sum "$destination" | awk '{print $1}')"
        printf '%s\tALREADY_VALID\t%s\t%s\n' "$relative" "$expected" "$hash"
        return
    fi
    curl --location --fail --silent --show-error --retry 20 --retry-all-errors --retry-delay 10 \
        --connect-timeout 30 --continue-at - --output "$partial" "$url"
    actual="$(stat -c '%s' "$partial")"
    [[ "$actual" == "$expected" ]]
    hash="$(sha256sum "$partial" | awk '{print $1}')"
    mv -- "$partial" "$destination"
    chmod 400 "$destination"
    printf '%s\tDOWNLOADED_AND_VERIFIED\t%s\t%s\n' "$relative" "$actual" "$hash"
}
export -f download_one
export DATA_ROOT
printf 'relative_path\tstatus\tbytes\tsha256\n' >"${RUN_DIR}/results.tsv"
xargs -r -P 5 -d '\n' -n 1 bash -c 'download_one "$1"' _ <"${RUN_DIR}/manifest.tsv" >>"${RUN_DIR}/results.tsv"
[[ "$(awk -F '\t' 'NR>1 && ($2=="DOWNLOADED_AND_VERIFIED" || $2=="ALREADY_VALID"){n++} END{print n+0}' "${RUN_DIR}/results.tsv")" == 15 ]]

module load python/3.12.11
cd "$PROJECT_ROOT"
python scripts/profile_ca_vqa.py --allow-incomplete --data-root "$DATA_ROOT" --download-run "$DOWNLOAD_RUN" --output "$OUTPUT"
