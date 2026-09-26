#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-reconstruct-refresh
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:15:00
#SBATCH --output=runs/reconstruct_refresh_%j.out
#SBATCH --error=runs/reconstruct_refresh_%j.err

set -euo pipefail
PROJECT_ROOT="./dataset"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src python -m spaceconflict.cli reconstruct-source-qa \
    --dataset ca_vqa,spar,sti_bench,vsi_bench,omnispatial \
    --resume \
    --run-id "reconstruct_refresh_${SLURM_JOB_ID}"
