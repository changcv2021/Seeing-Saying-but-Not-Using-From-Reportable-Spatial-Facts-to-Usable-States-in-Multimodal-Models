"""Scheduling-only extension: independent shards; frozen science stays read-only."""
import argparse, ast, datetime, fcntl, json, math, os, subprocess, sys
from pathlib import Path
EXTENSION = Path(__file__).resolve().parent
ORIGINAL = EXTENSION.parent / 'full_multimodel_20260908_v1'
REPORTING = EXTENSION.parent / 'full_multimodel_reporting_v1'
sys.path.insert(0, str(ORIGINAL))
from campaign import ROOT, RUN_ID, SEED, registry, verify, frozen, write, sha, load
LOCK = ROOT / 'split_scheduling_lock.json'

def verify_extension():
    verify()
    lock = json.loads(LOCK.read_text())
    if lock['scientific_protocol_sha256'] != sha(ROOT/'protocol_lock.json'):
        raise ValueError('SCIENTIFIC_PROTOCOL_CHANGED')
    for name, digest in lock['files'].items():
        if sha(name) != digest: raise ValueError('SCHEDULING_EXTENSION_CHANGED:'+name)

def budget_for(model, candidate_mean, judge_smoke_seconds, n=24196):
    if n != 24196 or candidate_mean <= 0 or judge_smoke_seconds <= 0:
        raise ValueError('INVALID_MEASURED_BUDGET')
    def phase(seconds, minimum):
        count = minimum
        while True:
            # 75% inference margin plus 30 minutes per shard for load/verification.
            hours = max(1, math.ceil((seconds*n/count*1.75+1800)/3600))
            if hours <= 6: return dict(shards=count, wall_hours=hours)
            if count >= 64: raise ValueError('SINGLE_SHARD_ESTIMATE_TOO_LONG')
            count *= 2
    candidate = phase(candidate_mean, model['replicas'])
    judge = phase(judge_smoke_seconds/96, 4)
    candidate.update(gpus=model['gpus'], cpus=4*model['gpus'],
                     memory_gib=64*model['gpus'], concurrency=model['replicas'])
    judge.update(gpus=1, cpus=4, memory_gib=32, concurrency=4)
    gpu_hours = candidate['shards']*candidate['wall_hours']*candidate['gpus'] + judge['shards']*judge['wall_hours']
    if gpu_hours > 192: raise ValueError('TOTAL_GPU_BUDGET_EXCEEDS_PREVIOUS_4GPU_48H_CAP')
    return dict(candidate=candidate, judge=judge, maximum_reserved_gpu_hours=gpu_hours,
                candidate_mean_seconds=candidate_mean, judge_smoke_seconds=judge_smoke_seconds,
                input_count=n, partition='gpu', account='YOUR_ACCOUNT', qos='allocated',
                shard_rule='request_index modulo num_shards', independent_nodes=True,
                max_concurrent_gpus_per_model=4, automatic_candidate_retries=0)

def require_gate():
    if json.loads((ROOT/'SCORING_GATE.json').read_text()).get('status') != 'PASS':
        raise ValueError('COMMON_7B_SCORING_GATE_REQUIRED')

def validate_rows(requests, parts, key='sample_id'):
    expected = [r[key] for r in requests]
    if len(set(expected)) != len(expected): raise ValueError('DUPLICATE_REQUEST')
    seen = set()
    for index, rows in enumerate(parts):
        if [r[key] for r in rows] != expected[index::len(parts)]:
            raise ValueError('SHARD_MEMBERSHIP_OR_COMPLETENESS_MISMATCH')
        for row in rows:
            if row[key] in seen: raise ValueError('DUPLICATE_OUTPUT')
            if row.get('error'): raise ValueError('PRESERVED_RUNTIME_ERROR')
            seen.add(row[key])
    if seen != set(expected): raise ValueError('INCOMPLETE_OUTPUT')
    return len(seen)

def validate_stage(key, stage):
    cfg = registry()[key]; root = ROOT/key
    plan = json.loads((root/'full_split_budget.json').read_text())
    count = plan['candidate' if stage == 'candidate' else 'judge']['shards']
    directory = root/('full' if stage == 'candidate' else 'full_judge')
    prefix = 'predictions_' if stage == 'candidate' else 'judgments_'
    files = [directory/(prefix+f'{i:03d}.jsonl') for i in range(count)]
    if set(directory.glob(prefix+'*.jsonl')) != set(files):
        raise ValueError('MISSING_OR_UNEXPECTED_OUTPUT_FILES')
    parts = []
    for path in files:
        manifest = json.loads(path.with_suffix('.manifest.json').read_text())
        if manifest.get('status') not in ('COMPLETE','PASS') or manifest['output_sha256'] != sha(path):
            raise ValueError('UNFINISHED_OR_CHANGED_OUTPUT')
        rows = load(path)
        if manifest['count'] != len(rows): raise ValueError('MANIFEST_COUNT_MISMATCH')
        parts.append(rows)
    n = validate_rows(load(ROOT/'requests.jsonl'), parts)
    if n != 24196: raise ValueError('WRONG_FULL_DENOMINATOR')
    if stage == 'candidate':
        for rows in parts:
            for row in rows:
                if (row['model_id'],row['model_revision'],row['run_id'],row['config_sha256'],
                    row['requested_samples_sha256']) != (cfg['model_id'],cfg['revision'],cfg['run_id'],
                    sha(root/'config.json'),cfg['input_hashes']['requests.jsonl']):
                    raise ValueError('CANDIDATE_PROVENANCE_MISMATCH')
                if row.get('gold_access_attempts',0) or row.get('generated_tokens',0)>512 or row.get('max_new_tokens')!=512:
                    raise ValueError('GOLD_OR_TOKEN_PROTOCOL_VIOLATION')
    return dict(status='COMPLETE', n=n, shards=count, files={str(p):sha(p) for p in files})

def submit(key, stage, command):
    require_gate()
    subprocess.run(['sinfo','-p','gpu','-h'],check=True,capture_output=True,timeout=30)
    directory=ROOT/key/'split_jobs'; directory.mkdir(exist_ok=True)
    result_path=directory/(stage+'.json'); intent=directory/(stage+'_intent.json')
    if result_path.exists(): return json.loads(result_path.read_text())
    if intent.exists(): raise ValueError('EXISTING_SUBMISSION_INTENT_REQUIRES_RECONCILIATION')
    frozen(intent,dict(command=command,submitted_by_job=os.environ['SLURM_JOB_ID'],
                       created_at=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    result=subprocess.run(command,capture_output=True,text=True,timeout=45)
    if result.returncode:
        frozen(directory/(stage+'_submit_error.json'),dict(returncode=result.returncode,stderr=result.stderr))
        raise RuntimeError('SBATCH_FAILED_NO_BLIND_RETRY:'+result.stderr)
    jid=result.stdout.strip().split(';')[0]
    if not jid.isdigit(): raise ValueError('AMBIGUOUS_SBATCH_RESPONSE')
    record=dict(job_id=jid,command=command)
    frozen(result_path,record)
    return record

def array_command(key, stage, plan):
    p=plan['candidate' if stage=='candidate' else 'judge']
    return ['sbatch','--parsable','--job-name=scfs_'+key+'_'+stage,'--partition=gpu',
            '--account=YOUR_ACCOUNT','--qos=allocated','--nodes=1','--ntasks=1',
            '--gpus-per-node='+str(p['gpus']),'--cpus-per-task='+str(p['cpus']),
            '--mem='+str(p['memory_gib'])+'G','--time='+f"{p['wall_hours']:02d}:00:00",
            '--array='+f"0-{p['shards']-1}%{p['concurrency']}",'--exclude=nid0688','--no-requeue',
            '--output='+str(ROOT/'logs'/('split_'+key+'_'+stage+'_%A_%a.out')),
            '--error='+str(ROOT/'logs'/('split_'+key+'_'+stage+'_%A_%a.err')),
            str(EXTENSION/'job.sh'),stage,key]

def cpu_command(key, stage, after):
    return ['sbatch','--parsable','--job-name=scfs_'+key+'_'+stage,'--partition=general',
            '--account=YOUR_ACCOUNT','--qos=allocated','--nodes=1','--ntasks=1','--cpus-per-task=2',
            '--mem=8G','--time=00:30:00','--no-requeue','--dependency=afterany:'+after,
            '--output='+str(ROOT/'logs'/('split_'+key+'_'+stage+'_%j.out')),
            '--error='+str(ROOT/'logs'/('split_'+key+'_'+stage+'_%j.err')),
            str(EXTENSION/'job.sh'),stage,key]

def dispatch(key, candidate_mean, judge_smoke_seconds):
    verify_extension(); require_gate()
    if json.loads((ROOT/key/'interface_gate.json').read_text())['status'] != 'PASS':
        raise ValueError('MODEL_ENGINEERING_GATE_REQUIRED')
    plan=budget_for(registry()[key],candidate_mean,judge_smoke_seconds)
    frozen(ROOT/key/'full_split_budget.json',plan)
    candidate=submit(key,'candidate',array_command(key,'candidate',plan))
    handoff=submit(key,'handoff',cpu_command(key,'handoff',candidate['job_id']))
    return dict(candidate_array=candidate['job_id'],handoff=handoff['job_id'],budget=plan,
                cross_model_dependencies=[],shared_gate='SCORING_GATE.json',layout='INDEPENDENT_SHARDS_V1')

def handoff(key):
    verify_extension(); require_gate()
    result=validate_stage(key,'candidate')
    frozen(ROOT/key/'full_candidate_acceptance.json',result)
    plan=json.loads((ROOT/key/'full_split_budget.json').read_text())
    judged=submit(key,'judge',array_command(key,'judge',plan))
    final=submit(key,'finish',cpu_command(key,'finish',judged['job_id']))
    frozen(ROOT/key/'full_judge_submission.json',dict(judge_array=judged['job_id'],final=final['job_id']))

def finish(key):
    verify_extension(); require_gate()
    validate_stage(key,'candidate')
    result=validate_stage(key,'judge')
    frozen(ROOT/key/'full_judge_acceptance.json',result)
    subprocess.run([sys.executable,str(ORIGINAL/'campaign.py'),'final','--model',key],check=True)
    subprocess.run([sys.executable,str(REPORTING/'report.py'),'--model',key],check=True)
    # Only a short CPU report write is serialized, never GPU inference or judge.
    with (ROOT/'comparison_write.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        subprocess.run([sys.executable,str(ORIGINAL/'summary.py')],check=True)
    frozen(ROOT/key/'split_completion.json',dict(status='COMPLETE',n=24196,scientific_protocol_unchanged=True))

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('action',choices=['handoff','finish'])
    p.add_argument('--model',required=True);p.add_argument('--run-id',default=RUN_ID)
    p.add_argument('--seed',type=int,default=SEED);p.add_argument('--limit',type=int)
    p.add_argument('--dry-run',action='store_true');p.add_argument('--resume',action='store_true')
    a=p.parse_args()
    if a.run_id!=RUN_ID or a.seed!=SEED or a.limit is not None:raise ValueError('PROTOCOL_MISMATCH')
    if a.dry_run: print('Validate complete frozen outputs before next stage.');return
    if not os.environ.get('SLURM_JOB_ID'):raise ValueError('SLURM_REQUIRED')
    try: globals()[a.action](a.model)
    except BaseException as exc:
        write(ROOT/a.model/('split_'+a.action+'_failure_'+os.environ['SLURM_JOB_ID']+'.json'),
              dict(status='BLOCKED_OUTPUTS_PRESERVED',error=type(exc).__name__+': '+str(exc)))
        raise

if __name__=='__main__':main()
