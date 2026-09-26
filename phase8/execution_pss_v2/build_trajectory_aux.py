"""Reuse frozen B1 programs as TRAIN/DEV state supervision, never as held-out tests."""
from collections import Counter,defaultdict
import sys,re
from common import *
from state_schema import *

PANEL=BASE/'sequential_state_mechanism/ssm_b1b2_20260911_v1/batches/B1/private_gold/world_panel.jsonl'

def apply_action(value,action):
    kind=action['kind'];amount=action['amount']
    if type(amount) is not int or amount<0:raise ValueError('ACTION_AMOUNT')
    if kind=='ADD':return value+amount
    if kind=='REMOVE':
        if value<amount:raise ValueError('REMOVAL_EXCEEDS_COUNT')
        return value-amount
    if kind=='NOOP':return value
    raise ValueError('UNSUPPORTED_ACTION')

def main():
    a=cli(__doc__).parse_args();root=a.run_root;out=root/'trajectory_aux_v1'
    if a.dry_run:print(out);return
    compute()
    if (out/'MANIFEST.json').exists() and a.resume:return
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(MODEL,local_files_only=True)
    group={r['global_world_id']:r['underlying_world_id'] for r in rows(root/'data/world_groups.jsonl')}
    owned={};parents=defaultdict(list)
    for split in ('train','dev'):
        for g in rows(root/'data'/split/'private_gold.jsonl'):
            world=g['underlying_world_id']
            if world in owned and owned[world]!=split:raise ValueError('SPLIT_LEAK')
            owned[world]=split;parents[world].append(g['sample_id'])
    graph_cache={};request_cache={};hashes={};samples=defaultdict(list);proofs=[];rejects=[]
    def checked_ref(ref):
        p=Path(ref['path'])
        if str(p) not in hashes:hashes[str(p)]=sha(p)
        if hashes[str(p)]!=ref['sha256'].removeprefix('sha256:'):raise ValueError('FROZEN_SOURCE_HASH_CHANGED')
        return p
    for panel in rows(PANEL):
        world=panel['world_cluster_id'];sequence=panel['sequence'];component=group.get(world)
        try:
            if component not in owned:raise ValueError('OUTSIDE_APPROVED_TRAIN_DEV_POOL')
            split=owned[component];program=panel['program'];s0=program['s0']
            s1=apply_action(s0,program['a1']);s2=apply_action(s1,program['a2'])
            if (s1,s2)!=(panel['s1'],panel['s2']):raise ValueError('PROGRAM_REPLAY_MISMATCH')
            facts={}
            for reference in panel['source_graphs']:
                path=checked_ref(reference)
                if path not in graph_cache:graph_cache[path]=read(path)
                facts.update({f['fact_id']:f for f in graph_cache[path]['facts']})
            fact=facts[panel['source_facts'][0]]
            if fact['predicate']!='COUNT' or fact['value']!=s0 or fact['context']['world_id']!=world:raise ValueError('SOURCE_S0_MISMATCH')
            path=checked_ref(panel['legacy_request_file'])
            if path not in request_cache:request_cache[path]={r['request_id']:r for r in rows(path)}
            legacy=request_cache[path][panel['legacy_request_id']]
            if legacy['world_cluster_id']!=world:raise ValueError('MEDIA_WORLD_MISMATCH')
            text=legacy['payload']['text'];media=legacy['payload']['media']
            if any(not Path(m['path']).is_file() for m in media):raise ValueError('SOURCE_MEDIA_MISSING')
            category=fact['subject'].removeprefix('class:').replace('_',' ')
            prefix=text.split('AUTHORIZED HYPOTHETICAL BRANCH')[0]
            step1=re.search(r'^STEP 1: (.+)$',text,re.M);step2=re.search(r'^STEP 2: (.+)$',text,re.M)
            if not step1 or not step2:raise ValueError('FROZEN_STEP_WORDING_MISSING')
            # The original programs and action wording are reused, not re-designed.
            for stage,value in [('S0',s0),('S1',s1),('S2',s2)]:
                query=prefix
                if stage!='S0':query+='A1 maps S0 to S1.\nACTION_1: '+step1[1]+'\n'
                if stage=='S2':query+='A2 acts on S1, not independently on S0, to produce S2.\nACTION_2: '+step2[1]+'\n'
                if stage!='S0':query+='The recorded S0 and other categories are unchanged. Only quantities are queried; do not recount occlusion after this symbolic edit.\n'
                state=dict(entities=[category],variable='count',frame=fact['context']['reference_frame'],value=value)
                query+='Report '+stage+' for entities '+json.dumps([category])+', variable count, frame '+state['frame']+'.\n'
                query+='Return only <STATE> with fields entities, variable, frame, value, in that order using JSON values. At most 512 output tokens.'
                target=serialize_state(state);nt=len(tokenizer.encode(target,add_special_tokens=False))+1
                if nt>512:raise ValueError('TARGET_TOKEN_BUDGET')
                sid='pss_trajectory_'+digest([world,sequence,stage])[:24]
                request=dict(sample_id=sid,level='L4',claim_text='',intervention_text='',media=media)
                samples[split].append(dict(sample_id=sid,aux_id=sid,level='L4',split=split,global_world_id=world,
                    underlying_world_id=component,stage=stage,sequence=sequence,state=state,request=request,
                    task_prompt=query,target=target,target_tokens=nt,end_turn=True,
                    parent_sample_ids=sorted(parents[component]),fact_ids=[fact['fact_id']],
                    source_refs=panel['source_graphs']+[panel['legacy_request_file']],
                    historically_exposed=True,usage='TRAIN_DEV_AUXILIARY_NOT_HELD_OUT_RESULT'))
            proofs.append(dict(world=world,underlying_world_id=component,split=split,sequence=sequence,program=program,
                states=[s0,s1,s2],source_fact=fact,source_panel=str(PANEL),legacy_request_id=legacy['request_id']))
        except (ValueError,KeyError) as exc:rejects.append(dict(world=world,sequence=sequence,reason=str(exc)))
    for split in ('train','dev'):write(out/split/'state.jsonl',samples[split],True)
    write(out/'proofs.jsonl',proofs,True);write(out/'rejects.jsonl',rejects,True)
    result=dict(status='PREPARED_TRAIN_DEV_ONLY',counts={s:dict(states=len(samples[s]),worlds=len({r['underlying_world_id'] for r in samples[s]}),
        stages=dict(Counter(r['stage'] for r in samples[s]))) for s in ('train','dev')},
        rejected_sequences=len(rejects),reject_reasons=dict(Counter(r['reason'] for r in rejects)),
        source_hashes=hashes,panel_sha256=sha(PANEL),test_opened=False,job_id=os.environ['SLURM_JOB_ID'],code_sha256=sha(__file__))
    write(out/'MANIFEST.json',result);print(json.dumps({k:v for k,v in result.items() if k!='source_hashes'}),flush=True)

if __name__=='__main__':main()
