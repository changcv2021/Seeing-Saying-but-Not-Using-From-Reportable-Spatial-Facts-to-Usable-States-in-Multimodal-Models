#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-log-audit
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:10:00
#SBATCH --output=runs/logging_regression_%j.out
#SBATCH --error=runs/logging_regression_%j.err

set -euo pipefail
PROJECT_ROOT="./dataset"
RUN_ID="logging_regression_${SLURM_JOB_ID}"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src pytest -q
srun env PYTHONPATH=src python -m spaceconflict.cli validate-contract \
    --dataset all --run-id "$RUN_ID" --resume
srun python - "$PROJECT_ROOT/runs/$RUN_ID/validate-contract.json" <<'PY'
import json, sys
from pathlib import Path
row = json.loads(Path(sys.argv[1]).read_text())
required = {
    "run_id", "timestamp_utc", "config_snapshot", "git_commit", "dataset_revisions",
    "seed", "input_hashes", "output_hashes", "status_counts",
    "counts", "exception",
}
missing = sorted(required - set(row))
if missing:
    raise SystemExit(f"MISSING_RUN_ENVELOPE_FIELDS:{missing}")
if row["result_status"] != "PASS" or row["exception"] is not None:
    raise SystemExit("RUN_ENVELOPE_STATUS_INVALID")
if len(row["dataset_revisions"]) < 5:
    raise SystemExit("DATASET_REVISIONS_INCOMPLETE")
print(json.dumps({"status": "PASS", "run_id": row["run_id"], "field_count": len(row)}))
PY
