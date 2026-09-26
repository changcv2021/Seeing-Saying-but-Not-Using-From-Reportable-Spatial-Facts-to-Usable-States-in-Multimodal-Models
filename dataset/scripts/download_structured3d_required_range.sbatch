#!/usr/bin/env bash
#SBATCH --job-name=sc_struct3d_rgb
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=06:00:00
#SBATCH --output=artifacts/upstream_media/spar7m_acquisition/slurm/structured3d_download_%j.out
#SBATCH --error=artifacts/upstream_media/spar7m_acquisition/slurm/structured3d_download_%j.err

set -euo pipefail
umask 0007
module load python/3.12.11

acq=artifacts/upstream_media/spar7m_acquisition
raw=artifacts/upstream_media/spar7m_raw/structured3d
script='./dataset/scripts/extract_structured3d_remote_zip.py'

report="$acq/alternative_sources/validation/structured3d/full_extract_report.json"
if [[ -f "$report" ]]; then cp -n "$report" "${report}.before_${SLURM_JOB_ID}"; fi

snapshot="$acq/alternative_sources/recovery_${SLURM_JOB_ID}"
mkdir -p "$snapshot"
cp "$script" "$snapshot/extract_structured3d_remote_zip.py"
cp "$acq/acquisition_config.yaml" "$snapshot/acquisition_config.yaml"
cp './dataset/scripts/download_structured3d_required_range.sbatch' "$snapshot/"
sha256sum "$snapshot/extract_structured3d_remote_zip.py" "$acq/required_accessible_media.jsonl" "$acq/required_withheld_media.jsonl" > "$snapshot/input_code.sha256"
script="$snapshot/extract_structured3d_remote_zip.py"

python -u "$script" --resume --rounds 3 --run-id "structured3d_retry_v3_${SLURM_JOB_ID}" \
  --accessible "$acq/required_accessible_media.jsonl" \
  --withheld "$acq/required_withheld_media.jsonl" \
  --output-root "$raw" \
  --report "$acq/alternative_sources/validation/structured3d/full_extract_report.json"

jq -e '.status == "PASS" and .requested == 855 and .passed == 855 and .failed == 0' \
  "$acq/alternative_sources/validation/structured3d/full_extract_report.json" >/dev/null

accessible_count=$(find "$raw/materialized/spar/structured3d/images" -type f -name '*.jpg' -printf '.' | wc -c)
withheld_count=$(find "$raw/withheld_source_png" -type f -name 'rgb_rawlight.png' -printf '.' | wc -c)
# Eleven withheld locators are also accessible for OTHER questions. Their PNGs
# are stored once under source_png; Unknown prompt exclusion remains per sample.
if [[ "$accessible_count" -ne 708 || "$withheld_count" -ne 147 ]]; then
  echo "Materialized count mismatch: accessible=$accessible_count withheld=$withheld_count" >&2
  exit 20
fi

echo STRUCTURED3D_DOWNLOAD_AND_VALIDATION_PASS
