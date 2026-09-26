"""Isolated behavioral closure; immutable SWS history and source-grounded evidence."""
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
SWS_CODE=HERE.parents[2]/'experiments/spatial_world_state/execution_sws_v1'
sys.path.insert(0,str(SWS_CODE))
from common import *
from review_policy_v2 import effective_policy
RUN='bc_20260910_v1'
ROOT=Path('artifacts/model_results/behavioral_closure')/RUN
BASE_CONFIG=SWS_CODE/'config_auto_v2.json'
GUIDE=HERE.parent/'SpaceConflict_NextStage_Behavioral_Closure_Work_Guide_CN.md'
BATCHES={**{f'D{i:02}':f'ca_source_d{i:02}_20260910' for i in range(1,5)},
    'E8':'native_e8_breadth_v1_20260910','NONCOUNT':'noncount_breadth_v1_20260910','MULTIVIEW':'multiview_breadth_v2_20260910',
    'E5S':'e5_sequence_supplement_v1_20260910'}

def cli(description):
    p=argparse.ArgumentParser(description=description)
    p.add_argument('--run-id',default=RUN);p.add_argument('--seed',type=int,default=20260909)
    p.add_argument('--dry-run',action='store_true');p.add_argument('--resume',action='store_true');p.add_argument('--limit',type=int)
    return p

def context(a):
    c=load(BASE_CONFIG);effective_policy(c)
    if a.run_id!=RUN or a.seed!=c['seed'] or a.limit is not None:raise ValueError('FROZEN_SCOPE_MISMATCH')
    if not a.dry_run and (not os.environ.get('SLURM_JOB_ID') or socket.gethostname().startswith('login')):raise ValueError('COMPUTE_ALLOCATION_REQUIRED')
    return c,Path(c['root']),ROOT

def check(ref):
    if sha(ref['path'])!=ref['sha256']:raise ValueError('FROZEN_HASH_CHANGED:'+ref['path'])
    return Path(ref['path'])

def eq(a,b):return type(a) is type(b) and a==b

def csvrows(p):
    with Path(p).open() as f:return list(csv.DictReader(f))

def scores(sws,case,model):
    if case=='E5S':
        pp=list((sws/'rescoring/coverage_supplement_interface_v3'/BATCHES[case]/BATCHES[case]/model).glob('snapshot_*'))
        if len(pp)!=1:raise ValueError('AMBIGUOUS_SCORE_SNAPSHOT')
        folder=pp[0]
    else:
        index=load(sws/'rescoring/interface_v3_20260910/ACTIVE_SCORING_INDEX.json')
        x=next(x for x in index['cases'] if (x['case'],x['model'])==(case,model))
        check(x['acceptance']);check(x['canonical']);folder=Path(x['normalized']).parent
    ac=load(folder/'RESCORE_ACCEPTANCE.json')
    if ac['status']!='COMPLETE':raise ValueError('INCOMPLETE_HISTORICAL_SCORES')
    file=folder/'normalized/all_physical_request_scores.csv'
    rr={r['request_id']:r for r in csvrows(file)}
    for r in rr.values():
        r['component_values']=json.loads(r['component_values'])
        r['expected']=json.loads(r['expected'])
        r['correct']=r.get('content_correct')=='True' if r['execution_status']=='RETURNED' else None
    return rr,[entry(file),entry(folder/'RESCORE_ACCEPTANCE.json')]

def endpoint(sc,rid):
    r=sc.get(rid,{})
    return dict(request_id=rid,status=r.get('execution_status','NOT_RUN'),parser_status=r.get('schema_status','NOT_RUN'),
        prediction=r.get('component_values',{}),correct=r.get('correct'),gold=r.get('expected'),
        raw_path=r.get('raw_path'),raw_sha256=r.get('raw_sha256'))

def batch(sws,case):
    p=sws/'batches'/BATCHES[case]
    return p,{r['request_id']:r for r in rows(p/'public_inputs/requests.jsonl')},list(rows(p/'private_gold/matched_structure.jsonl'))

def publish(out,name,matrix,sources,extra=None):
    dest=out/name
    csvsave(dest/'matrix.csv',matrix)
    refs={}
    def walk(x):
        if isinstance(x,dict):
            if x.get('raw_path') and x.get('raw_sha256'):
                key=(x['raw_path'],x['raw_sha256']);refs[key]=dict(path=key[0],sha256=key[1],request_id=x.get('request_id'))
            for v in x.values():walk(v)
        elif isinstance(x,list):
            for v in x:walk(v)
    for row in matrix:walk(row)
    save(dest/'raw_response_index.jsonl',refs.values(),'jsonl')
    source_refs=list({r['path']:r for r in sources}.values())
    for ref in source_refs:check(ref)
    report=dict(status='COMPLETE_FOR_EXISTING_EVIDENCE_NOT_FINAL_STUDY',module=name,rows=len(matrix),
        worlds=len({r.get('world_cluster_id') for r in matrix if r.get('world_cluster_id')}),
        created_at=now(),job_id=os.environ['SLURM_JOB_ID'],sources=source_refs,
        outputs=[entry(dest/'matrix.csv'),entry(dest/'raw_response_index.jsonl')],code=entry(HERE/'closure.py'),
        review_status='HUMAN_REVIEW_WAIVED_BY_RESEARCHER',grade='AUTO_ONLY_PROVISIONAL',
        original_gold_and_responses_modified=False,new_model_calls=0,**(extra or {}))
    save(dest/'ACCEPTANCE.json',report);print(json.dumps({k:v for k,v in report.items() if k not in ('sources','outputs')}),flush=True)
