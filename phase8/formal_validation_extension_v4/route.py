"""CPU routing: immediately admit if done, otherwise request only necessary GPUs."""
import os
from pathlib import Path
import subprocess
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'formal_training_v4'))
from plan import OUTPUT,read
from trainer import check_plan
from control import submit
PYTHON='python'


def main():
    if not os.environ.get('SLURM_JOB_ID'):raise ValueError('SLURM_REQUIRED')
    check_plan(OUTPUT)
    if (OUTPUT/'GPU_ACCEPTANCE.json').exists():
        subprocess.run([PYTHON,str(HERE.parent/'formal_training_v4/control.py'),'admit'],check=True)
        return
    boundaries=list((OUTPUT/'smoke').glob('*/attempts/*/CONTINUATION_REQUIRED.json'))
    if not boundaries or any(read(p)['reason']!='SIGNAL_OR_ALLOCATION_END' for p in boundaries):
        raise ValueError('UNKNOWN_FAILURE_REQUIRES_DIAGNOSIS_NO_AUTORETRY')
    submit(['sbatch','--parsable',str(HERE/'continue.sbatch')],
        OUTPUT/'VALIDATION_EXTENSION_INTENT.json',OUTPUT/'VALIDATION_EXTENSION_SUBMITTED.json')
    job=read(OUTPUT/'VALIDATION_EXTENSION_SUBMITTED.json')['job_id']
    submit(['sbatch','--parsable','--dependency=afterok:'+job,'--kill-on-invalid-dep=yes',
            str(HERE.parent/'formal_training_v4/admit.sbatch')],
        OUTPUT/'EXTENSION_ADMISSION_INTENT.json',OUTPUT/'EXTENSION_ADMISSION_SUBMITTED.json')


if __name__=='__main__':main()
