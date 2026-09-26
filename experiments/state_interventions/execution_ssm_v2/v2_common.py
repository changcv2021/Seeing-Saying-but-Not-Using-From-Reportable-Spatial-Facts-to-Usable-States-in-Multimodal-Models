"""Append-only SSM NextStage v2. Historical modules are read-only dependencies."""
import sys, copy, math
from pathlib import Path
HERE=Path(__file__).resolve().parent
SPACE=HERE.parents[2]
OLD_CODE=SPACE/'experiments/sequential_state/execution_ssm_v1'
sys.path.insert(0,str(OLD_CODE))
from ssm_common import *
HERE=Path(__file__).resolve().parent
SPACE=HERE.parents[2]
OLD_ROOT=ROOT
RUN='ssm_nextstage_v2_20260911'
ROOT=OLD_ROOT.parent/RUN
SEED=20260911
GUIDE=HERE.parent/'SpaceConflict_SSM_NextStage_v2_Work_Guide_CN.md'
EXCLUSIONS='nid0642,nid0653,nid0661,nid0674,nid0685,nid0688,nid0694,nid0698'

def cli(description):
    p=argparse.ArgumentParser(description=description)
    p.add_argument('--run-id',default=RUN);p.add_argument('--seed',type=int,default=SEED)
    p.add_argument('--resume',action='store_true');p.add_argument('--dry-run',action='store_true');p.add_argument('--limit',type=int)
    return p

def context(a):
    if a.run_id!=RUN or a.seed!=SEED or a.limit is not None:raise ValueError('FROZEN_SCOPE')
    if not a.dry_run and (not os.environ.get('SLURM_JOB_ID') or socket.gethostname().startswith('login')):raise ValueError('COMPUTE_ALLOCATION_REQUIRED')
    c=load(SWS_CODE/'config_auto_v2.json');c.update(root=str(ROOT),run_id=RUN,seed=SEED)
    c['generation']['joint_large_map_max_new_tokens']=512
    return c,ROOT

def runtime_refs():
    from real_compile_v1 import runtime_files
    c=load(SWS_CODE/'config_auto_v2.json')
    return runtime_files(c)+[entry(HERE/n) for n in ['v2_common.py','runtime.py','behavior_score.py','job.sh']]

def request(base,batch,condition,text,target,world=None):
    r=copy.deepcopy(base);r.pop('request_id',None);r.pop('model_independent_request_hash',None)
    w=world or r['world_cluster_id']
    r.update(experiment=batch,condition=condition,world_cluster_id=w,target_state=target,queried_fact_id=condition,
             wording='SSM_NEXTSTAGE_V2_FROZEN',logical_bundle_id=digest([RUN,batch,w]),models=MODELS)
    r['payload']['text']=text;r['requested_tokens']=512
    r['request_id']='ssmv2_'+digest([RUN,batch,w,r['payload'],r['schema']])[:24]
    r['model_independent_request_hash']=digest(r)
    return r

def publish(batch,reqs,gold,panel,protocol,source_refs,compiler):
    out=ROOT/'batches'/batch
    assert len({r['request_id'] for r in reqs})==len(reqs)
    assert {r['request_id'] for r in reqs}=={g['request_id'] for g in gold}
    save(out/'public_inputs/requests.jsonl',reqs,'jsonl');save(out/'private_gold/request_gold.jsonl',gold,'jsonl')
    save(out/'private_gold/world_panel.jsonl',panel,'jsonl')
    save(out/'manifest/PROTOCOL.json',protocol)
    worlds=sorted({r['world_cluster_id'] for r in reqs},key=lambda w:digest([SEED,batch,'SHARD',w]))
    groups=[worlds[i:i+24] for i in range(0,len(worlds),24)];shards=[]
    for i,ws in enumerate(groups):
        rr=[r for r in reqs if r['world_cluster_id'] in ws];p=out/f'public_inputs/shard_{i:03}.jsonl';save(p,rr,'jsonl')
        shards.append(dict(shard=i,worlds=len(ws),requests=len(rr),request_file=entry(p)))
    save(out/'manifest/shards.json',shards)
    save(out/'manifest/REQUEST_LOCK.json',dict(status='FROZEN_BEFORE_NEW_OUTPUTS',run_id=RUN,batch=batch,
        code=runtime_refs()+[entry(compiler)],public_inputs=[entry(out/'public_inputs/requests.jsonl'),entry(out/'manifest/shards.json'),entry(out/'manifest/PROTOCOL.json')]+[s['request_file'] for s in shards],
        private_inputs=[entry(out/'private_gold'/n) for n in ['request_gold.jsonl','world_panel.jsonl']],
        source_refs=source_refs,guide=entry(GUIDE),no_answer_based_retry=True,models=MODELS,
        historical_outputs_immutable=True,human_verified=False,review_status='HUMAN_REVIEW_WAIVED_BY_RESEARCHER'))
    report=dict(status='FROZEN_PROCESSOR_PENDING',batch=batch,worlds=len(worlds),requests_per_model=len(reqs),shards=len(shards))
    save(out/'manifest/BUILD_ACCEPTANCE.json',report);print(json.dumps(report),flush=True)

def cluster_ci(values,cluster_key='world_cluster_id',value_key='value'):
    """Mean across observations; bootstrap independent clusters, preserving cluster size."""
    import numpy as np
    from collections import defaultdict
    groups=defaultdict(list)
    for r in values:
        v=r.get(value_key)
        if v is not None and math.isfinite(float(v)):groups[r[cluster_key]].append(float(v))
    if not groups:return dict(n=0,worlds=0,mean=None,ci_low=None,ci_high=None)
    sums=np.array([sum(v) for v in groups.values()]);counts=np.array([len(v) for v in groups.values()])
    n=len(sums);rng=np.random.default_rng(SEED);ix=rng.integers(n,size=(5000,n))
    boot=sums[ix].sum(1)/counts[ix].sum(1)
    return dict(n=int(counts.sum()),worlds=n,mean=float(sums.sum()/counts.sum()),
                ci_low=float(np.quantile(boot,.025)) if n>1 else None,ci_high=float(np.quantile(boot,.975)) if n>1 else None,
                uncertainty='95% percentile cluster bootstrap; 5000; seed 20260911; not multiplicity-adjusted')
