#!/bin/bash
#SBATCH --job-name=sc_bundle_copy
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=02:00:00
#SBATCH --output=runs/evaluation_bundle_copy_20260903/slurm/%x_%j.out
#SBATCH --error=runs/evaluation_bundle_copy_20260903/slurm/%x_%j.err

set -euo pipefail

SOURCE="external/project/iclr/spacebenchmark/SpaceConflict_Evaluation_Bundle_v1_20260903"
TARGET="artifacts"
EXPECTED_FILES=17975
EXPECTED_BYTES=27110099290

test -d "$SOURCE"
test -f "$SOURCE/MANIFEST.json"
test -f "$SOURCE/SHA256SUMS"
mkdir -p "$TARGET"

echo "source=$SOURCE"
echo "target=$TARGET"
echo "copy_started_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"

srun rsync -a --partial --info=stats2 "$SOURCE/" "$TARGET/"

cd "$TARGET"
srun sha256sum --quiet -c SHA256SUMS

read -r actual_files actual_bytes < <(
  find . -type f -printf '%s\n' | awk '{files += 1; bytes += $1} END {print files, bytes}'
)

if [[ "$actual_files" -ne "$EXPECTED_FILES" ]]; then
  echo "FILE_COUNT_MISMATCH expected=$EXPECTED_FILES actual=$actual_files" >&2
  exit 2
fi
if [[ "$actual_bytes" -ne "$EXPECTED_BYTES" ]]; then
  echo "BYTE_COUNT_MISMATCH expected=$EXPECTED_BYTES actual=$actual_bytes" >&2
  exit 3
fi

source_manifest_sha256=$(sha256sum "$SOURCE/MANIFEST.json" | awk '{print $1}')
target_manifest_sha256=$(sha256sum "$TARGET/MANIFEST.json" | awk '{print $1}')
if [[ "$source_manifest_sha256" != "$target_manifest_sha256" ]]; then
  echo "MANIFEST_HASH_MISMATCH" >&2
  exit 4
fi

chmod 2770 "$TARGET"

echo "status=PASS"
echo "files=$actual_files"
echo "bytes=$actual_bytes"
echo "manifest_sha256=$target_manifest_sha256"
echo "copy_finished_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
