"""Cost-only preview; never freezes, submits, or reads prediction correctness."""
from base import *
from build import construct
from plan import OPTIONS

def calculate(cfg,root):
    setup=unique(rows(root/'inputs/setup/requests.jsonl'),'request_id')
    measurements={}
    for key in cfg['models']:
        directory=root/'raw/measurement'/key; path=directory/'completion.json'
        if not path.exists(): return dict(status='BLOCKED',reason='THREE_MODEL_MINIMUM_MEASUREMENT_NOT_COMPLETE')
        completion=load(path)
        if completion.get('infrastructure_errors') or completion.get('status')!='COMPLETE': return dict(status='BLOCKED',reason='MEASUREMENT_INFRASTRUCTURE_FAILURE',model=key)
        costs={}; media_max=1
        for item in completion['raw_index']:
            r=load(item['path']); request=setup[r['request_id']]; key2=(request['condition'],bool(request['payload']['media']))
            costs[key2]=max(costs.get(key2,0),r['wall_seconds'])
            media_max=max(media_max,len(request['payload']['media']))
        measurements[key]=dict(costs=costs,media_max=media_max,completion=completion)
    proposals=[]
    for caps in OPTIONS:
        requests,_,groups=construct(cfg,root,'discovery',*caps,persist=False)
        models={}; total=0
        for key,m in measurements.items():
            seconds=m['completion']['load_seconds']+60; selected=[r for r in requests if key in r['models']]; fallback_n=0
            for r in selected:
                media=bool(r['payload']['media']); bucket=(r['condition'],media)
                available=[v for (cond,vis),v in m['costs'].items() if vis==media]
                if not available: return dict(status='BLOCKED',reason='NO_MODALITY_COST_SAMPLE',model=key)
                seconds+=m['costs'].get(bucket,max(available))*max(1,len(r['payload']['media'])/m['media_max'])
                fallback_n+=bucket not in m['costs']
            seconds*=1.5
            models[key]=dict(request_count=len(selected),maximum_generated_tokens=len(selected)*cfg['max_new_tokens'],estimated_seconds=seconds,estimated_gpu_hours=seconds*m['completion']['gpus']/3600,unmeasured_condition_fallback_requests=fallback_n)
            total+=models[key]['estimated_gpu_hours']
        proposals.append(dict(caps=caps,actual_mechanism_groups=len(groups),mechanism_clusters=len({g['cluster_id'] for g in groups}),models=models,discovery_gpu_hours_estimate=total,
            reserved_minimum_measurement_gpu_hours=2/3,total_including_minimum_bound=total+2/3))
    return dict(status='PROVISIONAL_COST_PREVIEW',proposals=proposals,safety_factor=1.5,batch_authorized=False,discovery_frozen=False,
        caveats=['Only ten setup requests per model. Unmeasured conditions use worst matching media-present/media-absent timing.','Media count scaling is a conservative heuristic, not measured video/frame or context-length scaling.','Does not include not-yet-run full setup smoke. Runtime variability and walltime granularity require a final plan after full smoke.'],
        selection_used_correctness=False)

def main():
    a=args(__doc__).parse_args(); cfg,root,_=setup(a)
    if a.dry_run: print(json.dumps(dict(status='PLANNED',action='cost_preview'))); return
    result=calculate(cfg,root); write(root/'reports/cost_preview.json',result); print(json.dumps(result))

if __name__=='__main__': main()
