#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-ca-preflight
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:05:00
#SBATCH --output=runs/ca_profile_preflight_%j.out
#SBATCH --error=runs/ca_profile_preflight_%j.err

set -euo pipefail
PROJECT_ROOT="./dataset"
DATA_ROOT="external/upstream/data/full_media_incoming/ca_vqa/080812355c21a40f437ed03d4ae558d35bfa2929"
DOWNLOAD_RUN="$PROJECT_ROOT/runs/download_ca_vqa_slurm_8073172"
RUN_DIR="$PROJECT_ROOT/runs/ca_profile_preflight_${SLURM_JOB_ID}"
mkdir -p "$RUN_DIR"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun python - <<'PY'
import json
import tensorflow as tf
print(json.dumps({"status": "TENSORFLOW_IMPORT_PASS", "tensorflow_version": tf.__version__}))
PY
srun python scripts/profile_ca_vqa.py \
    --data-root "$DATA_ROOT" --download-run "$DOWNLOAD_RUN" \
    --output "$RUN_DIR/profile.preflight.json" --allow-incomplete
srun python - "$RUN_DIR/profile.preflight.json" <<'PY'
import json, sys
from pathlib import Path
row = json.loads(Path(sys.argv[1]).read_text())
if row["status"] != "PILOT_PROFILED" or set(row["task_profiles"]) != {
    "binary", "cardinality", "grounding2d", "grounding3d", "multichoice", "regression"
}:
    raise SystemExit("CA_PROFILE_PREFLIGHT_INCOMPLETE")
if any(not value["first_record_feature_summary"] for value in row["task_profiles"].values()):
    raise SystemExit("CA_PROFILE_PREFLIGHT_TFRECORD_PARSE_FAILED")
print(json.dumps({
    "status": "PASS", "task_count": len(row["task_profiles"]),
    "train_examples_from_dataset_info": row["train_examples_from_dataset_info"],
}))
PY
