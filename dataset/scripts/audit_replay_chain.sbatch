#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-replay-audit
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=runs/replay_chain_audit_%j.out
#SBATCH --error=runs/replay_chain_audit_%j.err

set -euo pipefail
PROJECT_ROOT="./dataset"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun python scripts/audit_replay_chain.py \
    --root "$PROJECT_ROOT" \
    --release pilot_verified_2k_v2 \
    --quota-version quota_pilot_2k_v2 \
    --unknown-version unknown_p1_v2 \
    --realization-version realization_p1_v2 \
    --canonical-version canonical_v4
