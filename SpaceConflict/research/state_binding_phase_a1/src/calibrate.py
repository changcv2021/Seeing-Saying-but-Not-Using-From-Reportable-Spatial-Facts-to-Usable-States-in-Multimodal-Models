"""Score setup-only frozen responses, enforce schema gate; never inspect real outcomes."""
from collections import defaultdict
from common import *
from scorer import score, selftest

def main():
    a=arguments(__doc__).parse_args(); cfg,root=setup(a)
    if a.dry_run: print('PLANNED: setup-only score and syntax gate'); return
    require_compute(); test=selftest()
    req=list(rows(root/'inputs/setup_v1/requests.jsonl')); gg={g['request_id']:g for g in rows(root/'gold/setup_v1.jsonl')}
    lock=load(root/'manifest/setup_v1_lock.json')
    if sha(root/'gold/setup_v1.jsonl')!=lock['gold_sha256']: raise ValueError('SETUP_GOLD_CHANGED')
    records=[]; index=[]; checks=[]; resources=[]
    for model in cfg['models']:
        d=root/'raw/setup_v1'/model; complete=load(d/'completion.json'); resources.append(dict(model=model,**complete))
        if complete['requests']!=len(req): raise ValueError('SETUP_INCOMPLETE')
        for r in req:
            p=d/(r['request_id']+'.json'); raw=load(p); g=gg[r['request_id']]; result=score(raw,g)
            records.append(dict(model=model,request_id=r['request_id'],world_id=r['group_id'],level=r['level'],condition=r['condition'],
                interface=g['schema']['kind'],gold=g['expected'],**result))
            index.append(dict(stage='setup_v1',model=model,request_id=r['request_id'],**entry(p),
                rendered_path=str(root/'rendered/setup_v1'/model/(r['request_id']+'.json')),presentation_hash=raw.get('presentation_hash')))
        mr=[r for r in records if r['model']==model]
        for kind in ['ALL','value','joint','action','verdict']:
            rr=[r for r in mr if kind=='ALL' or r['interface']==kind]
            validity=sum(r['schema_valid'] for r in rr)/len(rr)
            checks.append(dict(model=model,interface=kind,requests=len(rr),synthetic_worlds=len({r['world_id'] for r in rr}),
                schema_validity=validity,json_validity=sum(r['json_valid'] for r in rr)/len(rr),
                semantic_accuracy=sum(r['correct'] for r in rr)/len(rr),null=sum(r['status']=='NULL' for r in rr),
                invalid=sum(r['status']=='INVALID' for r in rr),old_status_key=sum(r['status_key_present'] for r in rr),
                status='PASS' if validity>=cfg['schema_gate_minimum'] else 'FAIL'))
    csvsave(root/'setup_interface_calibration.csv',records)
    csvsave(root/'tables/setup_schema_gate.csv',checks)
    save(root/'raw_predictions_index.jsonl',index,'jsonl')
    passed=all(c['status']=='PASS' for c in checks)
    save(root/'reports/setup_calibration_acceptance.json',dict(status='PASS' if passed else 'FAIL',checks=checks,scorer_tests=test,
        task_accuracy_not_gate=True,no_real_world_predictions_accessed=True))
    save(root/'reports/setup_resource_measurement.json',resources)
    save(root/'protocol_lock_a1.json',dict(status='INTERFACE_FROZEN_AWAITING_DERIVED_REVIEW' if passed else 'SETUP_INTERFACE_FAILED_STOP_BEFORE_REAL_WORLDS',
        setup_lock_sha256=sha(root/'manifest/setup_v1_lock.json'),prompt_version=cfg['prompt_version'],
        gate_pass=passed,core_frozen=False,core_inference_authorized=False))
    save(root/'LIVE_STATUS.json',dict(status='SETUP_PASSED_AWAITING_DERIVED_REVIEW' if passed else 'SETUP_FAILED',
        setup_responses=len(records),mechanism_responses=0,mechanism_started=False))
    print(json.dumps(dict(status='PASS' if passed else 'FAIL',responses=len(records),checks=checks)))

if __name__=='__main__': main()
