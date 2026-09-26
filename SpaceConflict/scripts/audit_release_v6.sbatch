#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-release-audit
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=runs/release_audit_%j.out
#SBATCH --error=runs/release_audit_%j.err

set -euo pipefail
PROJECT_ROOT="./SpaceConflict"
module load python/3.12.11
cd "$PROJECT_ROOT"
srun python scripts/audit_release.py --root "$PROJECT_ROOT" --release golden_verified_slice_v6
