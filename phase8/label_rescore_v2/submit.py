"""Run a CPU-only, once-frozen uniform correction on all eleven raw-output sets."""
import os
import shlex
import subprocess
from config import *


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--run-id', default=RUN_ID)
    p.add_argument('--seed', type=int, default=SEED)
    p.add_argument('--limit', type=int)
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--resume', action='store_true')
    args = p.parse_args()
    if (args.run_id, args.seed, args.limit) != (RUN_ID, SEED, None):
        raise ValueError('PROTOCOL_MISMATCH')
    if (ROOT / 'SUBMITTED.json').exists() or (ROOT / 'SUBMISSION_PROGRESS.json').exists():
        raise FileExistsError('ALREADY_SUBMITTED')
    sinfo = subprocess.run(['sinfo', '-p', 'general', '-o', '%P %a %l %D %C %m'],
                           check=True, text=True, capture_output=True).stdout
    assoc = subprocess.run(['sacctmgr', '-nP', 'show', 'assoc', 'where', 'user=' + os.environ['USER'],
                            'format=Cluster,Account,Partition,QOS,DefaultQOS'],
                           check=True, text=True, capture_output=True).stdout
    if 'general' not in sinfo or '|YOUR_ACCOUNT|' not in assoc or 'allocated' not in assoc:
        raise ValueError('NO_CONFIRMED_RESOURCES')
    jobs = []
    if not args.dry_run:
        (ROOT / 'logs').mkdir(parents=True, exist_ok=True)

    def submit(stage, dependency=None):
        cmd = ['sbatch', '--parsable', '--partition=general', '--account=YOUR_ACCOUNT', '--qos=allocated',
               '--nodes=1', '--ntasks=1', '--cpus-per-task=2', '--mem=16G', '--time=00:45:00',
               '--job-name=sc_label_v2_' + stage,
               '--output=' + str(ROOT / 'logs/%x_%A_%a.out'), '--error=' + str(ROOT / 'logs/%x_%A_%a.err')]
        if stage == 'score':
            cmd += ['--array=0-10']
        if dependency:
            cmd += ['--dependency=' + dependency, '--kill-on-invalid-dep=yes']
        cmd += [str(CODE / 'job.sbatch'), stage]
        print(shlex.join(cmd), flush=True)
        if args.dry_run:
            job = str(9700000 + len(jobs))
        else:
            result = subprocess.run(cmd, check=True, text=True, capture_output=True)
            job = result.stdout.strip().split(';')[0]
            if not job.isdigit():
                raise ValueError('BAD_SUBMISSION_RESPONSE')
        jobs.append(dict(stage=stage, job_id=job, command=cmd))
        if not args.dry_run:
            write(ROOT / 'SUBMISSION_PROGRESS.json', jobs)
        return job

    prepared = submit('prepare')
    scored = submit('score', 'afterok:' + prepared)
    submit('summary', 'afterok:' + scored)
    if not args.dry_run:
        write(ROOT / 'SUBMITTED.json', dict(status='SUBMITTED_NOT_COMPLETE', run_id=RUN_ID,
            authorization='USER: 我觉得这10个模型的都存在这个问题，你都修改下',
            jobs=jobs, resources=dict(gpus=0, cpus=2, memory='16G', walltime='00:45:00'),
            live_sinfo=sinfo, live_assoc=assoc))


if __name__ == '__main__':
    main()
