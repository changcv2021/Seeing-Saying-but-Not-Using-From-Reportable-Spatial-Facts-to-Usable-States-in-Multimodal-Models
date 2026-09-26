#!/bin/bash
#SBATCH --job-name=sc_view_plan_audit
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:10:00
#SBATCH --output=artifacts/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v2_scans_20260905/slurm/view_plan_%j.out
#SBATCH --error=artifacts/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v2_scans_20260905/slurm/view_plan_%j.err
set -euo pipefail
module load python/3.12.11
project='./dataset'
bundle=artifacts
run="$bundle/model_results/qwen2_5_vl_7b/full_release_qwen35judge_v2_scans_20260905"
srun python "$run/code/audit_spar_plans.py" --bundle "$bundle" --project "$project" --output "$run/view_plan_audit.json" --run-id spar_view_plan_20260905 --seed 20260905
