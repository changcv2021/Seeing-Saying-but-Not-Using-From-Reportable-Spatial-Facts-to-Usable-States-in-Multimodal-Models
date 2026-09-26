#!/bin/bash
#SBATCH --job-name=sc_bundle_frames
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=runs/evaluation_bundle_v1_20260903/slurm/%x_%j.out
#SBATCH --error=runs/evaluation_bundle_v1_20260903/slurm/%x_%j.err

set -euo pipefail
module load python/3.12.11 ffmpeg/7.7.1
PROJECT_ROOT="./SpaceConflict"
BUNDLE_ROOT="external/project/iclr/spacebenchmark/SpaceConflict_Evaluation_Bundle_v1_20260903"
export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"
cd "$PROJECT_ROOT"
srun python scripts/materialize_mllm_video_frames.py \
  --input "$BUNDLE_ROOT/benchmark/l1_l3/evaluation/requested_samples.available.jsonl" \
  --output "$BUNDLE_ROOT/benchmark/l1_l3/evaluation/requested_samples.available.frames.jsonl" \
  --cache-root "$BUNDLE_ROOT/media/l1_l3_video_frames" \
  --report "$BUNDLE_ROOT/benchmark/l1_l3/evaluation/video_frame_materialization_report.json" \
  --frame-count 16 \
  --run-id spaceconflict_evaluation_bundle_video_frames_v1_20260903 \
  --seed 20260903 \
  --resume
