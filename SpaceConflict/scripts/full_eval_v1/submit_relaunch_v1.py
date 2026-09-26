"""Normal Slurm resubmission after user-reported administrator clearance; no hold manipulation."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

STAGES = [
    ('preflight', 'debug', 1, '8G', 0, '00:30:00', None, None),
    ('smoke', 'gpu', 4, '64G', 1, '01:00:00', 'afterok:preflight', None),
    ('infer', 'gpu', 4, '64G', 1, '04:00:00', 'afterok:smoke', '0-7%2'),
    ('score', 'general', 1, '8G', 0, '00:30:00', 'afterany:infer', None),
    ('judge', 'gpu', 4, '32G', 1, '06:00:00', 'afterok:infer', '0-7%2'),
    ('final', 'general', 1, '8G', 0, '00:30:00', 'afterany:judge:score', None),
]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-root', type=Path, required=True)
    p.add_argument('--run-id', required=True)
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--resume', action='store_true')
    p.add_argument('--seed', type=int, default=20260904)
    p.add_argument('--limit', type=int)
    a = p.parse_args()
    if a.limit is not None: p.error('Use the mandatory smoke gate, not a limited full submission')
    sys.path.insert(0, str(a.run_root / 'code'))
    from common import write, sha
    cfg = json.loads((a.run_root / 'config.json').read_text())
    if cfg['run_id'] != a.run_id or cfg['seed'] != a.seed:
        raise ValueError('RUN_CONFIG_MISMATCH')
    approval = a.run_root / 'relaunch_authorization_20260905.json'
    if json.loads(approval.read_text())['basis'] != 'USER_REPORTED_ADMINISTRATOR_NO_OBJECTION':
        raise ValueError('RELAUNCH_AUTHORITY_RECORD_MISSING')
    dest = a.run_root / 'relaunch_submission_20260905.json'
    record = json.loads(dest.read_text()) if dest.exists() else dict(run_id=a.run_id, seed=a.seed,
        status='SUBMITTING', authority_record_sha256=sha(approval), config_sha256=sha(a.run_root/'config.json'),
        submitter_code_sha256=sha(__file__), jobs={})
    if record['jobs'] and not a.resume: raise FileExistsError(dest)
    for name, partition, cpus, ram, gpus, wall, dependency, array in STAGES:
        if name in record['jobs']: continue
        cmd = ['sbatch', '--parsable', '--job-name=sc7b_relaunch_'+name, '--partition='+partition,
               '--account=YOUR_ACCOUNT', '--qos=allocated', '--nodes=1', '--ntasks=1',
               f'--cpus-per-task={cpus}', '--mem='+ram, '--time='+wall,
               '--output='+str(a.run_root/'slurm'/f'relaunch_{name}_%A_%a.out'),
               '--error='+str(a.run_root/'slurm'/f'relaunch_{name}_%A_%a.err')]
        if gpus: cmd.append(f'--gpus-per-node={gpus}')
        if array: cmd.append('--array='+array)
        if dependency:
            parts = dependency.split(':')
            cmd.append('--dependency='+':'.join([parts[0]]+[record['jobs'][x]['job_id'] for x in parts[1:]]))
        if name == 'preflight':
            cmd += [str(a.run_root/'code_relaunch_20260905/relaunch_preflight_v1.sh'), str(a.run_root)]
        else:
            cmd += [str(a.run_root/'code/job.sh'), name, str(a.run_root)]
        print(json.dumps(dict(stage=name,command=cmd)), flush=True)
        if a.dry_run:
            record['jobs'][name] = dict(job_id=f'<{name}>', command=cmd)
            continue
        result = subprocess.run(cmd, text=True, capture_output=True)
        if result.returncode:
            record.update(status='SUBMISSION_FAILED', failed_stage=name, error=result.stderr.strip())
            write(dest, record)
            raise RuntimeError(result.stderr.strip())
        job_id = result.stdout.strip().split(';')[0]
        if not job_id.isdigit(): raise ValueError('UNEXPECTED_SBATCH_OUTPUT')
        record['jobs'][name] = dict(job_id=job_id, command=cmd)
        write(dest, record)
        state = subprocess.run(['scontrol','show','job','-o',job_id], capture_output=True, text=True, check=True).stdout
        if 'Reason=JobHeldAdmin' in state:
            record.update(status='STOPPED_NEW_ADMIN_HOLD', failed_stage=name)
            write(dest, record)
            raise RuntimeError('New administrator hold; stop without alternate submission')
        print(f'SUBMITTED {name} {job_id}', flush=True)
    if not a.dry_run:
        record['status'] = 'SUBMITTED'
        write(dest, record)

if __name__ == '__main__':
    main()
