#!/bin/bash
#SBATCH --job-name=sc_repair_s3d_views
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=04:00:00
#SBATCH --output=artifacts/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v2_scans_20260905/slurm/repair_s3d_%j.out
#SBATCH --error=artifacts/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v2_scans_20260905/slurm/repair_s3d_%j.err
set -euo pipefail
umask 0007
module load python/3.12.11
bundle=artifacts
run="$bundle/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v2_scans_20260905"
project='./SpaceConflict'
out="$bundle/upstream_media/spar7m_acquisition/repair_missing_v2_20260905"
python "$run/code_repair_v2/plan_missing_media_repair.py" --bundle "$bundle" --project "$project" --output "$out" --run-id missing_media_repair_20260905 --seed 20260905 --resume
python -u "$run/code_repair_v2/extract_structured3d_remote_zip.py" --accessible "$out/required_accessible.jsonl" \
  --withheld "$out/withheld_not_requested.jsonl" --output-root "$bundle/upstream_media/spar7m_raw/structured3d" \
  --report "$out/structured3d_report.json" --rounds 2 --seed 20260905 --run-id s3d_expanded_repair_20260905 --resume
