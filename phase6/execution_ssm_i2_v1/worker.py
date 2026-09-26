"""Independent technical gates, then fixed source-selected 9B I2 trials; no tuning."""
import time
from common_i2 import *
from engine import Engine
def technical(e,dest):
    requests=list(rows(I2/'public_inputs/technical.jsonl'));records=[];fail=[];maxlp=0.;maxrel=0.
    for i in range(4):
        pair=[r for r in requests if r['case']==i];r=next(r for r in pair if r['variant']=='recipient');d=next(r for r in pair if r['variant']=='donor')
        ri,rp=e.process(r);di,dp=e.process(d);rc=e.capture(ri,rp['anchors']);dc=e.capture(di,dp['anchors'])
        li=e.depths[3];an='P_CHECKPOINT';patch=(li,rp['anchors'][an],dc[li][an]);selfpatch=(li,rp['anchors'][an],rc[li][an])
        before=e.generate(ri,cap=32);ref=e.reference(ri,cap=32);fullref=e.reference(ri,cache=False,cap=32)
        read=e.generate(ri,selfpatch,cap=32,readonly=True);selfgen=e.generate(ri,selfpatch,cap=32)
        changed=e.generate(ri,patch,cap=32);changedref=e.reference(ri,cache=False,patch=patch,cap=32)
        # Altered execution must not contaminate subsequent unpatched execution.
        after=e.generate(ri,cap=32)
        short=e.generate(ri,cap=2)
        assert len(short['output_token_ids'])<=2
        answers=['{"value":0}','{"value":12}','{"value":null}']
        scores=[]
        for mode,p in [('BASE',None),('PATCHED',patch)]:
            batch=e.score(ri,answers,p);sequential=e.score(ri,answers,p,True)
            diff=max(abs(x-y) for a,b in zip(batch,sequential) for x,y in zip(a['token_logprobs'],b['token_logprobs']));maxlp=max(maxlp,diff)
            scores.append(dict(mode=mode,batch=batch,sequential=sequential,max_token_lp_difference=diff))
        # Shared prefix cannot see the different note that comes after ACTION_1.
        assert rp['input_token_ids'][:rp['anchors']['P_A1']+1]==dp['input_token_ids'][:dp['anchors']['P_A1']+1]
        rel=[]
        for layer in e.depths:
            a,b=rc[layer]['P_A1'].float(),dc[layer]['P_A1'].float()
            rel.append(float((a-b).square().mean().sqrt()/(a.square().mean().sqrt()+1e-8)))
        maxrel=max(maxrel,*rel)
        checks=dict(reference_cached=before['output_token_ids']==ref['output_token_ids'],reference_full=before['output_token_ids']==fullref['output_token_ids'],
            readonly=before['output_token_ids']==read['output_token_ids'],self=before['output_token_ids']==selfgen['output_token_ids'],
            changed_full_replay=changed['output_token_ids']==changedref['output_token_ids'],ab_isolation=before['output_token_ids']==after['output_token_ids'])
        if not all(checks.values()):fail.append(dict(case=i,checks=checks))
        records.append(dict(case=i,recipient=rp,donor=dp,layer=li,baseline=before,reference=ref,full_reference=fullref,readonly=read,self=selfgen,
            patched=changed,patched_reference=changedref,repeat_baseline=after,hard_cap_test=short,checks=checks,candidate_scores=scores,prefix_relative_rms=rel))
        save(dest/f'case_{i}.json',records[-1]);print(json.dumps(dict(stage='I2_TECH',case=i,checks=checks)),flush=True)
        del ri,di,rc,dc;e.pipe.image_cache.clear()
    if maxlp>.5:fail.append('CANDIDATE_REPLAY_LP_ABOVE_CEILING')
    if maxrel>.01:fail.append('PREFIX_CAUSAL_INVARIANCE_FAILED')
    save(dest/'TOLERANCE_LOCK.json',dict(calibrated_on_independent_setup=True,max_observed_lp=maxlp,max_observed_prefix_relative_rms=maxrel,
        candidate_lp_tolerance=min(.5,max(.02,maxlp*2)),prefix_relative_rms_tolerance=min(.01,max(.0001,maxrel*2)),failures=fail))
    result=dict(status='PASS' if not fail else 'FAILED_ENGINE_EQUIVALENCE',scope='FULL_REPLAY_BLOCK_OUTPUT_INTERVENTIONS_ONLY_NO_CACHE_OPTIMIZATION',
        failures=fail,config=e.config,forward_count=e.forward_count,generations=e.generations,patched_generations=e.patched_generations,
        cases=[entry(dest/f'case_{i}.json') for i in range(4)],tolerance=entry(dest/'TOLERANCE_LOCK.json'),gold_audit=e.guard,
        peak_gpu_bytes=[e.torch.cuda.max_memory_allocated(i) for i in range(e.pipe.mc['gpus'])],job_id=os.environ['SLURM_JOB_ID'])
    save(dest/'ACCEPTANCE.json',result)
    if fail:raise ValueError('I2_ENGINE_EQUIVALENCE_FAILED')
def core(e,dest,shard):
    gate=load(I2/'technical/qwen35_9b/ACCEPTANCE.json');assert gate['status']=='PASS';check(gate['tolerance'])
    requests={r['request_id']:r for r in rows(I2/'public_inputs/requests.jsonl')}
    trials=[r for r in rows(I2/'public_inputs/trials.jsonl') if r['shard']==shard];cache={};present={};baseline={};caps={};qualified={}
    # Existing processor records must agree exactly; cached historical answers are NOT used as the new baseline.
    old=load(ROOT/'batches/B2/review/qwen35_9b/PROCESSOR_ACCEPTANCE.json');check(old['records'])
    expected={r['request_id']:r for r in rows(old['records']['path'])}
    from interface_repair_v3.adapter import normalize
    def get(rid):
        if rid not in cache:
            inputs,pres=e.process(requests[rid]);want=expected[rid]
            assert (pres['input_token_ids'],pres['presentation_hash'],pres['rendered_prompt_sha256'])==(want['input_token_ids'],want['presentation_hash'],want['rendered_prompt_sha256'])
            cache[rid]=inputs;present[rid]=pres;caps[rid]=e.capture(inputs,pres['anchors'])
            bp=dest/'baselines'/(rid+'.json')
            if bp.exists():rec=load(bp)
            else:
                gen=e.generate(inputs);ref=e.reference(inputs)
                rec=dict(request_id=rid,presentation=pres,baseline=gen,reference_cached=ref,
                    normalized=normalize(gen['raw_response'],requests[rid]['schema']),status='PASS' if gen['output_token_ids']==ref['output_token_ids'] else 'ENGINE_EQUIVALENCE_UNRESOLVED')
                save(bp,rec)
            baseline[rid]=rec
        return cache[rid]
    returned=[];started=time.monotonic()
    for n,t in enumerate(trials):
        target=dest/'trials'/(t['trial_id']+'.json')
        if target.exists():returned.append(entry(target));continue
        ri=get(t['recipient']);get(t['donor']);li=e.depths[t['depth']];an=t['anchor'];pos=present[t['recipient']]['anchors'][an]
        stamp=(t['recipient'],li,an)
        if stamp not in qualified:
            sp=dest/'self_checks'/(digest(stamp)+'.json')
            if sp.exists():sc=load(sp)
            else:
                selfgen=e.generate(ri,(li,pos,caps[t['recipient']][li][an]))
                sc=dict(request_id=t['recipient'],layer=li,anchor=an,response=selfgen,
                    status='PASS' if selfgen['output_token_ids']==baseline[t['recipient']]['baseline']['output_token_ids'] else 'ENGINE_EQUIVALENCE_UNRESOLVED')
                save(sp,sc)
            qualified[stamp]=sc['status']=='PASS'
        common=dict(trial=t,layer=li,layer_type=getattr(e.layers[li],'block_type',None),recipient_anchor=pos,donor_anchor=present[t['donor']]['anchors'][an],
            baseline_ref=entry(dest/'baselines'/(t['recipient']+'.json')),donor_baseline_ref=entry(dest/'baselines'/(t['donor']+'.json')),
            job_id=os.environ['SLURM_JOB_ID'],batch_size=1,cache_policy='FULL_REPLAY_EVERY_TOKEN')
        if not qualified[stamp] or any(baseline[k]['status']!='PASS' for k in (t['recipient'],t['donor'])):
            save(target,dict(common,status='NOT_RUN_ENGINE_EQUIVALENCE_UNRESOLVED'));returned.append(entry(target));continue
        vec=caps[t['donor']][li][an];recipient_vec=caps[t['recipient']][li][an]
        patch=(li,pos,vec)
        # Free response is committed before candidate strings are read for teacher forcing.
        free=dest/'free_responses'/(t['trial_id']+'.json')
        if free.exists():gen=load(free)
        else:gen=e.generate(ri,patch);save(free,gen)
        answers=t['score_only_candidate_strings'];unpatched=e.score(ri,answers);patched=e.score(ri,answers,patch)
        saved=dest/'activation_vectors'/(t['trial_id']+'.pt');saved.parent.mkdir(parents=True,exist_ok=True)
        if not saved.exists():e.torch.save(dict(donor=vec,recipient=recipient_vec,layer=li,anchor=an),saved)
        rec=dict(common,status='RETURNED',response=gen,normalized=normalize(gen['raw_response'],requests[t['recipient']]['schema']),
            candidate_scores=dict(unpatched=unpatched,patched=patched),activation=entry(saved),tensor_elements=vec.numel(),
            donor_norm=float(vec.float().norm()),recipient_norm=float(recipient_vec.float().norm()),delta_norm=float((vec.float()-recipient_vec.float()).norm()))
        save(target,rec);returned.append(entry(target))
        if n%8==0:print(json.dumps(dict(stage='I2_CORE',shard=shard,done=n+1,total=len(trials),elapsed=time.monotonic()-started)),flush=True)
    save(dest/'RAW_INDEX.json',returned)
    save(dest/'ACCEPTANCE.json',dict(status='EXECUTION_COMPLETE_WITH_EXPLICIT_NOT_RUN',trials=len(trials),raw_index=entry(dest/'RAW_INDEX.json'),
        forward_count=e.forward_count,generations=e.generations,patched_generations=e.patched_generations,gold_audit=e.guard,
        job_id=os.environ['SLURM_JOB_ID'],scientific_support='NOT_EVALUATED',elapsed=time.monotonic()-started))
def main():
    p=cli(__doc__);p.add_argument('--model',required=True);p.add_argument('--stage',choices=['technical','core'],required=True);p.add_argument('--shard',type=int)
    a=p.parse_args();c,out=setup_i2(a)
    if a.dry_run:print('I2 full-replay engine; no cached suffix after intervention');return
    verify();assert a.model in MODELS
    shard=a.shard if a.shard is not None else int(os.environ.get('SLURM_ARRAY_TASK_ID','0'))
    dest=out/'technical'/a.model if a.stage=='technical' else out/'raw'/a.model/f'shard_{shard:03}'
    if (dest/'ACCEPTANCE.json').exists():print('EXISTING_ACCEPTANCE_RETAINED');return
    if a.stage=='core':assert a.model=='qwen35_9b' and load(out/'technical'/a.model/'ACCEPTANCE.json')['status']=='PASS'
    e=Engine(c,a.model,dest)
    if a.stage=='technical':technical(e,dest)
    else:core(e,dest,shard)
if __name__=='__main__':main()
