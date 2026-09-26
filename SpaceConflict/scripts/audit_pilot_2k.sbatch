#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-pilot-audit
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=runs/pilot_audit_%j.out
#SBATCH --error=runs/pilot_audit_%j.err

set -euo pipefail
PROJECT_ROOT="./SpaceConflict"
module load python/3.12.11
cd "$PROJECT_ROOT"
srun python scripts/analyze_pilot_2k.py \
    --root "$PROJECT_ROOT" --run-dir "$PROJECT_ROOT/runs/pilot_2k_8074928" \
    --wall-seconds 177 --allocated-cpus 2
srun python scripts/audit_release.py \
    --root "$PROJECT_ROOT" --release pilot_verified_2k_v1 \
    --quota-version quota_pilot_2k_v1 --unknown-version unknown_p1_v1 \
    --split-version world_split_v6
