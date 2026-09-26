"""Operational retry only; frozen scientific runner, requests and scoring unchanged."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
from types import SimpleNamespace

CODE = Path(__file__).resolve().parent
OLD = CODE.parent / 'qwen36_38_20260920_v1'
spec = importlib.util.spec_from_file_location('frozen_q368', OLD / 'run.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
ROOT = old.ROOT
RETRY = ROOT / CODE.name.replace('qwen36_38_retry', 'retry')
EXCLUDE = 'nid0642,nid0653,nid0661,nid0674,nid0684,nid0685,nid0688,nid0694,nid0698'
ARRAYS = {'qwen36_27b_direct': '0-2,4-15', 'qwen38_27b_direct': '6-15'}
KEPT = {'qwen36_27b_direct': [3], 'qwen38_27b_direct': list(range(6))}
SCORES = ('full_score.json', 'full_score.md', 'full_scored.jsonl',
          'full_diagnostics.json', 'accuracy_report_cn.md', 'acceptance.json')

def plan():
    old.verify()
    preserved = {}
    for model, indices in KEPT.items():
        root = ROOT / model
        assert json.loads((root / 'smoke_acceptance.json').read_text())['status'] == 'PASS'
        for index in range(16):
            path = root / 'full' / f'predictions_{index:03d}.jsonl'
            if index in indices:
                manifest = json.loads(path.with_suffix('.manifest.json').read_text())
                assert path.is_file() and manifest['status'] == 'COMPLETE'
                preserved[str(path)] = manifest
            else:
                assert not path.exists(), f'Unexpected prediction; inspect before retry: {path}'
    return dict(run_id=old.RUN_ID, seed=old.SEED, arrays=ARRAYS, preserved=preserved,
                protocol_lock_sha256=old.sha(ROOT / 'protocol_lock.json'), exclude=EXCLUDE,
                code_hashes={str(p): old.sha(p) for p in (CODE / 'retry.py', CODE / 'score_job.sh')},
                original_jobs=['8301670', '8301673'], reason='nid0684 GPU_RECOVERY_REQUIRED',
                scientific_changes=False, score_policy='Existing deterministic label accuracy; no new auxiliary judge')

def command(model, stage, dependency=None):
    gpu = stage == 'full'
    name = 'sc_' + model[:6] + '_retry2_' + stage
    cmd = ['sbatch', '--parsable', '--account=YOUR_ACCOUNT', '--qos=allocated', '--nodes=1', '--ntasks=1',
           '--partition=' + ('gpu' if gpu else 'general'), '--cpus-per-task=' + ('8' if gpu else '4'),
           '--mem=' + ('128G' if gpu else '16G'), '--time=' + ('2-00:00:00' if gpu else '00:45:00'),
           '--job-name=' + name, '--chdir=' + str(CODE),
           '--output=' + str(RETRY / 'logs' / (name + '_%A_%a.out')),
           '--error=' + str(RETRY / 'logs' / (name + '_%A_%a.err'))]
    if gpu:
        cmd += ['--gpus-per-node=2', '--exclude=' + EXCLUDE, '--array=' + ARRAYS[model]]
    if dependency:
        cmd += ['--dependency=afterany:' + dependency]
    return cmd + ([str(OLD / 'job.sh'), 'full', '--model', model] if gpu else
                  [str(CODE / 'score_job.sh'), '--model', model, '--resume'])

def score(a):
    if not os.environ.get('SLURM_JOB_ID'):
        raise RuntimeError('SLURM_REQUIRED')
    frozen = json.loads((RETRY / 'RETRY_PLAN.json').read_text())
    assert old.sha(ROOT / 'protocol_lock.json') == frozen['protocol_lock_sha256']
    for path, digest in frozen['code_hashes'].items():
        assert old.sha(path) == digest, path
    old.verify()
    for path, manifest in frozen['preserved'].items():
        if Path(path).parents[1].name == a.model:
            assert old.sha(path) == manifest['output_sha256'], 'Preserved prediction changed: ' + path
    archive = RETRY / 'prior_scores' / a.model
    archive.mkdir(parents=True, exist_ok=True)
    marker = archive / 'ARCHIVED.json'
    if not marker.exists():
        hashes = {}
        for name in SCORES:
            src, dst = ROOT / a.model / name, archive / name
            if src.exists():
                if not dst.exists():
                    shutil.copy2(src, dst)
                assert old.sha(src) == old.sha(dst), 'Archive mismatch: ' + name
                hashes[name] = old.sha(dst)
        old.write(marker, hashes)
    old.score(SimpleNamespace(model=a.model))
    old.write(RETRY / (a.model + '_score_completed.json'), dict(
        job_id=os.environ['SLURM_JOB_ID'], preserved_predictions_verified=True,
        acceptance=json.loads((ROOT / a.model / 'acceptance.json').read_text()),
        output_hashes={name: old.sha(ROOT / a.model / name) for name in SCORES}))

def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('action', choices=['submit', 'score'])
    p.add_argument('--model', choices=list(ARRAYS))
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--resume', action='store_true')
    p.add_argument('--run-id', default=old.RUN_ID)
    p.add_argument('--seed', type=int, default=old.SEED)
    p.add_argument('--limit', type=int)
    a = p.parse_args()
    assert a.run_id == old.RUN_ID and a.seed == old.SEED and a.limit is None
    if a.action == 'score':
        assert a.model
        if not a.dry_run:
            score(a)
        return
    record = RETRY / 'SUBMISSIONS.json'
    saved = json.loads(record.read_text()) if record.exists() else {'jobs': {}}
    if record.exists() and not a.resume and not a.dry_run:
        raise FileExistsError(record)
    if not (RETRY / 'RETRY_PLAN.json').exists():
        frozen = plan()
        active = subprocess.check_output(['squeue', '-h', '-u', 'anonymous', '-o', '%j'], text=True)
        assert not any('qwen36' in n or 'qwen38' in n for n in active.splitlines()), 'Existing model job active'
        if not a.dry_run:
            (RETRY / 'logs').mkdir(parents=True, exist_ok=True)
            old.write(RETRY / 'RETRY_PLAN.json', frozen)
    if not a.dry_run:
        subprocess.run(['sinfo', '-p', 'gpu,general'], check=True)
    for model in ARRAYS:
        dependency = None
        for stage in ('full', 'score'):
            key = model + '_' + stage
            if key in saved['jobs']:
                dependency = saved['jobs'][key]['id']
                continue
            cmd = command(model, stage, dependency)
            print(shlex.join(cmd), flush=True)
            if a.dry_run:
                dependency = '${' + model + '_ARRAY_ID}'
                continue
            result = subprocess.run(cmd, check=True, text=True, capture_output=True)
            jid = result.stdout.strip().split(';')[0]
            assert jid.isdigit(), result.stdout
            saved['jobs'][key] = dict(id=jid, command=cmd, stderr=result.stderr)
            old.write(record, saved)
            dependency = jid
            print(json.dumps({'key': key, 'job_id': jid}), flush=True)

if __name__ == '__main__':
    main()
