#!/bin/bash
#SBATCH --job-name=sc_bundle_l123
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=04:00:00
#SBATCH --output=runs/evaluation_bundle_v1_20260903/slurm/%x_%j.out
#SBATCH --error=runs/evaluation_bundle_v1_20260903/slurm/%x_%j.err

set -euo pipefail
module load python/gpu/3.12.5
EVAL_ROOT="external/scratch/industbench_qwen25vl7b"
PROJECT_ROOT="./dataset"
STORAGE_ROOT="external/upstream"
BUNDLE_ROOT="external/project/iclr/spacebenchmark/SpaceConflict_Evaluation_Bundle_v1_20260903"
source "$EVAL_ROOT/venv/bin/activate"
export PYTHONPATH="$PROJECT_ROOT/src"
export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"
cd "$PROJECT_ROOT"
srun python scripts/prepare_mllm_v10_smoke.py \
  --storage-root "$STORAGE_ROOT" \
  --cache-root "$BUNDLE_ROOT/media/l1_l3" \
  --output-dir "$BUNDLE_ROOT/benchmark/l1_l3/evaluation" \
  --selection-mode all \
  --allow-rejects \
  --known-unavailable-revision 0fe664cbada1e7c1173fd743e0f781882eebf777 \
  --request-name requested_samples.available.jsonl \
  --reject-name media_unavailable.jsonl \
  --report-name media_resolution_report.json \
  --run-id spaceconflict_evaluation_bundle_v1_20260903 \
  --seed 20260903 \
  --resume
