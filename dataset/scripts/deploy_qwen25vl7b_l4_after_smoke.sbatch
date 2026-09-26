#!/bin/bash
#SBATCH --job-name=sc_qwen25vl7b_deploy
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:10:00
#SBATCH --output=runs/mllm/qwen2_5_vl_7b/l4_balanced_test_v3_20260903/slurm/%x_%j.out
#SBATCH --error=runs/mllm/qwen2_5_vl_7b/l4_balanced_test_v3_20260903/slurm/%x_%j.err

set -euo pipefail
module load python/3.12.11
PROJECT_ROOT="./dataset"
cd "$PROJECT_ROOT"
python scripts/deploy_qwen25vl7b_l4_after_smoke.py

