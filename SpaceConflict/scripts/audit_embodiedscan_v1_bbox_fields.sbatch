#!/bin/bash
#SBATCH --job-name=embodiedscan_v1_bbox_audit
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=00:20:00
#SBATCH --output=runs/embodiedscan_v1_bbox_audit_%j.out
#SBATCH --error=runs/embodiedscan_v1_bbox_audit_%j.err

set -euo pipefail

project_dir="./SpaceConflict"
annotation="external/upstream/data/full_media_incoming/hypo3d/official/embodiedscan_v1/annotations/embodiedscan_infos_train.pkl"

cd "${project_dir}"
module load python/3.12.11

PYTHONPATH=src srun python - "${annotation}" <<'PY'
import json
import sys
from pathlib import Path

from spaceconflict.hypo3d_l4.restricted_pickle import load_restricted_annotation_pickle

payload = load_restricted_annotation_pickle(Path(sys.argv[1]))
rows = payload.get("data_list") or payload.get("infos") or []
for item in rows:
    instances = item.get("instances") if isinstance(item, dict) else None
    if not isinstance(instances, list) or not instances:
        continue
    instance = next((value for value in instances if isinstance(value, dict)), None)
    if instance is None:
        continue
    summary = {
        "item_keys": sorted(item),
        "instance_keys": sorted(instance),
        "instance_field_types": {key: type(value).__name__ for key, value in sorted(instance.items())},
        "bbox_3d": instance.get("bbox_3d"),
        "bbox_label_3d": instance.get("bbox_label_3d"),
        "sample_idx": item.get("sample_idx"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    break
else:
    raise SystemExit("No instance-bearing data row found")
PY
