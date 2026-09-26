#!/bin/bash
#SBATCH --job-name=sc_pss_v4_ddp
#SBATCH --partition=gpu
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --exclude=nid0642,nid0653,nid0661,nid0674,nid0684,nid0685,nid0687,nid0688,nid0694,nid0698
#SBATCH --cpus-per-task=8
#SBATCH --mem=128G
#SBATCH --gpus-per-node=2
#SBATCH --time=2-00:00:00
#SBATCH --array=0-9
#SBATCH --signal=B:USR1@1800
#SBATCH --output=artifacts/model_results/pss_20260922_v1/approved_v2/formal_training_v4/logs/%x_%A_%a.out
#SBATCH --error=artifacts/model_results/pss_20260922_v1/approved_v2/formal_training_v4/logs/%x_%A_%a.err
set -euo pipefail
# Do not send an unhandled USR1 to torchrun's supervisor. Both training ranks
# independently check the granted EndTime and synchronously stop at a boundary.
trap ':' USR1
module load python/gpu/3.12.5
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false
export HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
methods=(answer_natural answer_balanced cot_partial pss_l4 pss_full)
seeds=(20260922 20260923)
index="$SLURM_ARRAY_TASK_ID"
method="${methods[index/2]}"
seed="${seeds[index%2]}"
srun --cpu-bind=none --kill-on-bad-exit=1 python -m torch.distributed.run --standalone --nnodes=1 --nproc_per_node=2 './training/formal_training_v4/trainer.py' --method "$method" --seed "$seed"
python './training/formal_training_v4/control.py' finish --index "$index"
