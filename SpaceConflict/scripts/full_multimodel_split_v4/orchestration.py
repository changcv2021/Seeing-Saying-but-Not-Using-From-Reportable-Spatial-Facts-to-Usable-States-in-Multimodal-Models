"""Scheduling-only extension: independent shards; frozen science stays read-only."""
import argparse, ast, datetime, fcntl, json, math, os, re, shutil, subprocess, sys
from pathlib import Path
EXTENSION = Path(__file__).resolve().parent
ORIGINAL = EXTENSION.parent / 'full_multimodel_20260908_v1'
REPORTING = EXTENSION.parent / 'full_multimodel_reporting_v1'
sys.path.insert(0, str(ORIGINAL))
from campaign import ROOT, RUN_ID, SEED, registry, verify, frozen, write, sha, load
LOCK = ROOT / 'split_scheduling_v4_lock.json'

def verify_extension():
    verify()
    lock = json.loads(LOCK.read_text())
    if lock['scientific_protocol_sha256'] != sha(ROOT/'protocol_lock.json'):
        raise ValueError('SCIENTIFIC_PROTOCOL_CHANGED')
    for name, digest in lock['files'].items():
        if sha(name) != digest: raise ValueError('SCHEDULING_EXTENSION_CHANGED:'+name)

def read_cluster_limits():
    partition=subprocess.run(['scontrol','show','partition','gpu','-o'],check=True,capture_output=True,text=True,timeout=30).stdout
    configuration=subprocess.run(['scontrol','show','config'],check=True,capture_output=True,text=True,timeout=30).stdout
    raw=re.search(r'\bMaxTime=([^ ]+)',partition).group(1)
    days,clock=(raw.split('-',1) if '-' in raw else ('0',raw))
    h,m,s=map(int,clock.split(':'))
    seconds=int(days)*86400+h*3600+m*60+s
    array_size=int(re.search(r'MaxArraySize\s*=\s*(\d+)',configuration).group(1))
    if seconds<3600 or array_size<1:raise ValueError('UNSUPPORTED_LIVE_CLUSTER_CONFIGURATION')
    return dict(gpu_wall_hours=seconds//3600,max_array_tasks=array_size,source='LIVE_SLURM_CONFIGURATION')

def budget_for(model, candidate_mean, judge_smoke_seconds, n=24196, limits=None):
    if n != 24196 or not math.isfinite(candidate_mean) or candidate_mean<=0 or (judge_smoke_seconds is not None and (not math.isfinite(judge_smoke_seconds) or judge_smoke_seconds<=0)):
        raise ValueError('INVALID_MEASURED_BUDGET')
    limits=limits or dict(gpu_wall_hours=48,max_array_tasks=1000,source='TEST_FIXTURE_VERIFIED_SITE_DEFAULT')
    wall=limits['gpu_wall_hours']; max_count=min(n,limits['max_array_tasks'])
    def phase(seconds, minimum):
        # Only site limits constrain each allocation. Slow estimates never reject a run.
        desired=max(minimum,math.ceil(seconds*n*1.75/max(1,wall*3600-1800)))
        count=min(desired,max_count)
        estimate=(seconds*n/count*1.75+1800)/3600
        return dict(shards=count,wall_hours=wall,estimated_hours=estimate,
                    timed_continuation_supported=True,estimated_continuation_needed=estimate>wall)
    candidate = phase(candidate_mean, model['replicas'])
    judge = (phase(judge_smoke_seconds/96, 4) if judge_smoke_seconds is not None else
             dict(shards=min(4,max_count),wall_hours=wall,estimated_hours=None,
                  timed_continuation_supported=True,estimated_continuation_needed=None,
                  basis='FIXED_FOUR_SHARDS_NO_JUDGE_TIMING_YET'))
    candidate.update(gpus=model['gpus'], cpus=4*model['gpus'],
                     memory_gib=64*model['gpus'], concurrency=model['replicas'])
    judge.update(gpus=1, cpus=4, memory_gib=32, concurrency=4)
    gpu_hours = candidate['shards']*candidate['wall_hours']*candidate['gpus'] + judge['shards']*judge['wall_hours']
    return dict(candidate=candidate, judge=judge, maximum_reserved_gpu_hours=gpu_hours,
                candidate_mean_seconds=candidate_mean, judge_smoke_seconds=judge_smoke_seconds,
                input_count=n, partition='gpu', account='YOUR_ACCOUNT', qos='allocated',
                shard_rule='request_index modulo num_shards', independent_nodes=True,
                max_concurrent_gpus_per_model=4, answer_based_retries=0,
                cumulative_gpu_hour_cap=None,artificial_shard_cap=None,cluster_limits=limits,
                time_limit_continuation='Only unfinished requests; completed outputs immutable.')

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

def require_stage_gate(stage):
    if stage.split('_',1)[0] in ('judge','finish'):
        require_gate()


def submit(key, stage, command):
    require_stage_gate(stage)
    subprocess.run(['sinfo','-p','gpu','-h'],check=True,capture_output=True,timeout=30)
    directory=ROOT/key/'split_jobs_v4'; directory.mkdir(exist_ok=True)
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

def array_command(key, stage, plan, indices=None):
    p=plan['candidate' if stage=='candidate' else 'judge']
    members=f"0-{p['shards']-1}" if indices is None else ','.join(map(str,indices))
    return ['sbatch','--parsable','--job-name=scfs_'+key+'_'+stage,'--partition=gpu',
            '--account=YOUR_ACCOUNT','--qos=allocated','--nodes=1','--ntasks=1',
            '--gpus-per-node='+str(p['gpus']),'--cpus-per-task='+str(p['cpus']),
            '--mem='+str(p['memory_gib'])+'G','--time='+f"{p['wall_hours']:02d}:00:00",
            '--array='+f"{members}%{p['concurrency']}",'--exclude=nid0642,nid0653,nid0661,nid0674,nid0685,nid0688,nid0694,nid0698','--no-requeue','--signal=B:USR1@600',
            '--output='+str(ROOT/'logs'/('split_v4_'+key+'_'+stage+'_%A_%a.out')),
            '--error='+str(ROOT/'logs'/('split_v4_'+key+'_'+stage+'_%A_%a.err')),
            str(EXTENSION/'job.sh'),stage,key]

def cpu_command(key, stage, after):
    return ['sbatch','--parsable','--job-name=scfs_'+key+'_'+stage,'--partition=general',
            '--account=YOUR_ACCOUNT','--qos=allocated','--nodes=1','--ntasks=1','--cpus-per-task=2',
            '--mem=8G','--time=00:30:00','--no-requeue','--dependency=afterany:'+after,
            '--output='+str(ROOT/'logs'/('split_v4_'+key+'_'+stage+'_%j.out')),
            '--error='+str(ROOT/'logs'/('split_v4_'+key+'_'+stage+'_%j.err')),
            str(EXTENSION/'job.sh'),stage,key]

def renew_controller():
    """A CPU allocation's walltime is not an experiment-duration deadline."""
    current=os.environ['SLURM_JOB_ID'];record=ROOT/'controller_continuations_v4'/(current+'.json')
    if record.exists():return json.loads(record.read_text())
    command=['sbatch','--parsable','--job-name=scfm_split_v4_controller','--partition=general',
             '--account=YOUR_ACCOUNT','--qos=allocated','--nodes=1','--ntasks=1','--cpus-per-task=1',
             '--mem=4G','--time=24:00:00','--no-requeue','--dependency=afterany:'+current,
             '--output='+str(ROOT/'logs/split_v4_controller_%j.out'),
             '--error='+str(ROOT/'logs/split_v4_controller_%j.err'),str(EXTENSION/'job.sh'),'controller']
    subprocess.run(['sinfo','-p','general','-h'],check=True,capture_output=True,timeout=30)
    result=subprocess.run(command,check=True,capture_output=True,text=True,timeout=45)
    job=result.stdout.strip().split(';')[0]
    if not job.isdigit():raise ValueError('AMBIGUOUS_CONTROLLER_SUBMISSION')
    record.parent.mkdir(exist_ok=True)
    data=dict(previous_job=current,next_job=job,command=command,experiment_complete=False,
              reason='CONTINUE_MONITORING_WITHOUT_CUMULATIVE_DEADLINE')
    frozen(record,data);return data

def dispatch(key, candidate_mean=None, judge_smoke_seconds=None):
    verify_extension()
    ready=json.loads((ROOT/key/'inference_readiness_v4.json').read_text())
    if ready['status'] not in ('PASS_ENGINEERING_ONLY','WAIVED_BY_USER_NOT_TESTED'):
        raise ValueError('INFERENCE_NOT_READY')
    if ready['status']=='WAIVED_BY_USER_NOT_TESTED':
        if key!='qwen25vl_32b':raise ValueError('WAIVER_ONLY_FOR_EXPLICITLY_AUTHORIZED_32B')
        plan=json.loads((ROOT/key/'full_split_budget.json').read_text())
        # Never overlap with the superseded pending v2 candidate array.
        old=subprocess.run(['sacct','-n','-X','-j','8174908,8174909,8174644','-P','--format=JobID,State'],
                           check=True,capture_output=True,text=True,timeout=30).stdout
        lines=[line.split('|') for line in old.splitlines() if '|' in line]
        if not lines or any(not line[1].startswith('CANCELLED') for line in lines):
            raise ValueError('OLD_V2_JOBS_NOT_CANCELLED')
    else:
        plan=budget_for(registry()[key],candidate_mean,judge_smoke_seconds,limits=read_cluster_limits())
        frozen(ROOT/key/'full_split_budget.json',plan)
    candidate=submit(key,'candidate',array_command(key,'candidate',plan))
    write(ROOT/key/'split_jobs_v4/candidate_latest.json',dict(**candidate,round=0,indices=list(range(plan['candidate']['shards']))))
    handoff=submit(key,'handoff',cpu_command(key,'handoff',candidate['job_id']))
    return dict(candidate_array=candidate['job_id'],handoff=handoff['job_id'],budget=plan,
                cross_model_dependencies=[],shared_gate='JUDGE_ONLY: SCORING_GATE.json',
                layout='INDEPENDENT_SHARDS_V4_INFERENCE_SCORING_DECOUPLED',
                readiness=ready['status'],experiment_complete=False)


def time_resume_allowed(state,supervisor,current_array):
    if state=='TIMEOUT':return True
    return state=='COMPLETED' and supervisor.get('status')=='CHECKPOINTED' and supervisor.get('array_job_id')==current_array

def preserve_complete_prefix(path,expected,attempt):
    """On timeout only: preserve all raw bytes and retain complete committed JSON rows."""
    if not path.exists():return 0
    raw=path.read_bytes(); lines=raw.splitlines(keepends=True); valid=[]; broken=False
    for i,line in enumerate(lines):
        try:row=json.loads(line)
        except (ValueError,UnicodeDecodeError):
            if i!=len(lines)-1:raise ValueError('CORRUPTION_INSIDE_COMMITTED_PREFIX')
            broken=True;break
        if len(valid)>=len(expected) or row.get('sample_id')!=expected[len(valid)]:
            raise ValueError('TIMEOUT_PREFIX_NOT_EXACT_SHARD_PREFIX')
        if row.get('error'):raise ValueError('RUNTIME_ERROR_IS_NOT_TIME_BASED_RETRY')
        valid.append(line)
    needs_newline=bool(valid and not valid[-1].endswith(b'\n'))
    if broken or needs_newline:
        archive=path.parent/'timeout_archives'/attempt/path.name
        archive.parent.mkdir(parents=True,exist_ok=True)
        if archive.exists():
            if archive.read_bytes()!=raw:raise ValueError('PRESERVE_EXISTING_TIMEOUT_ARCHIVE')
        else:shutil.copy2(path,archive)
        content=b''.join(valid)
        if content and not content.endswith(b'\n'):content+=b'\n'
        temporary=path.with_suffix('.checkpoint.part')
        temporary.write_bytes(content);os.replace(temporary,path)
        frozen(archive.with_suffix('.recovery.json'),dict(original_sha256=sha(archive),
               resumed_prefix_sha256=sha(path),committed_rows=len(valid),all_original_bytes_preserved=True))
    return len(valid)

def continue_time_limited_shards(key,stage):
    plan=json.loads((ROOT/key/'full_split_budget.json').read_text());count=plan[stage]['shards']
    directory=ROOT/key/('full' if stage=='candidate' else 'full_judge')
    prefix='predictions_' if stage=='candidate' else 'judgments_'
    missing=[i for i in range(count) if not (directory/(prefix+f'{i:03d}.manifest.json')).exists()]
    if not missing:return False
    latest=json.loads((ROOT/key/'split_jobs_v4'/(stage+'_latest.json')).read_text())
    query=subprocess.run(['sacct','-n','-P','-X','-j',','.join(sorted(set(latest.get('index_jobs',{}).values()) or {latest['job_id']})),'--format=JobID,State'],
                         check=True,capture_output=True,text=True,timeout=30)
    states={}
    for line in query.stdout.splitlines():
        fields=line.split('|')
        if len(fields)>1 and '_' in fields[0]:
            suffix=fields[0].rsplit('_',1)[1]
            if suffix.isdigit():states[(fields[0].rsplit('_',1)[0],int(suffix))]=fields[1].split()[0]
    requests=load(ROOT/'requests.jsonl')
    for index in missing:
        supervisor_path=directory/f'supervisor_shard_{index:03d}.json'
        supervisor=json.loads(supervisor_path.read_text()) if supervisor_path.exists() else {}
        supplier=latest.get('index_jobs',{}).get(str(index),latest['job_id'])
        state=states.get((supplier,index))
        if index not in latest['indices'] or not time_resume_allowed(state,supervisor,supplier):
            raise ValueError('UNFINISHED_NON_TIME_FAILURE_PRESERVED:'+str(index)+':'+str(state))
        expected=[r['sample_id'] for r in requests[index::count]]
        preserve_complete_prefix(directory/(prefix+f'{index:03d}.jsonl'),expected,latest['job_id'])
    number=latest['round']+1
    # Refresh the site's per-allocation cap, not a cumulative experiment budget.
    limits=read_cluster_limits();newplan=json.loads(json.dumps(plan))
    newplan[stage]['wall_hours']=limits['gpu_wall_hours']
    continuation=submit(key,stage+f'_continue_{number:04d}',array_command(key,stage,newplan,missing))
    write(ROOT/key/'split_jobs_v4'/(stage+'_latest.json'),dict(**continuation,round=number,indices=missing))
    following='handoff' if stage=='candidate' else 'finish'
    submit(key,following+f'_continue_{number:04d}',cpu_command(key,following,continuation['job_id']))
    frozen(ROOT/key/'split_jobs_v4'/(stage+f'_continuation_{number:04d}.json'),
           dict(previous_array=latest['job_id'],new_array=continuation['job_id'],indices=missing,
                reason='SLURM_TIME_LIMIT_OR_SAFE_ROW_BOUNDARY_CHECKPOINT',completed_responses_not_regenerated=True))
    return True

def maybe_submit_judge(key):
    root=ROOT/key
    # Lock only this model's short dispatch transaction, never GPU computation.
    with (root/'judge_dispatch_v4.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        done=root/'full_judge_submission_v4.json'
        if done.exists():return dict(status='JUDGE_SUBMITTED',**json.loads(done.read_text()))
        if not (root/'full_candidate_acceptance.json').exists():
            return dict(status='WAITING_FOR_OWN_PREDICTIONS')
        gatepath=ROOT/'SCORING_GATE.json'
        gate=json.loads(gatepath.read_text()) if gatepath.exists() else {}
        if gate.get('status')!='PASS':
            state=('SCORING_BLOCKED_CANDIDATE_UNAFFECTED' if gate.get('status','').startswith('BLOCKED')
                   else 'WAITING_FOR_SCORER_ONLY_CANDIDATE_UNAFFECTED')
            result=dict(status=state,gate=gate.get('status','NOT_COMPLETED'))
            write(root/'judge_wait_v4.json',result)
            return result
        require_gate()
        accepted=json.loads((root/'full_candidate_acceptance.json').read_text())
        if accepted['status']!='COMPLETE' or accepted['n']!=24196:
            raise ValueError('OWN_PREDICTIONS_NOT_COMPLETE')
        plan=json.loads((root/'full_split_budget.json').read_text())
        judged=submit(key,'judge',array_command(key,'judge',plan))
        write(root/'split_jobs_v4/judge_latest.json',dict(**judged,round=0,indices=list(range(plan['judge']['shards']))))
        final=submit(key,'finish',cpu_command(key,'finish',judged['job_id']))
        record=dict(judge_array=judged['job_id'],final=final['job_id'])
        frozen(done,record)
        return dict(status='JUDGE_SUBMITTED',**record)

def handoff(key):
    verify_extension()
    if continue_time_limited_shards(key,'candidate'):return
    result=validate_stage(key,'candidate')
    frozen(ROOT/key/'full_candidate_acceptance.json',result)
    # A scorer that is not ready never prevents candidate output acceptance.
    print(json.dumps(maybe_submit_judge(key)),flush=True)


def finish(key):
    verify_extension(); require_gate()
    validate_stage(key,'candidate')
    if continue_time_limited_shards(key,'judge'):return
    result=validate_stage(key,'judge')
    frozen(ROOT/key/'full_judge_acceptance.json',result)
    subprocess.run([sys.executable,str(ORIGINAL/'campaign.py'),'final','--model',key],check=True)
    subprocess.run([sys.executable,str(REPORTING/'report.py'),'--model',key],check=True)
    # Only a short CPU report write is serialized, never GPU inference or judge.
    with (ROOT/'comparison_write.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        subprocess.run([sys.executable,str(ORIGINAL/'summary.py')],check=True)
    frozen(ROOT/key/'split_completion_v4.json',dict(status='COMPLETE',n=24196,scientific_protocol_unchanged=True))

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
