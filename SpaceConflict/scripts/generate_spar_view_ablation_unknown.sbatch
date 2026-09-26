#!/usr/bin/env bash
#SBATCH --job-name=spaceconf-spar-unknown
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=runs/spar_view_ablation_unknown_%j.out
#SBATCH --error=runs/spar_view_ablation_unknown_%j.err

set -euo pipefail
PROJECT_ROOT="./SpaceConflict"
module load python/3.12.11
cd "$PROJECT_ROOT"

srun env PYTHONPATH=src python scripts/generate_spar_view_ablation_unknown.py \
    --root "$PROJECT_ROOT" \
    --l1-proofs candidates/auto_accepted/pairs.proof_verification_spar_7m_l1_v1.jsonl \
    --l3-proofs candidates/auto_accepted/pairs.proof_verification_spar_7m_l3_xform_v1.jsonl \
    --l3-ablations verifier_outputs/spar_7m_l3_xform_ablation.v1.jsonl \
    --media-index data/media_index/spar/0fe664cbada1e7c1173fd743e0f781882eebf777/qualitative_relation_media.v2.jsonl \
    --target 1177 --seed 20260826 --run-id "spar_view_ablation_unknown_${SLURM_JOB_ID}" --resume
