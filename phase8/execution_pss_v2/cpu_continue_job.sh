#!/bin/bash
#SBATCH --partition=debug
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:45:00
#SBATCH --output=artifacts/model_results/pss_20260922_v1/approved_v2/logs/%x_%j.out
#SBATCH --error=artifacts/model_results/pss_20260922_v1/approved_v2/logs/%x_%j.err
set -euo pipefail
module load python/gpu/3.12.5
export OMP_NUM_THREADS=2
case "$1" in
 verify_environment.py|build_supervision.py|build_supervision_v2.py|build_supervision_v3.py|prepare_supervision.py|inspect_sources.py|build_trajectory_aux.py|processor_probe.py|freeze_partial_cot.py|finalize_data.py|preserve_state_context.py|processor_probe_v2.py|finalize_data_v2.py) step="$1";;
 *) exit 2;;
esac
exec python "./phase8/execution_pss_v2/${step}" --resume
