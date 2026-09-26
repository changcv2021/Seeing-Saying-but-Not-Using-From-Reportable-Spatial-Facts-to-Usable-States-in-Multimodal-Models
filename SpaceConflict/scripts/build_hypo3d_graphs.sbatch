#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-hypo3d-graphs
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=runs/hypo3d_graphs_%j.out
#SBATCH --error=runs/hypo3d_graphs_%j.err

set -euo pipefail

PROJECT_ROOT="./SpaceConflict"
SEED=20260826
JOB_TAG="${SLURM_JOB_ID:-manual}"
WORLD_INDEX_VERSION="world_index_hypo3d_v1"
SPLIT_VERSION="world_split_hypo3d_v1"
WORLD_GRAPH_VERSION="world_graph_hypo3d_v1"
RESULT_DIR="${PROJECT_ROOT}/runs/hypo3d_graphs_${JOB_TAG}"

mkdir -p "$RESULT_DIR"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src pytest -q >"${RESULT_DIR}/pytest.txt"
srun env PYTHONPATH=src python -m spaceconflict.cli validate-contract \
    --dataset hypo3d --seed "$SEED" --run-id "hypo3d_contract_${JOB_TAG}" \
    --workers 1 --resume >"${RESULT_DIR}/contract.json"
srun env PYTHONPATH=src python -m spaceconflict.cli build-world-index \
    --dataset hypo3d --world-index-version "$WORLD_INDEX_VERSION" \
    --seed "$SEED" --run-id "${WORLD_INDEX_VERSION}_${JOB_TAG}" \
    --workers 1 --resume >"${RESULT_DIR}/world_index.json"
srun env PYTHONPATH=src python -m spaceconflict.cli split-worlds \
    --world-index-version "$WORLD_INDEX_VERSION" --split-version "$SPLIT_VERSION" \
    --seed "$SEED" --run-id "${SPLIT_VERSION}_${JOB_TAG}" \
    --workers 1 --resume >"${RESULT_DIR}/world_split.json"

# A partial graph-build status is allowed only when rejected worlds retain
# structured reject codes; validate-graphs independently checks that invariant.
set +e
srun env PYTHONPATH=src python -m spaceconflict.cli build-graphs \
    --dataset hypo3d --world-index-version "$WORLD_INDEX_VERSION" \
    --split-version "$SPLIT_VERSION" --world-graph-version "$WORLD_GRAPH_VERSION" \
    --seed "$SEED" --run-id "${WORLD_GRAPH_VERSION}_${JOB_TAG}" \
    --workers 1 --resume >"${RESULT_DIR}/world_graph.json"
GRAPH_RC=$?
set -e
if [[ "$GRAPH_RC" != 0 && "$GRAPH_RC" != 2 ]]; then
    exit "$GRAPH_RC"
fi
srun env PYTHONPATH=src python -m spaceconflict.cli validate-graphs \
    --dataset hypo3d --world-graph-version "$WORLD_GRAPH_VERSION" \
    --seed "$SEED" --run-id "validate_${WORLD_GRAPH_VERSION}_${JOB_TAG}" \
    --workers 1 --resume >"${RESULT_DIR}/graph_validation.json"
