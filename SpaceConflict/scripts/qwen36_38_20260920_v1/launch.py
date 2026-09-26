"""Explicit independent-model Slurm launch; no global concurrency throttle."""
import argparse
import json
import shlex
import subprocess
from run import CODE, ROOT, MODELS, RUN_ID, SEED, SHARDS, write

EXCLUDE = 'nid0642,nid0653,nid0661,nid0674,nid0685,nid0688,nid0694,nid0698'

def command(stage, model=None, dependency=None):
    gpu = stage in ('smoke', 'full')
    name = 'scq368_prepare' if model is None else f'sc_{model[:6]}_{stage}'
    cmd = ['sbatch', '--parsable', '--account=YOUR_ACCOUNT', '--qos=allocated', '--nodes=1', '--ntasks=1',
        '--partition='+('gpu' if gpu else 'debug'), '--cpus-per-task='+('8' if gpu else '4'),
        '--mem='+('128G' if gpu else '16G'),
        '--time='+('2-00:00:00' if stage == 'full' else '01:00:00' if stage == 'smoke' else '00:45:00'),
        '--job-name='+name, '--chdir='+str(CODE),
        '--output='+str(ROOT/'logs'/f'{name}_%A_%a.out'),
        '--error='+str(ROOT/'logs'/f'{name}_%A_%a.err')]
    if gpu:
        cmd += ['--gpus-per-node=2', '--exclude='+EXCLUDE]
    if stage == 'full':
        cmd += [f'--array=0-{SHARDS-1}']
    if dependency:
        cmd += ['--dependency='+dependency]
    cmd += [str(CODE/'job.sh'), stage]
    if model:
        cmd += ['--model', model]
    return cmd

def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--resume', action='store_true')
    p.add_argument('--run-id', default=RUN_ID)
    p.add_argument('--seed', type=int, default=SEED)
    p.add_argument('--limit', type=int)
    a = p.parse_args()
    assert a.run_id == RUN_ID and a.seed == SEED and a.limit is None
    record = ROOT/'SUBMISSIONS.json'
    saved = json.loads(record.read_text()) if record.exists() else {'run_id': RUN_ID, 'jobs': {}}
    if record.exists() and not a.resume and not a.dry_run:
        raise FileExistsError(record)
    if not a.dry_run:
        # Fail before any submission if scheduler/config cannot be queried.
        subprocess.run(['sinfo', '-p', 'gpu,debug'], check=True)
        subprocess.run(['sacctmgr', '-nP', 'show', 'assoc', 'where', 'user=anonymous',
                        'format=Account,Partition,QOS,DefaultQOS'], check=True)
        (ROOT/'logs').mkdir(parents=True, exist_ok=True)
    def submit(key, stage, model=None, dependency=None):
        if key in saved['jobs']:
            return saved['jobs'][key]['id']
        cmd = command(stage, model, dependency)
        print(shlex.join(cmd), flush=True)
        if a.dry_run:
            return '${'+key.upper()+'_ID}'
        result = subprocess.run(cmd, check=True, text=True, capture_output=True)
        jid = result.stdout.strip().split(';')[0]
        assert jid.isdigit(), result.stdout
        saved['jobs'][key] = {'id': jid, 'command': cmd, 'stderr': result.stderr}
        write(record, saved)
        print(json.dumps({'key': key, 'job_id': jid}), flush=True)
        return jid
    prep = submit('prepare', 'prepare')
    for model in MODELS:
        smoke = submit(model+'_smoke', 'smoke', model, 'afterok:'+prep)
        full = submit(model+'_full', 'full', model, 'afterok:'+smoke)
        # afterany deliberately produces a truthful partial report on failed arrays.
        submit(model+'_score', 'score', model, 'afterany:'+full)

if __name__ == '__main__':
    main()
