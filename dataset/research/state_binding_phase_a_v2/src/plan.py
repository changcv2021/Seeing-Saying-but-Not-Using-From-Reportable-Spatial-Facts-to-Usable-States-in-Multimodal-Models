"""Freeze one shared panel using measured setup cost and output schema, never accuracy."""
import math
from base import *
from build import construct
from metrics import parse

# Predeclared diminishing panel options; chosen only once, before discovery results.
OPTIONS=[(96,128,32,16),(64,96,24,12),(48,72,16,8),(32,48,12,6),(16,32,8,4)]

def main():
    a=args(__doc__).parse_args(); cfg,root,project=setup(a)
    if a.dry_run: print(json.dumps(dict(status='PLANNED',options=OPTIONS,uses_discovery_outcomes=False))); return
    authpath=root/'manifest/gpu_authorization.json'
    if not authpath.exists():
        write(root/'reports/resource_readiness.json',dict(status='BLOCKED',reason='EXPLICIT_GPU_BUDGET_CONFIRMATION_NOT_RECEIVED',gpu_jobs_submitted=False)); return
    auth=load(authpath)
    if not auth.get('batch_authorized') or not auth.get('total_gpu_hours'):
        write(root/'reports/resource_readiness.json',dict(status='BLOCKED',reason='BATCH_BUDGET_NOT_AUTHORIZED')); return
    if (root/'inputs/discovery/requests.jsonl').exists():
        # Frozen panel cannot be revised in response to the discovery results.
        print(json.dumps(load(root/'manifest/resource_plan.json'))); return
    stage=cfg.get('setup_input_stage','setup')
    gatepath=root/'reports'/('smoke_gate_'+stage+'.json')
    if not gatepath.exists() or load(gatepath)['status']!='PASS':
        write(root/'reports/resource_readiness.json',dict(status='BLOCKED',reason='FULL_SMOKE_GATE_NOT_PASS',evidence=str(gatepath)))
        raise SystemExit(2)
    setup_requests=unique(rows(root/'inputs'/stage/'requests.jsonl'),'request_id')
    setup_gold=unique(rows(root/'gold'/stage/'gold.jsonl'),'request_id')
    smoke=load(root/'manifest'/stage/'smoke_requests.json'); measurements={}
    minimum=root/'manifest/minimal_measurement_authorization.json'
    # Reserve the full bounded allocation, including setup/teardown, not just generation.
    spent=load(minimum)['max_total_gpu_hours'] if minimum.exists() else 0
    # Count full approved smoke allocations, not just generation plus weight loading.
    # Import, processor construction, I/O and teardown also consume allocated GPUs.
    spent+=auth['full_smoke_reserved_gpu_hours']
    smoke_generation_load_gpu_hours=0
    for key in cfg['models']:
        directory=root/'raw'/stage/key; completion=directory/'completion.json'
        if not completion.exists():
            write(root/'reports/resource_readiness.json',dict(status='BLOCKED',reason='SMOKE_NOT_COMPLETED',model=key)); return
        c=load(completion); expected={rid for rid in smoke['request_ids'] if key in setup_requests[rid]['models']}
        if c['status']!='COMPLETE' or c['infrastructure_errors'] or {r['request_id'] for r in c['raw_index']}!=expected: raise ValueError('SMOKE_INCOMPLETE_OR_INFRASTRUCTURE_FAILURE')
        records=[load(directory/(rid+'.json')) for rid in sorted(expected)]
        valid=sum(parse(r,setup_gold[r['request_id']])['status']!='INVALID' for r in records)
        # Interface violations are measured behavioral outcomes, not a model
        # performance gate. The original threshold failure is preserved separately.
        # Engineering validity is enforced by smoke_gate, parser tests and preflight.
        env=load(directory/'environment.json')
        if env['effective_mode']['enable_thinking'] or env['effective_mode']['max_new_tokens']!=512: raise ValueError('SMOKE_MODE_MISMATCH')
        costs={}
        for r in records:
            rr=setup_requests[r['request_id']]
            bucket=(rr['condition'],bool(rr['payload']['media']))
            costs[bucket]=max(costs.get(bucket,0),r['wall_seconds'])
        measurements[key]=dict(costs=costs,load_seconds=c['load_seconds'],gpus=c['gpus'],records=records,schema_valid=valid,schema_total=len(records))
        smoke_generation_load_gpu_hours+=(c['total_wall_seconds']+c['load_seconds'])*c['gpus']/3600
    estimates=[]; selected=None
    for caps in OPTIONS:
        rr,_,_=construct(cfg,root,'discovery',*caps,persist=False)
        per_model={}; total=spent
        for key,m in measurements.items():
            seconds=m['load_seconds']+30
            for r in rr:
                if key not in r['models']: continue
                media=bool(r['payload']['media']); bucket=(r['condition'],media)
                matched=[x for x in m['records'] if (setup_requests[x['request_id']]['condition'],bool(setup_requests[x['request_id']]['payload']['media']))==bucket]
                if not matched: matched=[x for x in m['records'] if bool(setup_requests[x['request_id']]['payload']['media'])==media]
                def extrapolate(x):
                    source=setup_requests[x['request_id']]
                    # Conservative prospective context scaling in addition to 50% margin.
                    media_ratio=len(r['payload']['media'])/max(1,len(source['payload']['media']))
                    text_ratio=len(r['payload']['text'])/max(1,len(source['payload']['text']))
                    return x['wall_seconds']*max(1,media_ratio,text_ratio)
                seconds+=max(extrapolate(x) for x in matched)
            seconds=math.ceil(seconds*1.5) # explicit 50% safety margin, not a performance claim
            per_model[key]=dict(wall_seconds=seconds,gpus=m['gpus'],gpu_hours=seconds*m['gpus']/3600,requests=sum(key in r['models'] for r in rr))
            total+=per_model[key]['gpu_hours']
        entry=dict(caps=caps,total_gpu_hours_including_smoke=total,models=per_model)
        estimates.append(entry)
        hard_caps=auth.get('discovery_wall_caps_seconds',{})
        within_wall=all(per_model[k]['wall_seconds']<=hard_caps.get(k,float('inf')) for k in cfg['models'])
        if total<=auth['total_gpu_hours'] and within_wall: selected=entry; break
    if selected is None:
        write(root/'reports/resource_readiness.json',dict(status='BLOCKED',reason='NO_PREDECLARED_PANEL_FITS_MEASURED_BUDGET',estimates=estimates,measured_smoke_gpu_hours=spent)); return
    integration=load(root/'reports'/(stage+'_integration_checks.json'))
    if integration['status']!='PASS': raise ValueError('INPUT_INTEGRATION_NOT_PASS')
    plan=construct(cfg,root,'discovery',*selected['caps'])
    record=dict(status='PASS',budget_authorized=True,authorization=evidence_entry(authpath),total_gpu_hours=auth['total_gpu_hours'],reserved_setup_gpu_hours=spent,
        measured_smoke_generation_load_gpu_hours=smoke_generation_load_gpu_hours,
        estimate=selected,options_considered=estimates,safety_factor=1.5,selection_basis='SETUP_COST_AND_SCHEMA_ONLY; no discovery outcome read',discovery_input_hash=plan['input_hash'],
        generated_token_cap=512,peak_allocated_gpu_bytes={k:[max(r['peak_memory_bytes'][i] for r in m['records']) for i in range(m['gpus'])] for k,m in measurements.items()},
        output_contract_diagnostics={k:dict(valid=m['schema_valid'],total=m['schema_total'],blocking=False) for k,m in measurements.items()},
        protocol_amendment=evidence_entry(root/'manifest/setup_gate_amendment_v24.json'),
        cost_extrapolation='maximum matching-condition/modality setup cost, scaled up for media-count/text-length ratio, then 1.5 safety factor',
        auto_submit=False,stop_after_phase_a=True)
    frozen_write(root/'manifest/resource_plan.json',record)
    write(root/'reports/resource_readiness.json',record)
    print(json.dumps(record))

if __name__=='__main__': main()
