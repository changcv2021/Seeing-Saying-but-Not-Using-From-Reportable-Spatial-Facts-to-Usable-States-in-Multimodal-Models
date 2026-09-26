#!/usr/bin/env bash
#SBATCH --job-name=sc_scannet_rgb
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=1-00:00:00
#SBATCH --output=artifacts/upstream_media/spar7m_acquisition/slurm/scannet_download_%j.out
#SBATCH --error=artifacts/upstream_media/spar7m_acquisition/slurm/scannet_download_%j.err

set -euo pipefail
umask 0007

acq=artifacts/upstream_media/spar7m_acquisition
archive_dir=artifacts/upstream_media/spar7m_raw/scannet/archives
archive="$archive_dir/scannet-frames.zip"
url=https://huggingface.co/datasets/WHB139426/Scannet/resolve/main/scannet-frames.zip
expected_size=99134473611
expected_sha=fe61e7f728b75af10b8fdb8ac203bdfa7f27f6e205fa2f416ad36f6ca063fb13
validation="$acq/alternative_sources/validation/scannet"

mkdir -p "$archive_dir" "$validation"
curl --fail --location --retry 20 --retry-all-errors --retry-delay 10 \
  --continue-at - --output "$archive" "$url"

actual_size=$(stat -c '%s' "$archive")
if [[ "$actual_size" != "$expected_size" ]]; then
  echo "Size mismatch: expected=$expected_size actual=$actual_size" >&2
  exit 10
fi
printf '%s  %s\n' "$expected_sha" "$archive" | sha256sum --check

unzip -Z1 "$archive" > "$validation/archive_members.txt"
rg '[.]jpg$' "$validation/archive_members.txt" \
  | rg --no-filename -o 'scene[0-9]{4}_[0-9]{2}' \
  | sort -u > "$validation/present_scenes.txt"
comm -23 "$acq/scene_lists/scannet.txt" "$validation/present_scenes.txt" \
  > "$validation/missing_required_scenes.txt"

jq -r 'select(.base_dataset == "scannet") | .locator' \
  "$acq/required_accessible_media.jsonl" "$acq/required_withheld_media.jsonl" \
  | awk -F/ '{name=$6; sub(/[.]jpg$/, "", name); printf "%s/%d\n", $4, name}' \
  | sort -u > "$validation/expected_frames.txt"
rg '[.]jpg$' "$validation/archive_members.txt" \
  | sed -E 's#.*(scene[0-9]{4}_[0-9]{2})/(.*/)?([0-9]+)[.]jpg$#\1/\3#' \
  | awk -F/ 'NF == 2 {printf "%s/%d\n", $1, $2}' \
  | sort -u > "$validation/present_frames.txt"
comm -23 "$validation/expected_frames.txt" "$validation/present_frames.txt" \
  > "$validation/missing_required_frames.txt"

missing_count=$(wc -l < "$validation/missing_required_scenes.txt")
missing_frame_count=$(wc -l < "$validation/missing_required_frames.txt")
if [[ "$missing_count" -ne 0 || "$missing_frame_count" -ne 0 ]]; then
  echo "Missing required ScanNet content: scenes=$missing_count frames=$missing_frame_count" >&2
  exit 20
fi

printf 'archive=%s\nbytes=%s\nsha256=%s\nrequired_scenes=747\nmissing_scenes=0\nrequired_frames=%s\nmissing_frames=0\nstatus=PASS\n' \
  "$archive" "$actual_size" "$expected_sha" \
  "$(wc -l < "$validation/expected_frames.txt")" > "$validation/summary.txt"
echo SCANNET_DOWNLOAD_AND_VALIDATION_PASS
