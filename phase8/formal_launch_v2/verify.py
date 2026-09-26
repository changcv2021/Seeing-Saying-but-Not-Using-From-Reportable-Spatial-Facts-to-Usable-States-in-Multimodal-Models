"""Verify a launch-only override without changing the scientific runtime."""
import json
import os
from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'formal_training_v3'))
from paths import OUTPUT, read, sha, write

def verify():
    manifest = read(HERE/'LAUNCH_OVERRIDE.json')
    for path, expected in manifest['file_hashes'].items():
        if sha(path) != expected:
            raise ValueError('LAUNCH_OVERRIDE_CHANGED:'+path)
    runtime = read(OUTPUT/'TRAINING_RUNTIME.json')
    if sha(OUTPUT/'TRAINING_RUNTIME.json') != manifest['runtime_sha256']:
        raise ValueError('SCIENTIFIC_RUNTIME_CHANGED')
    for group in ('code_hashes','run_config_hashes','resource_launcher_hashes'):
        for path, expected in runtime[group].items():
            if sha(path) != expected:
                raise ValueError('ORIGINAL_FROZEN_FILE_CHANGED:'+path)
    if os.environ.get('SLURM_JOB_ID'):
        receipt = dict(manifest=manifest, job_id=os.environ['SLURM_JOB_ID'],
            array_index=os.environ.get('SLURM_ARRAY_TASK_ID'),
            cpu_binding_override='srun --cpu-bind=none')
        path = OUTPUT/'launch_receipts'/('bind2_'+os.environ['SLURM_JOB_ID']+'.json')
        if path.exists():
            if read(path) != receipt: raise ValueError('LAUNCH_RECEIPT_CHANGED')
        else:
            write(path, receipt)
    print('PASS_LAUNCH_OVERRIDE_SCIENTIFIC_RUNTIME_UNCHANGED', flush=True)
    return manifest

if __name__ == '__main__': verify()
