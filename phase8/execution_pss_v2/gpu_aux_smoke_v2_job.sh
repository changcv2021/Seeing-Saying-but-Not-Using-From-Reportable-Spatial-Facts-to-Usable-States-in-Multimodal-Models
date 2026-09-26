#!/bin/bash
#SBATCH --job-name=sc_pss_9b_aux_smoke_v2
#SBATCH --partition=gpu
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --gpus-per-node=1
#SBATCH --time=02:00:00
#SBATCH --exclude=nid0642,nid0653,nid0661,nid0674,nid0684,nid0685,nid0687,nid0688,nid0694,nid0698
#SBATCH --output=artifacts/model_results/pss_20260922_v1/approved_v2/logs/%x_%j.out
#SBATCH --error=artifacts/model_results/pss_20260922_v1/approved_v2/logs/%x_%j.err
set -euo pipefail
module load python/gpu/3.12.5
export OMP_NUM_THREADS=4
export TOKENIZERS_PARALLELISM=false
export HF_HUB_OFFLINE=1
export HF_HUB_DISABLE_TELEMETRY=1
export PYTHONUNBUFFERED=1
exec python './phase8/execution_pss_v2/aux_smoke_v2.py'

