"""Setup-only interface/resource gate. Never selects by answer correctness."""
import subprocess
from base import *
from metrics import parse, observed_object


def violation_detail(raw,gold):
    obj=observed_object(raw.get('raw_response',''),raw.get('truncated',False))
    if not obj: return dict(category='NO_UNAMBIGUOUS_COMPLETE_REQUIRED_OBJECT')
    if gold['kind']=='value':
        if obj.get('status') not in ['VALUE','UNDETERMINED']:
            return dict(category='STATUS_ENUM_VIOLATION',observed_status=obj.get('status'),allowed_statuses=['VALUE','UNDETERMINED'],value_field_present='value' in obj)
        return dict(category='VALUE_TYPE_OR_STATUS_VALUE_CONFLICT',observed_status=obj.get('status'),expected_type=gold['domain']['type'])
    if gold['kind']=='verdict':
        field=gold.get('field','label'); allowed=list(gold['mapping']) if gold.get('mapping') else list(LABELS)
        return dict(category='LABEL_FIELD_OR_MAPPING_VIOLATION',field=field,observed_field=obj.get(field),allowed_outputs=allowed)
    return dict(category='STRUCTURED_FIELDS_OR_TYPES_VIOLATION',kind=gold['kind'])


def main():
    a=args(__doc__).parse_args(); cfg,root,project=setup(a)
    if a.dry_run: print(json.dumps(dict(status='PLANNED',action='smoke_gate'))); return
    stage=cfg['setup_input_stage']; reqfile=root/'inputs'/stage/'requests.jsonl'
    req=unique(rows(reqfile),'request_id'); gold=unique(rows(root/'gold'/stage/'gold.jsonl'),'request_id')
    smoke=load(root/'manifest'/stage/'smoke_requests.json'); presentation={}; outputs=[]; checks=[]
    tests=subprocess.run([sys.executable,'-m','unittest','discover','-v','-s',str(CODE/'tests')],capture_output=True,text=True)
    write(root/'reports/phase_a_unit_tests.json',dict(status='PASS' if not tests.returncode else 'FAIL',stdout=tests.stdout,stderr=tests.stderr,returncode=tests.returncode))
    checks.append(dict(check='scorer_and_pairing_tests',status='PASS' if not tests.returncode else 'FAIL'))
    for model in cfg['models']:
        expected={rid for rid in smoke['request_ids'] if model in req[rid]['models']}
        directory=root/'raw'/stage/model; cp=directory/'completion.json'
        if not cp.exists():
            checks.append(dict(check=model+':complete',status='NOT_RUN')); continue
        c=load(cp); exact=c['status']=='COMPLETE' and not c['infrastructure_errors'] and {r['request_id'] for r in c['raw_index']}==expected
        checks.append(dict(check=model+':complete',status='PASS' if exact else 'FAIL',expected=len(expected),completed=c['completed']))
        valid=0; errors=[]; resource=[]
        for rid in sorted(expected):
            p=directory/(rid+'.json')
            if not p.exists(): continue
            r=load(p); pp=parse(r,gold[rid]); ok=pp['status'] not in ['INVALID','NOT_RUN']
            valid+=ok
            if not ok: errors.append(dict(request_id=rid,condition=req[rid]['condition'],raw_path=str(p),raw_sha256=sha(p),reason='OUTPUT_CONTRACT_INVALID',detail=violation_detail(r,gold[rid])))
            rendered_path=root/'rendered'/stage/model/(rid+'.json')
            rendered=load(rendered_path)
            assert rendered['rendered_prompt_sha256']==r['rendered_prompt_sha256']
            presentation.setdefault(rid,[]).append(dict(model=model,prompt=r['rendered_prompt_sha256'],presentation=r['presentation_hash']))
            assert r['output_tokens']<=cfg['max_new_tokens']==512
            env=load(r['environment_path'])
            assert not env['effective_mode']['enable_thinking'] and not env['effective_mode']['do_sample']
            assert env['effective_mode']['max_new_tokens']==512 and env['request_manifest_sha256']==sha(reqfile)
            assert sha(r['environment_path'])==r['environment_sha256']
            resource.append(dict(request_id=rid,condition=req[rid]['condition'],media_count=len(req[rid]['payload']['media']),input_tokens=r['input_tokens'],
                output_tokens=r['output_tokens'],wall_seconds=r['wall_seconds'],peak_memory_bytes=r['peak_memory_bytes'],truncated=r['truncated']))
        checks.append(dict(check=model+':schema',status='PASS' if expected and valid/len(expected)>=.95 else 'FAIL',valid=valid,total=len(expected),invalid=errors,
            blocking=False,scope='OBSERVED_MODEL_OUTPUT_BEHAVIOR',
            note='Original 95% diagnostic retained. See disclosed setup_gate_amendment_v24.json; INVALID outputs remain failures, no retries or inferred answers.'))
        outputs.append(dict(model=model,expected=len(expected),schema_valid=valid,load_seconds=c['load_seconds'],gpus=c['gpus'],records=resource))
    identical=all(len({(r['prompt'],r['presentation']) for r in vals})==1 for vals in presentation.values())
    checks.append(dict(check='identical_actual_common_prompts_and_media',status='PASS' if identical and len(outputs)==3 else 'FAIL',requests=len(presentation)))
    amendment=root/'manifest/setup_gate_amendment_v24.json'
    assert amendment.exists() and load(amendment)['discovery_outcomes_exist'] is False
    result=dict(status='PASS' if all(x['status']=='PASS' for x in checks if x.get('blocking',True)) else 'BLOCKED',checks=checks,models=outputs,
        status_scope='ENGINEERING_EXECUTION_AND_PARSER_NOT_MODEL_SCHEMA_SUCCESS',protocol_amendment=evidence_entry(amendment),
        stage=stage,input_hash=sha(reqfile),data_purpose='SETUP_ONLY',original_review='USER_ATTESTED_PASS',derived_review='PROVISIONAL',
        answer_accuracy_used_for_panel_selection=False)
    write(root/'reports'/('smoke_gate_'+stage+'.json'),result)
    write(root/'reports'/('actual_input_consistency_'+stage+'.json'),dict(status='PASS' if identical and len(outputs)==3 else 'FAIL',by_request=presentation))
    print(json.dumps(dict(status=result['status'],report=str(root/'reports'/('smoke_gate_'+stage+'.json')))))
    if result['status']!='PASS': raise SystemExit(2)


if __name__=='__main__': main()
