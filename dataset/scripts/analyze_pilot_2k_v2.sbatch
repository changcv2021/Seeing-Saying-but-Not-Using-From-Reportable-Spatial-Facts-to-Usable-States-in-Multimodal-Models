#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-pilot-v2-analysis
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=runs/pilot_v2_analysis_%j.out
#SBATCH --error=runs/pilot_v2_analysis_%j.err

set -euo pipefail
PROJECT_ROOT="./dataset"
module load python/3.12.11
cd "$PROJECT_ROOT"
srun python scripts/analyze_pilot_2k.py \
    --root "$PROJECT_ROOT" \
    --run-dir "$PROJECT_ROOT/runs/pilot_rebalance_8075122" \
    --structural-run-dir "$PROJECT_ROOT/runs/pilot_2k_8074928" \
    --wall-seconds 374 --allocated-cpus 2 \
    --proof-version proof_verification_p1_v2 \
    --quota-version quota_pilot_2k_v2 \
    --release pilot_verified_2k_v2
