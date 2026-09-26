#!/bin/bash
#SBATCH --job-name=sc_v10_frames_r3
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:20:00
#SBATCH --output=runs/mllm/qwen2_5_vl_7b/production_available_v10_smoke_r3_20260903/slurm/%x_%j.out
#SBATCH --error=runs/mllm/qwen2_5_vl_7b/production_available_v10_smoke_r3_20260903/slurm/%x_%j.err

set -euo pipefail
module load python/3.12.11 ffmpeg/7.7.1
PROJECT_ROOT="./SpaceConflict"
SOURCE_RUN="$PROJECT_ROOT/runs/mllm/qwen2_5_vl_7b/production_available_v10_smoke_r3_media_20260903"
RUN_ROOT="$PROJECT_ROOT/runs/mllm/qwen2_5_vl_7b/production_available_v10_smoke_r3_20260903"
FRAME_CACHE="external/upstream/evaluation_cache/qwen2_5_vl_7b/production_available_v10_smoke_r3_20260903/video_frames_v1"
export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"
cd "$PROJECT_ROOT"
srun python scripts/materialize_mllm_video_frames.py \
  --input "$SOURCE_RUN/requested_samples.smoke.jsonl" \
  --output "$RUN_ROOT/requested_samples.smoke.jsonl" \
  --cache-root "$FRAME_CACHE" \
  --report "$RUN_ROOT/video_frame_materialization_report.json" \
  --frame-count 16 \
  --run-id qwen25vl7b_v10_cross_source_smoke_r3_20260903 \
  --seed 20260903
