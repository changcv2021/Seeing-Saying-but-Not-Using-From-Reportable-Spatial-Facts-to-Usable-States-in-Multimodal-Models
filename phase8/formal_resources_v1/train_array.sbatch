#!/bin/bash
# Versioned formal trainer: admission is checked before submission and execution.
#SBATCH --job-name=sc_pss_formal
#SBATCH --partition=gpu
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --gpus-per-node=1
#SBATCH --time=2-00:00:00
#SBATCH --array=0-9
#SBATCH --signal=USR1@1800
#SBATCH --exclude=nid0642,nid0653,nid0661,nid0674,nid0684,nid0685,nid0687,nid0688,nid0694,nid0698
#SBATCH --output=artifacts/model_results/pss_20260922_v1/approved_v2/formal_training_v1/logs/%x_%A_%a.out
#SBATCH --error=artifacts/model_results/pss_20260922_v1/approved_v2/formal_training_v1/logs/%x_%A_%a.err
set -euo pipefail
module load python/gpu/3.12.5
export OMP_NUM_THREADS=4
export TOKENIZERS_PARALLELISM=false
export HF_HUB_OFFLINE=1
export HF_HUB_DISABLE_TELEMETRY=1
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1
# No %N array throttle, no inter-arm/seed dependencies, and no exclusive nodes.
set +e
srun --kill-on-bad-exit=1 python './phase8/formal_resources_v1/resource_tools.py' --run-index "$SLURM_ARRAY_TASK_ID"
status=$?
set -e
if [ "$status" -eq 75 ]; then
    # Only a committed allocation-boundary checkpoint can authorize continuation.
    python './phase8/formal_training_v3/continuation.py' --index "$SLURM_ARRAY_TASK_ID"
else
    exit "$status"
fi
