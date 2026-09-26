#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-guide-audit
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:05:00
#SBATCH --output=runs/guide_compliance_%j.out
#SBATCH --error=runs/guide_compliance_%j.err

set -euo pipefail
PROJECT_ROOT="./dataset"
GUIDE="$PROJECT_ROOT/../dataset_Codex_Benchmark_Build_Guide_CN.md"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src python scripts/audit_guide_compliance.py \
    --root "$PROJECT_ROOT" --guide "$GUIDE" \
    --release production_available_v1 --quota-version quota_production_available_v1 \
    --seed 20260826 \
    --output-json "$PROJECT_ROOT/reports/guide_compliance.production_available_v1.json" \
    --output-markdown "$PROJECT_ROOT/reports/guide_compliance.production_available_v1.md"
