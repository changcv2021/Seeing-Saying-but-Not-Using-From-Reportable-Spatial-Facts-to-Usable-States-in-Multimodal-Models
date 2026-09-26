#!/bin/bash
#SBATCH --job-name=sc_export_r6
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=artifacts/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v2_scans_20260905/slurm/recover_export_%j.out
#SBATCH --error=artifacts/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v2_scans_20260905/slurm/recover_export_%j.err
set -euo pipefail
umask 0007
module load python/3.12.11
bundle=artifacts
run="$bundle/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v2_scans_20260905"
project='./SpaceConflict'
python "$run/code_prepare_r6/test_protocol.py"
python "$run/code_prepare_r6/test_scan_integration.py"
srun python -u "$run/code_prepare_r6/prepare.py" --bundle "$bundle" --project "$project" --run-root "$run" \
  --run-id full_release_qwen35judge_v2_scans_20260905 --seed 20260904 --resume \
  --spar-assets "$bundle/upstream_media/spar7m_acquisition/integration_v1_20260905/assets.jsonl"
