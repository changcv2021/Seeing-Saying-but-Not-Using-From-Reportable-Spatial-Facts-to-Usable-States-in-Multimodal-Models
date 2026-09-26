#!/usr/bin/env bash
#SBATCH --job-name=sc_s3d_probe
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:15:00
#SBATCH --output=artifacts/upstream_media/spar7m_acquisition/slurm/structured3d_probe_%j.out
#SBATCH --error=artifacts/upstream_media/spar7m_acquisition/slurm/structured3d_probe_%j.err

set -euo pipefail
module load python/3.12.11

acq=artifacts/upstream_media/spar7m_acquisition
raw=artifacts/upstream_media/spar7m_raw/structured3d
script='./dataset/scripts/extract_structured3d_remote_zip.py'

python "$script" \
  --accessible "$acq/required_accessible_media.jsonl" \
  --withheld "$acq/required_withheld_media.jsonl" \
  --output-root "$raw" \
  --report "$acq/probes/structured3d_scene_00006.json" \
  --only-scene scene_00006
