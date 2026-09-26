#!/usr/bin/env bash
set -euo pipefail
# CPU-only collector template. Schedule afterany, not as evidence of complete success.
if [[ $# -ne 2 ]]; then
  echo "usage: $0 REPO_ROOT RUN_ROOT" >&2; exit 2
fi
cd "$1"
python -m spatial_world_state_study.collect --run-root "$2" --allow-partial --never-impute-missing
