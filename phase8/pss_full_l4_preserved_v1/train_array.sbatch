#!/bin/bash
#SBATCH --job-name=sc_pss_l4_preserved
#SBATCH --partition=gpu
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=128G
#SBATCH --gpus-per-node=2
#SBATCH --time=2-00:00:00
#SBATCH --array=0-1
#SBATCH --exclude=nid0642,nid0653,nid0661,nid0674,nid0684,nid0685,nid0687,nid0688,nid0694,nid0698
#SBATCH --signal=B:USR1@1800
#SBATCH --output=artifacts/model_results/pss_20260922_v1/approved_v2/pss_full_l4_preserved_v1/logs/%x_%A_%a.out
#SBATCH --error=artifacts/model_results/pss_20260922_v1/approved_v2/pss_full_l4_preserved_v1/logs/%x_%A_%a.err
set -euo pipefail
trap ':' USR1
module load python/gpu/3.12.5
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false
export HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
preserved_code='./phase8/pss_full_l4_preserved_v1'
preserved_python='python'
seeds=(20260922 20260923)
seed="${seeds[$SLURM_ARRAY_TASK_ID]}"
preserved_output="artifacts/model_results/pss_20260922_v1/approved_v2/pss_full_l4_preserved_v1/seed_${seed}"
srun --cpu-bind=none --kill-on-bad-exit=1 "$preserved_python" "$preserved_code/smoke.py" --seed "$seed"
srun --cpu-bind=none --kill-on-bad-exit=1 "$preserved_python" -m torch.distributed.run --standalone --nnodes=1 --nproc_per_node=2 "$preserved_code/trainer.py" --output "$preserved_output" --method pss_full_l4_preserved --seed "$seed"
"$preserved_python" "$preserved_code/control.py" finish --seed "$seed"
