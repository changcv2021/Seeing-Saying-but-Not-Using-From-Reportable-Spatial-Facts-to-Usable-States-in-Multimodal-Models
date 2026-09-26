#!/usr/bin/env bash
#SBATCH --job-name=sc_s3d_fix_validate
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:20:00
#SBATCH --output=artifacts/upstream_media/spar7m_acquisition/slurm/structured3d_validate_%j.out
#SBATCH --error=artifacts/upstream_media/spar7m_acquisition/slurm/structured3d_validate_%j.err
set -euo pipefail
umask 0007
module load python/3.12.11
acq=artifacts/upstream_media/spar7m_acquisition
script='./dataset/scripts/extract_structured3d_remote_zip.py'
snapshot="$acq/alternative_sources/recovery_validation_${SLURM_JOB_ID}"
mkdir -p "$snapshot"
cp "$script" "$snapshot/"
sha256sum "$snapshot/extract_structured3d_remote_zip.py" "$acq/required_accessible_media.jsonl" "$acq/required_withheld_media.jsonl" > "$snapshot/input_code.sha256"
python -u "$snapshot/extract_structured3d_remote_zip.py" --resume --rounds 1 \
  --run-id "structured3d_fix_validation_${SLURM_JOB_ID}" --only-scene scene_00806 --limit 1 \
  --accessible "$acq/required_accessible_media.jsonl" --withheld "$acq/required_withheld_media.jsonl" \
  --output-root artifacts/upstream_media/spar7m_raw/structured3d \
  --report "$snapshot/report.json"
jq -e '.status == "PASS" and .passed == 1 and .failed == 0' "$snapshot/report.json"
