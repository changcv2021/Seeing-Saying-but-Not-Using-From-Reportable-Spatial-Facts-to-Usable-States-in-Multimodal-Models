"""Close I2 with same-target probability contrasts; bounded technical refresh of 16 controls only."""
from collections import defaultdict,Counter
from v2_common import *
from interface_repair_v3.adapter import normalize
I2=OLD_ROOT/'i2_interchange_v1'

def analyze():
    dest=ROOT/'W2/same_target_closure';inp=I2/'reports/snapshot_8201958/ALL_RAW_RESPONSES.jsonl';table=[]
    for r in rows(inp):
        rec,g=r['record'],r['gold'];t=rec['trial'];target=g['primary_counterfactual']
        def lp(key):
            hit=[s['logprob'] for s in rec.get('candidate_scores',{}).get(key,[]) if json.loads(s['answer'])=={'value':target}]
            assert len(hit)<=1;return hit[0] if hit else None
        x,y=lp('unpatched'),lp('patched')
        pred=rec.get('normalized',{}).get('normalized',{}).get('component_values',{}).get('value')
        table.append(dict(trial_id=t['trial_id'],pair=t['base_pair_id'],depth=t['depth'],anchor=t['anchor'],control=t['control'],world_cluster_id=t['cluster_id'],
            status=rec['status'],primary_target=target,delta=y-x if x is not None and y is not None else None,
            changed_to_unrelated_value=pred not in [g['recipient_final_gold'],g['donor_final_gold'],g['donor_s1'],g['expected_counterfactual'],None] if rec['status']=='RETURNED' else None,
            candidate_target_present=x is not None and y is not None,raw_ref=entry(I2/'raw/qwen35_9b'/f'shard_{t["shard"]:03}/trials'/(t['trial_id']+'.json'))))
    primary={(r['pair'],r['depth']):r for r in table if r['control']=='PRIMARY' and r['anchor']=='P_CHECKPOINT'};groups=defaultdict(list)
    for r in table:
        if r['control'] in ['PRIMARY','SAME_DONOR_DIFFERENT_A2']:continue
        p=primary[(r['pair'],r['depth'])]
        if r['delta'] is not None and p['delta'] is not None:
            groups[r['control']].append(dict(world_cluster_id=r['world_cluster_id'],value=p['delta']-r['delta']))
    summaries=[dict(control=control,metric='PRIMARY_CHECKPOINT_MINUS_CONTROL_SAME_PRIMARY_CF_LP',**cluster_ci(v)) for control,v in sorted(groups.items())]
    csvsave(dest/'TRIAL_PROBABILITIES.csv',table);csvsave(dest/'MATCHED_CONTROL_RESULTS.csv',summaries)
    # Neither single favorable window nor uncorrected point estimate establishes a compositional mechanism.
    stable=[r for r in summaries if r['ci_low'] is not None and r['ci_low']>0]
    save(dest/'CLOSURE.json',dict(status='ANALYZED',historical_primary_untouched=True,main_384_not_rerun=True,
        decision='I2_SINGLE_TOKEN_S1_INTERCHANGE_NOT_SUPPORTED' if not stable else 'ARGMAX_UNSUPPORTED_CONTINUOUS_CONTROL_SPECIFICITY_UNRESOLVED',
        stable_positive_contrasts=stable,matched_results=entry(dest/'MATCHED_CONTROL_RESULTS.csv'),
        missing_or_unscored_candidates=sum(not r['candidate_target_present'] for r in table),source=entry(inp),
        no_expand_layers_pairs_or_anchors=True))
    print(json.dumps(load(dest/'CLOSURE.json')),flush=True)

def technical(c):
    out=ROOT/'W2/technical_followup';out.mkdir(parents=True,exist_ok=True)
    plan=[]
    for t in rows(I2/'public_inputs/trials.jsonl'):
        raw=I2/'raw/qwen35_9b'/f'shard_{t["shard"]:03}/trials'/(t['trial_id']+'.json')
        if load(raw)['status']!='RETURNED':plan.append(dict(trial=t,original=entry(raw)))
    assert len(plan)==16 and all(p['trial']['control']!='PRIMARY' for p in plan)
    save(out/'FOLLOWUP_LOCK.json',dict(status='FROZEN_BEFORE_REFRESH',code=entry(__file__),engine=entry(SPACE/'phase6/execution_ssm_i2_v1/engine.py'),
        trials=plan,rounds=1,accuracy_gate=False,no_primary_rerun=True,
        rule='One fixed cache/no-cache/noop/self/A-B-A equivalence diagnostic; unresolved contexts stay NOT_RUN. Fill only original 16 controls if all their context checks pass.'))
    reqs={r['request_id']:r for r in rows(I2/'public_inputs/requests.jsonl')}
    sys.path.insert(0,str(SPACE/'phase6/execution_ssm_i2_v1'))
    from engine import Engine
    e=Engine(c,'qwen35_9b',out);contexts={};vectors={}
    rids=sorted({p['trial'][k] for p in plan for k in ['recipient','donor']})
    for rid in rids:
        inputs,pres=e.process(reqs[rid]);vec=e.capture(inputs,pres['anchors']);li=e.depths[3];patch=(li,pres['anchors']['P_CHECKPOINT'],vec[li]['P_CHECKPOINT'])
        first=e.generate(inputs);cache=e.reference(inputs,True);fullref=e.reference(inputs,False);noop=e.generate(inputs,patch,readonly=True);selfr=e.generate(inputs,patch);second=e.generate(inputs)
        tokens=first['output_token_ids'];passed=all(r['output_token_ids']==tokens for r in [cache,fullref,noop,selfr,second])
        rec=dict(request_id=rid,presentation=pres,baseline=first,reference_cached=cache,reference_full=fullref,noop=noop,self_patch=selfr,repeat=second,
            normalized=normalize(first['raw_response'],reqs[rid]['schema']),equivalence_pass=passed)
        save(out/'contexts'/(rid+'.json'),rec);contexts[rid]=rec;vectors[rid]=vec
        print(json.dumps(dict(stage='I2_TECH_REFRESH',request=rid,pass_gate=passed,full=first['raw_response'],cached=cache['raw_response'])),flush=True)
    results=[]
    for p in plan:
        t=p['trial'];r,d=t['recipient'],t['donor'];path=out/'controls'/(t['trial_id']+'.json')
        if not contexts[r]['equivalence_pass'] or not contexts[d]['equivalence_pass']:
            rec=dict(trial=t,status='NOT_RUN_ENGINE_EQUIVALENCE_UNRESOLVED',original=p['original'])
        else:
            inputs,pres=e.process(reqs[r]);li=e.depths[t['depth']];anchor=t['anchor'];patch=(li,pres['anchors'][anchor],vectors[d][li][anchor])
            response=e.generate(inputs,patch);answers=t['score_only_candidate_strings']
            rec=dict(trial=t,status='RETURNED_FOLLOWUP_CONTROL',original=p['original'],response=response,normalized=normalize(response['raw_response'],reqs[r]['schema']),
                     candidate_scores=dict(unpatched=e.score(inputs,answers),patched=e.score(inputs,answers,patch)),
                     baseline_ref=entry(out/'contexts'/(r+'.json')),donor_baseline_ref=entry(out/'contexts'/(d+'.json')))
        save(path,rec);results.append(dict(trial_id=t['trial_id'],status=rec['status'],raw=entry(path)))
    save(out/'RAW_RESPONSE_INDEX.jsonl',results,'jsonl');save(out/'ACCEPTANCE.json',dict(status='BOUNDED_REFRESH_COMPLETE',
        counts=dict(Counter(r['status'] for r in results)),contexts=len(contexts),failed_contexts=[r for r,c in contexts.items() if not c['equivalence_pass']],
        original_results_unchanged=True,main_trials_rerun=0,engine=e.config,job_id=os.environ['SLURM_JOB_ID']))

if __name__=='__main__':
    p=cli(__doc__);p.add_argument('--stage',choices=['analyze','technical'],required=True);a=p.parse_args();c,_=context(a)
    analyze() if a.stage=='analyze' else technical(c)
