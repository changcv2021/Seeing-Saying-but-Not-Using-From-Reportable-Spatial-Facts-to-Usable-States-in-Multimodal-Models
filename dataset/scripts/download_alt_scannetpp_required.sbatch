#!/usr/bin/env bash
#SBATCH --job-name=sc_scannetpp_rgb
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=1-00:00:00
#SBATCH --output=artifacts/upstream_media/spar7m_acquisition/slurm/scannetpp_download_%j.out
#SBATCH --error=artifacts/upstream_media/spar7m_acquisition/slurm/scannetpp_download_%j.err

set -euo pipefail
umask 0007

acq=artifacts/upstream_media/spar7m_acquisition
manifest="$acq/alternative_sources/manifests/scannetpp_required_526.tsv"
archive_dir=artifacts/upstream_media/spar7m_raw/scannetpp/archives
member_dir="$acq/alternative_sources/member_lists/scannetpp"
validation="$acq/alternative_sources/validation/scannetpp"

mkdir -p "$archive_dir" "$member_dir" "$validation"

download_one() {
  local scene=$1
  local filename=$2
  local expected_size=$3
  local expected_sha=$4
  local destination="$archive_dir/$filename"
  local url="https://huggingface.co/datasets/HarrisonPENG/scannetpp/resolve/main/$filename"

  curl --fail --location --retry 20 --retry-all-errors --retry-delay 10 \
    --continue-at - --output "$destination" "$url"
  local actual_size
  actual_size=$(stat -c '%s' "$destination")
  if [[ "$actual_size" != "$expected_size" ]]; then
    echo "$scene size mismatch: expected=$expected_size actual=$actual_size" >&2
    return 10
  fi
  printf '%s  %s\n' "$expected_sha" "$destination" | sha256sum --check
  tar -tzf "$destination" > "$member_dir/$scene.members.txt"
}
export -f download_one
export archive_dir member_dir

xargs -n 4 -P "${SLURM_CPUS_PER_TASK:-4}" bash -euo pipefail -c 'download_one "$@"' _ < "$manifest"

jq -r 'select(.base_dataset == "scannetpp") | .locator' \
  "$acq/required_accessible_media.jsonl" "$acq/required_withheld_media.jsonl" \
  | awk -F/ '/image_color\/[0-9]+[.]jpg$/ {
  name=$6; sub(/[.]jpg$/, "", name);
  printf "%s/images/frame_%06d\n", $4, name
}' \
  | sort -u > "$validation/expected_frames_all_scenes.txt"

cut -f1 "$manifest" > "$validation/downloaded_scenes.txt"
awk 'NR==FNR {scene[$1]=1; next} {
  split($0, p, "/"); if (scene[p[1]]) print $0
}' "$validation/downloaded_scenes.txt" "$validation/expected_frames_all_scenes.txt" \
  | sort -u > "$validation/expected_frames_526_scenes.txt"

rg --no-filename -o '[0-9a-f]+/images/frame_[0-9]+([.]jpg)?$' "$member_dir"/*.members.txt \
  | sed -E 's/[.]jpg$//' | sort -u > "$validation/present_frames.txt"
comm -23 "$validation/expected_frames_526_scenes.txt" "$validation/present_frames.txt" \
  > "$validation/missing_required_frames.txt"

archive_count=$(find "$archive_dir" -maxdepth 1 -type f -name '*.tar.gz' -printf '.' | wc -c)
missing_count=$(wc -l < "$validation/missing_required_frames.txt")
if [[ "$archive_count" -ne 526 || "$missing_count" -ne 0 ]]; then
  echo "Validation failed: archives=$archive_count missing_frames=$missing_count" >&2
  exit 20
fi

total_bytes=$(awk -F '\t' '{sum += $3} END {printf "%.0f", sum}' "$manifest")
printf 'archive_count=%s\nbytes=%s\nexpected_frames=%s\nmissing_frames=%s\nstatus=PASS\n' \
  "$archive_count" "$total_bytes" \
  "$(wc -l < "$validation/expected_frames_526_scenes.txt")" "$missing_count" \
  > "$validation/summary.txt"
echo SCANNETPP_DOWNLOAD_AND_VALIDATION_PASS
