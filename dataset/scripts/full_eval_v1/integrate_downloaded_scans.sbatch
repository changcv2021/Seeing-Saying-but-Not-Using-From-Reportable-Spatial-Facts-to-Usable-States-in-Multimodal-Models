#!/bin/bash
#SBATCH --job-name=sc_integrate_scans
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=02:00:00
#SBATCH --output=artifacts/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v1_20260904/slurm/integrate_scans_%j.out
#SBATCH --error=artifacts/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v1_20260904/slurm/integrate_scans_%j.err
set -euo pipefail
umask 0007
module load python/3.12.11
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
project='./dataset'
bundle=artifacts
code="$bundle/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v1_20260904/code_prepare_r5"
python "$code/test_protocol.py"
python "$code/test_scan_integration.py"
if [[ "${1:-full}" == tests ]]; then exit 0; fi
srun python -u "$code/integrate_downloaded_scans.py" --bundle "$bundle" --project "$project" \
  --output "$bundle/upstream_media/spar7m_acquisition/integration_v1_20260905" \
  --run-id scans_integration_v1_20260905 --seed 20260905 --workers 4 --resume
