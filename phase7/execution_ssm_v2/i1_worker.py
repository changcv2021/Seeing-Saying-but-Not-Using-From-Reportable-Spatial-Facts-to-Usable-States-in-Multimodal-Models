"""Actual 9B causal replay. Preserve first raw outputs and pair-specific technical failures."""
import time,fcntl
from v2_common import *
from i1_engine import I1Engine
from interface_repair_v3.adapter import normalize

def verify():
    inp=load(ROOT/'I1/manifest/INPUT_LOCK.json');run=load(ROOT/'I1/manifest/RUNTIME_LOCK.json')
    for ref in inp['public_inputs']+run['code']:check(ref)
    check(run['input_lock']);return inp,run

def technical(e,dest,reqs,panel):
    """No mechanism-score gate. Exact generation equivalence and fixed numerical tolerance."""
    own=load(ROOT/'I1/manifest/TECHNICAL_CASE.json');records=[]
    for name,rid in own['requests']['S2'].items():
        r=reqs[rid];inputs,pres=e.process(r);again,pres2=e.process(r)
        assert pres['presentation_hash']==pres2['presentation_hash'] and e.torch.equal(inputs['input_ids'],again['input_ids']);del again
        vectors=e.capture(inputs,pres['anchors']);li=e.depths[3];pos=pres['anchors']['P_CONTEXT_END'];patch=(li,pos,vectors[li]['P_CONTEXT_END'])
        base=e.generate(inputs);cached=e.reference(inputs,cache=True);full=e.reference(inputs,cache=False)
        noop=e.generate(inputs,patch,readonly=True);selfr=e.generate(inputs,patch)
        answers=['{"value":0}','{"value":12}','{"value":null}']
        teacher=e.score(inputs,answers);stepwise=e.score(inputs,answers,sequential=True);selfscore=e.score(inputs,answers,patch)
        lp_error=max(abs(x['logprob']-y['logprob']) for x,y in zip(teacher,stepwise))
        self_error=max(abs(x['logprob']-y['logprob']) for x,y in zip(teacher,selfscore))
        toks=base['output_token_ids'];eq=all(toks==v['output_token_ids'] for v in [cached,full,noop,selfr])
        records.append(dict(request_id=rid,donor_kind=name,presentation=pres,baseline=base,cached=cached,hf_full=full,noop=noop,self_patch=selfr,
            teacher_scores=teacher,stepwise_scores=stepwise,self_scores=selfscore,token_equivalence=eq,
            teacher_stepwise_max_lp_error=lp_error,self_max_lp_error=self_error,pass_gate=eq and lp_error<=.5 and self_error<=.5))
        print(json.dumps(dict(stage='I1_TECH',kind=name,pass_gate=records[-1]['pass_gate'],seconds=base['generation_seconds'],input_tokens=pres['input_tokens'])),flush=True)
    # A-B-A cache isolation; changed-vector hook against independent HF uncached generation.
    one=records[0];inputs,pres=e.process(reqs[one['request_id']]);other_inputs,other_pres=e.process(reqs[records[1]['request_id']])
    othervec=e.capture(other_inputs,other_pres['anchors']);li=e.depths[3];patch=(li,pres['anchors']['P_CONTEXT_END'],othervec[li]['P_CONTEXT_END'])
    changed=e.generate(inputs,patch);changed_ref=e.reference(inputs,cache=False,patch=patch);repeat=e.generate(inputs)
    cap2=e.generate(inputs,cap=2)
    checks=dict(changed_hook_exact=changed['output_token_ids']==changed_ref['output_token_ids'],request_cache_isolation=repeat['output_token_ids']==one['baseline']['output_token_ids'],cap2_obeys_limit=cap2['output_tokens']<=2)
    save(dest/'TECHNICAL_RAW.json',dict(contexts=records,changed=changed,changed_reference=changed_ref,repeat=repeat,cap2=cap2,checks=checks))
    result=dict(status='PASS' if all(r['pass_gate'] for r in records) and all(checks.values()) else 'FAILED',
        raw=entry(dest/'TECHNICAL_RAW.json'),runtime_lock=entry(ROOT/'I1/manifest/RUNTIME_LOCK.json'),engine=e.config,
        peak_memory_bytes=[e.torch.cuda.max_memory_allocated(i) for i in range(e.torch.cuda.device_count())],
        baseline_seconds=[r['baseline']['generation_seconds'] for r in records],checks=checks,job_id=os.environ['SLURM_JOB_ID'],
        semantic_accuracy_not_a_gate=True,no_prompt_retry=True)
    save(dest/'TECHNICAL_ACCEPTANCE.json',result)
    if result['status']!='PASS':raise ValueError('I1_TECHNICAL_GATE_FAILED_NO_CORE_SUBMISSION')

def main():
    p=cli(__doc__);p.add_argument('--stage',choices=['technical','localize','selected'],required=True);p.add_argument('--shard',type=int)
    a=p.parse_args();c,root=context(a);verify();i1=root/'I1'
    reqs={r['request_id']:r for r in rows(i1/'public_inputs/requests.jsonl')};panel=list(rows(i1/'public_inputs/panel.jsonl'));bycase={p['case_id']:p for p in panel}
    if a.stage=='technical':
        dest=i1/'technical/qwen35_9b';dest.mkdir(parents=True,exist_ok=True)
        if (dest/'TECHNICAL_ACCEPTANCE.json').exists():assert load(dest/'TECHNICAL_ACCEPTANCE.json')['status']=='PASS';return
        e=I1Engine(c,'qwen35_9b',dest);technical(e,dest,reqs,panel);return
    gate=load(i1/'technical/qwen35_9b/TECHNICAL_ACCEPTANCE.json');assert gate['status']=='PASS';check(gate['runtime_lock'])
    sid=a.shard if a.shard is not None else int(os.environ['SLURM_ARRAY_TASK_ID'])
    if a.stage=='localize':
        sh=next(s for s in load(i1/'manifest/shards.json') if s['shard']==sid);worlds=set(sh['worlds'])
        cases=[p for p in panel if p['world_cluster_id'] in worlds and p['split']=='LOCALIZE' and p['cohort'] in ['A','B']]
        # No SELECT requests or SELECT outputs loaded for mechanism selection in this stage.
        windows=None
    else:
        candidates=load(i1/'selection/CANDIDATE_LOCK.json');assert candidates['status']=='CANDIDATES_FROZEN'
        check(candidates['runtime_lock']);windows=candidates['windows'];worlds=sorted({p['world_cluster_id'] for p in panel},key=lambda w:digest([SEED,'I1_SELECTED_SHARD',w]))
        cases=[p for p in panel if p['world_cluster_id'] in set(worlds[sid::8])]
    dest=i1/'raw'/a.stage/f'shard_{sid:03}';dest.mkdir(parents=True,exist_ok=True)
    owner=(dest/'writer.lock').open('a');fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
    e=I1Engine(c,'qwen35_9b',dest);save(dest/'ENGINE.json',e.config)
    baseline_cache={};activation_cache={};metrics=[];started=time.monotonic()
    def baseline(rid):
        r=reqs[rid];inputs,pres=e.process(r);path=dest/'baselines'/(rid+'.json');actpath=dest/'activations'/(rid+'.pt')
        if rid in baseline_cache:return inputs,pres,baseline_cache[rid],activation_cache[rid]
        if path.exists():
            rec=load(path);assert rec['request_hash']==r['model_independent_request_hash'];check(rec['activations'])
            vectors=e.torch.load(actpath,map_location='cpu',weights_only=True)
            assert pres['input_token_ids']==rec['presentation']['input_token_ids'] and pres['presentation_hash']==rec['presentation']['presentation_hash']
        else:
            vectors=e.capture(inputs,pres['anchors']);li=e.depths[3];patch=(li,pres['anchors']['P_CONTEXT_END'],vectors[li]['P_CONTEXT_END'])
            gen=e.generate(inputs);cached=e.reference(inputs,cache=True);noop=e.generate(inputs,patch,readonly=True);selfr=e.generate(inputs,patch)
            ok=gen['output_token_ids']==cached['output_token_ids']==noop['output_token_ids']==selfr['output_token_ids']
            actpath.parent.mkdir(parents=True,exist_ok=True);e.torch.save(vectors,actpath)
            rec=dict(request_id=rid,request_hash=r['model_independent_request_hash'],presentation=pres,baseline=gen,cached=cached,noop=noop,self_patch=selfr,
                normalized=normalize(gen['raw_response'],r['schema']),equivalence_pass=ok,activations=entry(actpath),runtime_lock=entry(i1/'manifest/RUNTIME_LOCK.json'))
            save(path,rec)
        baseline_cache[rid]=rec;activation_cache[rid]=vectors
        return inputs,pres,rec,vectors
    for case in cases:
        if case['invalid_or_null_conditions']:
            # Retain the originally qualified cohort label but do not turn parser failure into valid rescue.
            eligibility='ORIGINAL_INTERFACE_NULL_OR_INVALID_SEPARATE'
        else:eligibility='HISTORICAL_VALID_COHORT'
        ws=windows or [dict(depth=d,anchor=an) for d in range(8) for an in ['P_CONTEXT_END','P_A1_END','P_A2_END','P_QUERY']]
        queries=['S2'] if a.stage=='localize' else ['S2','S0','PROTECTED']
        for query in queries:
            rid=case['requests'][query]['BASE'];inputs,pres,base,vec=baseline(rid)
            donors=[('INFORMATIVE_S0',rid,case['requests'][query]['INFORMATIVE_S0']),('SAME_VALUE_SHAM',rid,case['requests'][query]['SAME_VALUE_SHAM']),
                    ('SUCCESS_DONOR',rid,case['success_donor_requests'].get(query))]
            if a.stage=='selected' and query=='S2' and case['cohort'] in ['A','B']:
                if case['split']=='LOCALIZE':donors=[]  # Existing LOCALIZE primary responses are reused, not regenerated.
                donors.append(('REVERSE_B01_TO_B05',case['requests'][query]['INFORMATIVE_S0'],case['requests'][query]['BASE']))
            for kind,rid,did in donors:
                inputs,pres,base,vec=baseline(rid)
                din,dp,db,dv=baseline(did) if did else (None,None,None,None)
                if din is not None:del din
                for window in ws:
                    depth,anchor=window['depth'],window['anchor'];li=e.depths[depth]
                    tid='i1_'+digest([RUN,a.stage,case['case_id'],query,kind,depth,anchor])[:24];path=dest/'trials'/(tid+'.json')
                    if path.exists():metrics.append(dict(trial_id=tid,status=load(path)['status'],raw=entry(path)));continue
                    t=dict(trial_id=tid,case_id=case['case_id'],world_cluster_id=case['world_cluster_id'],split=case['split'],cohort=case['cohort'],
                        eligibility=eligibility,query=query,donor_kind=kind,recipient=rid,donor=did,depth=depth,relative_depth=e.config['relative_depths'][depth],layer=li,anchor=anchor,
                        recipient_position=pres['anchors'][anchor],donor_position=dp['anchors'][anchor] if dp else None,
                        baseline_ref=entry(dest/'baselines'/(rid+'.json')),donor_baseline_ref=entry(dest/'baselines'/(did+'.json')) if did else None)
                    reason='NO_QUALIFIED_SUCCESS_DONOR' if did is None else 'ENGINE_EQUIVALENCE_UNRESOLVED' if not base['equivalence_pass'] or not db['equivalence_pass'] else None
                    if reason:r=dict(trial=t,status='NOT_RUN_'+reason)
                    else:
                        patch=(li,pres['anchors'][anchor],dv[li][anchor]);response=e.generate(inputs,patch)
                        # Full candidate strings scored ONLY after free generation. Never inserted in the prompt.
                        value={'S2':case['s2'],'S0':case['program']['s0'],'PROTECTED':case['protected']}[query]
                        dcase=bycase[case['success_donor_case']] if kind=='SUCCESS_DONOR' else case
                        dvalue={'S2':dcase['s2'],'S0':dcase['program']['s0'],'PROTECTED':dcase['protected']}[query]
                        old=case['old_wrong_prediction'].get('value')
                        values=[value,old,case['program']['s0'],case['s1'],dvalue,None]
                        answers=list(dict.fromkeys(json.dumps({'value':v},separators=(',',':')) for v in values))
                        scpath=dest/'candidate_baselines'/(digest([rid,answers])+'.json')
                        if not scpath.exists():save(scpath,e.score(inputs,answers))
                        before=load(scpath);after=e.score(inputs,answers,patch)
                        r=dict(trial=t,status='RETURNED',response=response,normalized=normalize(response['raw_response'],reqs[rid]['schema']),
                            candidate_scores=dict(unpatched=before,patched=after),score_only_values=dict(correct=value,original_wrong=old,s0=case['program']['s0'],s1=case['s1'],donor_final=dvalue),
                            original_baseline_valid=base['normalized']['normalized']['status']=='VALID',activation=entry(dest/'activations'/(did+'.pt')))
                    save(path,r);metrics.append(dict(trial_id=tid,status=r['status'],raw=entry(path)))
            del inputs
        # CPU activation cache bounded to current case; retained artifacts allow deterministic reuse.
        baseline_cache.clear();activation_cache.clear();e.pipe.image_cache.clear()
        print(json.dumps(dict(stage=a.stage,shard=sid,case=case['case_id'],trials=len(metrics),seconds=time.monotonic()-started)),flush=True)
    save(dest/'RAW_RESPONSE_INDEX.jsonl',metrics,'jsonl')
    save(dest/'EXECUTION_ACCEPTANCE.json',dict(status='COMPLETE_WITH_EXPLICIT_TECHNICAL_GAPS' if any(r['status']!='RETURNED' for r in metrics) else 'COMPLETE',
        planned=len(metrics),returned=sum(r['status']=='RETURNED' for r in metrics),not_run=sum(r['status']!='RETURNED' for r in metrics),
        elapsed_seconds=time.monotonic()-started,forward_count=e.forward_count,generations=e.generations,patched_generations=e.patched_generations,
        peak_memory_bytes=[e.torch.cuda.max_memory_allocated(i) for i in range(e.torch.cuda.device_count())],
        index=entry(dest/'RAW_RESPONSE_INDEX.jsonl'),runtime_lock=entry(i1/'manifest/RUNTIME_LOCK.json'),job_id=os.environ['SLURM_JOB_ID']))
if __name__=='__main__':main()
