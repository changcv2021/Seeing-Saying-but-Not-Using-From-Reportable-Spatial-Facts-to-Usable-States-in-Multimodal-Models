"""Audited idempotent submissions for already frozen batches; no cross-model barrier."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common_auto_v2 import load, save, entry, now


def main():
    p = argparse.ArgumentParser(); p.add_argument('--submit', action='store_true')
    p.add_argument('--mode', choices=['prepare', 'audit', 'batches'], required=True)
    args = p.parse_args(); c = load(HERE.parent / 'config_auto_v2.json'); root = Path(c['root'])
    # Slurm must be reachable, and the association and partitions must match the recorded request.
    assoc = subprocess.run(['sacctmgr', '-nP', 'show', 'assoc', 'user=anonymous', 'format=Account,QOS'], capture_output=True, text=True, check=True).stdout
    if 'YOUR_ACCOUNT|allocated' not in assoc: raise ValueError('LIVE_ACCOUNT_QOS_NOT_VERIFIED')
    site = subprocess.run(['sinfo', '-h', '-o', '%P %a %l %G'], capture_output=True, text=True, check=True).stdout
    if not all(any(line.startswith(part) and ' up ' in line for line in site.splitlines()) for part in ('general', 'gpu')):
        raise ValueError('LIVE_PARTITIONS_NOT_AVAILABLE')
    dest = root / 'scheduler/data_continuation_v1'; logs = root / 'logs/data_continuation_v1'
    if args.submit: logs.mkdir(parents=True, exist_ok=True)
    def submit(key, stage, extra=(), gpus=0, cpus=2, mem='16G', wall='00:30:00', array=None, dependency=None):
        record = dest / (key + '.json')
        if record.exists(): return load(record)['job_id']
        cmd = ['sbatch', '--parsable', '--account=YOUR_ACCOUNT', '--qos=allocated', '--partition=' + ('gpu' if gpus else 'general'),
               '--nodes=1', '--ntasks=1', '--cpus-per-task=' + str(cpus), '--mem=' + mem, '--time=' + wall,
               '--job-name=sws_dc_' + key, '--output=' + str(logs / (key + '_%A_%a.out')),
               '--error=' + str(logs / (key + '_%A_%a.err'))]
        if gpus: cmd += ['--gpus-per-node=' + str(gpus), '--exclude=' + ','.join(c['resources']['exclusions'])]
        if array: cmd += ['--array=' + array]
        if dependency: cmd += ['--dependency=' + dependency, '--kill-on-invalid-dep=yes']
        cmd += [str(HERE / 'job.sh'), stage, *extra]
        print(json.dumps(dict(key=key, command=cmd), ensure_ascii=False), flush=True)
        if not args.submit: return 'DRY_RUN_' + key
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode: raise RuntimeError(result.stderr)
        job = result.stdout.strip().split(';')[0]
        if not job.isdigit(): raise ValueError('UNPARSEABLE_SUBMISSION:' + result.stdout)
        save(record, dict(job_id=job, command=cmd, created_at=now(), status='SUBMITTED_NOT_COMPLETED',
            submitter=entry(__file__), live_site=site, live_assoc=assoc))
        return job
    if args.mode in ('prepare', 'audit'):
        submit(args.mode, args.mode, cpus=2, mem='16G', wall='01:00:00'); return
    reports = load(root / 'preparation/data_continuation_v1_20260910/BATCH_MANIFEST.json')
    for r in reports:
        batch = r['batch']; short = batch.split('_')[2]
        scorelock = submit(short + '_scorelock', 'freeze_score', ['--batch', batch], cpus=2, mem='8G')
        for model in c['models']:
            tag = model.split('_')[-1]; gp = 2 if tag == '27b' else 1
            proc = submit(short + '_' + tag + '_proc', 'processor', ['--batch', batch, '--model', model], cpus=4, mem='32G', wall='01:00:00')
            infer = submit(short + '_' + tag + '_infer', 'infer', ['--batch', batch, '--model', model],
                gpus=gp, cpus=4 * gp, mem='128G' if gp == 2 else '64G', wall='03:00:00' if gp == 2 else '02:00:00',
                array='0-' + str(len(r['shards']) - 1) + ('%2' if gp == 2 else '%4'), dependency='afterok:' + proc)
            submit(short + '_' + tag + '_score', 'rescore', ['--batch', batch, '--model', model], cpus=2, mem='8G',
                dependency='afterok:' + scorelock + ',afterany:' + infer)


if __name__ == '__main__': main()
