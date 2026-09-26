"""Independent historical preservation, model inventory and empirical cost audit."""
from collections import Counter,defaultdict
import math
import subprocess
from common import *

def quantile(xs,q):
    xs=sorted(xs); return xs[min(len(xs)-1,math.ceil(q*len(xs))-1)] if xs else None

def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run: print('CPU old-result checks, no new-model inference or sample selection'); return
    b0=Path(c['b0']); package=Path(c['package']); protected={}
    for r in rows(b0/'manifest/history_before.jsonl'): protected[r['path']]=r
    for path in b0.rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts: protected.setdefault(str(path),entry(path))
    failures=[]
    for n,r in enumerate(protected.values(),1):
        p=Path(r['path'])
        if not p.is_file(): failures.append(dict(path=str(p),reason='MISSING')); continue
        actual=entry(p)
        if actual['bytes']!=r['bytes'] or actual['sha256']!=r['sha256'].removeprefix('sha256:'): failures.append(dict(expected=r,actual=actual))
        if n%2000==0: print(json.dumps(dict(history_checked=n,total=len(protected))),flush=True)
    save(root/'manifest/history_before.jsonl',list(protected.values()),'jsonl')
    model_inventory=load(b0/'manifest/model_inventory.json'); model_checks=[]
    for m in model_inventory:
        checks=[]
        for key in ('manifest','index','config'):
            actual=entry(m[key]['path']); checks.append(dict(kind=key,actual=actual,match=actual['sha256']==m[key]['sha256']))
        shard_checks=[dict(path=s['path'],expected_bytes=s['bytes'],exists=Path(s['path']).is_file(),bytes_match=Path(s['path']).is_file() and Path(s['path']).stat().st_size==s['bytes']) for s in m['shard_sizes']]
        model_checks.append(dict(**m,checks=checks,shard_checks=shard_checks))
    save(root/'manifest/model_inventory.json',model_checks)
    raw_counts=Counter(); raw_worlds=defaultdict(set); timing=defaultdict(list); memory=defaultdict(list); index=[]; row_ids=set()
    source=b0/'03_B0_RAW_RESPONSES_WITH_PROMPTS.csv'
    with source.open(newline='') as f:
        for r in csv.DictReader(f):
            key=(r['model'],r['request_id'])
            if key in row_ids: raise ValueError('B0_DUPLICATE_RAW_KEY:'+str(key))
            row_ids.add(key); raw_counts[r['model']]+=1; raw_worlds[r['model']].add(r['underlying_world_id'])
            raw=json.loads(r['raw_record']); seconds=raw.get('generation_seconds')
            if isinstance(seconds,(int,float)): timing[r['model']].append(seconds)
            if raw.get('peak_memory_bytes'): memory[r['model']].append(raw['peak_memory_bytes'])
            index.append(dict(model_id=r['model'],model_revision=raw.get('model_revision'),request_id=r['request_id'],
                world_cluster_id=r['underlying_world_id'],cohort=r['cohort'],level=r['level'],
                raw_path=r['raw_path'],raw_sha256=sha(r['raw_path']),prompt_sha256=hashlib.sha256(r['actual_rendered_prompt'].encode()).hexdigest(),
                source_table=str(source),source_raw_preserved=True,
                human_status='REUSE_PRIOR_TASK_REVIEW_ONLY' if r['cohort']=='B0_A' else 'NO_HUMAN_REVIEW_B0_B',
                eligible_as_new_SWS_response=False))
    save(root/'manifest/legacy_raw_response_index.jsonl',index,'jsonl')
    estimates=[]
    smoke=load(b0/'reports/resource_measurement.json')
    for m in c['models']:
        mm=next(x for x in smoke['models'] if x['model']==m); gpu=2 if m.endswith('27b') else 1
        estimates.append(dict(model=m,gpus_per_worker=gpu,observed_B0_responses=raw_counts[m],worlds=len(raw_worlds[m]),
             smoke_media_seconds=mm['measured_cost_by_media']['True'],
             actual_B0_generation_seconds_median=quantile(timing[m],0.5),actual_B0_generation_seconds_p90=quantile(timing[m],0.9),
             behavior_max_requests=29928,naive_smoke_extrapolation_gpu_hours=29928*gpu*mm['measured_cost_by_media']['True']/3600,
             observed_max_peak_memory_bytes=[max(v[d] for v in memory[m]) for d in range(gpu)] if memory[m] else [],
             limitation='B0_COUNT_INPUTS_NOT_REPRESENTATIVE_OF_ALL_SWS_MODALITIES; NEW_SMOKE_AND_WHITEBOX_FORWARD_MEASUREMENT_REQUIRED'))
    resource=dict(status='ESTIMATE_NOT_AUTHORIZATION',models=estimates,behavior_naive_gpu_hours=sum(x['naive_smoke_extrapolation_gpu_hours'] for x in estimates),
        E0_new_requests=0,E0_policy='REUSE_IN_PROGRESS_BASELINE_NO_DUPLICATE_JOBS',
        expanded_authorization_recovered=False,old_B0_gpu_budget=24,old_budget_reusable_for_SWS=False,
        proposed_total_gpu_hour_ceiling=500,proposed_breakdown_gpu_hours={'behavior_and_C1_allowance':250,'M0_M1_M2_C2_unmeasured_allowance':200,'infrastructure_reserve':50},
        breakdown_is_proposed_allowance_not_measured_forecast=True,queue_wait_is_not_gpu_usage=True,
        gpu_submissions_by_this_script=0,actual_SWS_gpu_hours=0)
    save(root/'scheduler/resource_estimate_initial.json',resource)
    commands=[['sinfo','-p','gpu,general,debug','-o','%P %a %l %D %c %m %G'],['sacctmgr','-nP','show','assoc','where','user=anonymous','format=Cluster,Account,User,Partition,QOS'],['sacctmgr','-nP','show','qos','allocated','format=Name,MaxWall,MaxTRESPU,MaxJobsPU,MaxSubmitPU'],['squeue','-u','anonymous','-o','%i|%j|%T|%M|%l|%b|%R'],['lfs','quota','-h','-p','12886','external/project']]
    site=[]
    for cmd in commands:
        result=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
        site.append(dict(command=cmd,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr))
    save(root/'scheduler/site_snapshot.json',dict(timestamp=now(),host=socket.gethostname(),checks=site))
    source_paths=[Path(c['project'])/'research/state_binding_phase_a1/core_execution_v3/pipeline_v3.py',Path(c['campaign'])/'code/vision_process_frozen.py']
    model_impl=Path('external/scratch/industbench_qwen_family/venv/lib/python3.12/site-packages/transformers/models/qwen3_5/modeling_qwen3_5.py')
    if model_impl.exists(): source_paths.append(model_impl)
    save(root/'manifest/initial_runtime_sources.json',[entry(p) for p in source_paths])
    result=dict(status='PASS' if not failures and all(all(x['match'] for x in m['checks']) and all(x['bytes_match'] for x in m['shard_checks']) for m in model_checks) else 'FAIL',
        run_id=c['run_id'],job_id=os.environ['SLURM_JOB_ID'],checked_history_files=len(protected),history_mismatches=failures,
        legacy_raw_source=entry(source),legacy_retained_responses=dict(raw_counts),legacy_worlds={m:len(ws) for m,ws in raw_worlds.items()},
        old_predictions_used_for_new_world_selection=False,new_SWS_responses=0,media_review_signatures_created=0,
        current_backend_bridge='NOT_RUN_NO_GPU_BUDGET',whitebox_equivalence='NOT_RUN',
        legacy_loader_limit='A1/B0 Pipeline.process rejects non-image input; video support must be independently adapted and bridged')
    save(root/'reports/history_and_model_audit.json',result)
    print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__': main()
