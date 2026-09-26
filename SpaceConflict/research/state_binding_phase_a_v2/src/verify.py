"""CPU integration checks, dependency snapshot and review pack; no model execution."""
import html
import subprocess
from base import *

def main():
    a=args(__doc__).parse_args(); cfg,root,project=setup(a)
    stage=cfg.get('setup_input_stage','setup')
    if a.dry_run: print(json.dumps({'status':'PLANNED','action':'verify_setup'})); return
    proc=subprocess.run([sys.executable,'-m','unittest','discover','-v','-s',str(CODE/'tests')],text=True,capture_output=True)
    write(root/'reports/phase_a_unit_tests.json',dict(status='PASS' if proc.returncode==0 else 'FAIL',stdout=proc.stdout,stderr=proc.stderr,returncode=proc.returncode))
    if proc.returncode: raise ValueError('PHASE_A_UNIT_TESTS_FAILED')
    req=list(rows(root/'inputs'/stage/'requests.jsonl')); gold=unique(rows(root/'gold'/stage/'gold.jsonl'),'request_id')
    split=load(root/'manifest/cluster_split.json')['partition']
    checks=[]
    def check(name,ok,detail=None):
        checks.append(dict(check=name,status='PASS' if ok else 'FAIL',detail=detail))
        if not ok: raise ValueError('INTEGRATION_FAILED:'+name)
    check('exact_gold_join',set(gold)=={r['request_id'] for r in req})
    model_checks=[]
    for m in load(Path(cfg['campaign'])/'config.json')['models']:
        modeldir=Path(m['model_path']); index=modeldir/'model.safetensors.index.json'
        shards=sorted(set(load(index)['weight_map'].values()))
        items=[dict(path=str(modeldir/name),exists=(modeldir/name).is_file(),bytes=(modeldir/name).stat().st_size if (modeldir/name).is_file() else None) for name in shards]
        check('model_shards_present:'+m['key'],bool(items) and all(x['exists'] and x['bytes']>0 for x in items))
        model_checks.append(dict(model=m['key'],revision=m['revision'],index=evidence_entry(index),shards=items,validation='INDEX_COVERAGE_AND_NONEMPTY_FILE_STAT; full weight hashes not recomputed'))
    write(root/'reports/model_weight_readiness.json',dict(status='PASS',models=model_checks))
    check('setup_only',all(split[r['cluster_id']]=='setup' for r in req))
    check('gold_not_in_ordinary_records',all(not {'gold','private','claim_gold','gold_by_state','reference_answer'}&set(r) for r in req))
    check('oracle_media_absent',all(not r['payload']['media'] for r in req if r['is_oracle']))
    check('local_oracle_excludes_computed_state',all(not any(k in r['payload']['text'] for k in ['"post_predicate"','"count_deltas"','"post_facts"']) for r in req if r['condition']=='G_LOCAL'))
    check('ordinary_media_present',all(r['payload']['media'] for r in req if not r['is_oracle'] and r['condition']!='ACTION_PARSE'))
    check('declared_512_cap',all(r['max_new_tokens']==512 and '512' in r['payload']['system'] for r in req))
    core={'D_ORIG','FACT_SEPARATE','ACTION_PARSE','FACT_JOINT','SELECT_VALUE','STATE_VERDICT'}
    check('identical_three_model_core',all(r['models']==cfg['models'] for r in req if r['condition'] in core))
    for cond in ['SELECT_VALUE','STATE_VERDICT']:
        for key in {(r['group_id'],r['claim_id']) for r in req if r['condition']==cond}:
            pair=[r for r in req if r['condition']==cond and (r['group_id'],r['claim_id'])==key]
            check('target_only:'+cond+':'+str(key),len(pair)==2 and pair[0]['payload']['media']==pair[1]['payload']['media'] and pair[0]['payload']['text'].replace('TARGET STATE: '+pair[0]['target'],'TARGET STATE: <TARGET>')==pair[1]['payload']['text'].replace('TARGET STATE: '+pair[1]['target'],'TARGET STATE: <TARGET>'))
    # Select interface/cost requests prospectively, never by answer quality.
    bins={}
    for r in sorted(req,key=lambda r:stable_rank(cfg['seed'],r['request_id'])):
        domain=gold[r['request_id']].get('domain',{}).get('type','')
        key=(r['condition'],r['source'] if r['condition']=='D_ORIG' else domain,r['level'] if r['condition']=='D_ORIG' else '')
        bins.setdefault(key,r)
    chosen={r['request_id']:r for r in bins.values()}
    for r in sorted(req,key=lambda r:stable_rank(cfg['seed']+1,r['request_id'])):
        if len(chosen)>=40: break
        chosen.setdefault(r['request_id'],r)
    # Preserve target pairs in smoke too; request count is data-derived, not an untested cost estimate.
    for r in list(chosen.values()):
        if r['condition'] in ['SELECT_VALUE','STATE_VERDICT']:
            for rr in req:
                if (rr['group_id'],rr['condition'],rr['claim_id'])==(r['group_id'],r['condition'],r['claim_id']): chosen[rr['request_id']]=rr
    ordered=sorted(chosen.values(),key=lambda r:stable_rank(cfg['seed']+4,r['request_id']))
    minimal=[]
    for condition in ['D_ORIG','FACT_SEPARATE','FACT_JOINT','SELECT_VALUE','STATE_VERDICT','G_MULTI_VALUE','G_SHAM_VALUE','ACTION_PARSE']:
        candidates=[r for r in ordered if r['condition']==condition and r['models']==cfg['models']]
        if candidates: minimal.append(candidates[0]['request_id'])
    for r in ordered:
        if r['condition']=='D_ORIG' and r['request_id'] not in minimal and len(minimal)<10: minimal.append(r['request_id'])
    frozen_write(root/'manifest'/stage/'smoke_requests.json',dict(request_ids=[r['request_id'] for r in ordered],measurement_request_ids=minimal,by_model={m:sum(m in r['models'] for r in ordered) for m in cfg['models']},selection_basis='Prospective condition/schema/source coverage; no outputs read',requests_hash=sha(root/'inputs'/stage/'requests.jsonl')))
    files=list((CODE/'src').glob('*.py'))+list((CODE/'configs').glob('*'))+list((CODE/'tests').glob('*.py'))+list((CODE/'scripts').glob('*'))
    files.extend((CODE.parent/'spatial_conflict_diagnosis_v1/src').glob('*.py'))
    files.extend(Path(cfg['campaign'],'code').glob('*.py'))
    write(root/'manifest/implementation_dependencies.json',[evidence_entry(p) for p in sorted(set(files))])
    page=['<!doctype html><meta charset="utf-8"><title>Phase A setup review</title><h1>Setup input review</h1><p>Parent review: USER_ATTESTED PASS. Derived queries: PROVISIONAL. These are planned inputs, not actual processor-rendered media. Actual presentations will only exist after GPU smoke.</p>']
    for r in req:
        page+=['<details><summary>'+html.escape(r['request_id']+' '+r['condition'])+'</summary><pre>'+html.escape(json.dumps(r,ensure_ascii=False,indent=2))+'</pre><h3>Private reviewer-only truth (never inference input)</h3><pre>'+html.escape(json.dumps(gold[r['request_id']],ensure_ascii=False,indent=2))+'</pre></details>']
    write(root/'review'/(stage+'_review.html'),'\n'.join(page),'text')
    write(root/'reports'/(stage+'_integration_checks.json'),dict(status='PASS',checks=checks,smoke_requests=len(ordered),actual_processor_review='NOT_RUN',stage=stage))
    print(json.dumps(dict(status='PASS',request_count=len(req),smoke_request_count=len(ordered),unit_test_log=str(root/'reports/phase_a_unit_tests.json'))))

if __name__=='__main__': main()
