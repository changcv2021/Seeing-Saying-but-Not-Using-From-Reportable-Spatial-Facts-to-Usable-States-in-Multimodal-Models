"""Build proof-grounded train/dev supervision, recording every unsupported item.

Never opens test gold or historical model predictions. Never imputes hidden states.
"""
from collections import Counter,defaultdict
import re,sys,time
from common import *
from state_schema import *

sys.path.insert(0,str(REPO/'src'))
sys.path.insert(0,str(ROOT/'environment/proof_overlay'))
from spaceconflict.generation.language import entity_description,_context_forms
from spaceconflict.generation.verification import independent_label
from spaceconflict.l4_three_part.engine_a import execute_transition_a
from spaceconflict.l4_three_part.checker_b import check_transition_b
from spaceconflict.l4_three_part.controlled import verify_controlled_pair
from spaceconflict.hypo3d_l4.verification import verify_count_pair_accessibly

def ref(path):return dict(path=str(path),sha256=sha(path))
def atom_text(f,labels=None):
    labels=labels or {};s=labels.get(f['subject'],entity_description(f['subject']))
    o=labels.get(f.get('object'),entity_description(f['object']) if f.get('object') else '')
    pred=f['predicate'];v=f.get('value');neg=f.get('polarity','positive')!='positive'
    relations={'LEFT_OF':'is left of','RIGHT_OF':'is right of','ABOVE':'is above','BELOW':'is below',
               'FRONT_OF':'is in front of','BEHIND':'is behind','BEFORE':'appears before','AFTER':'appears after'}
    if pred in relations:return f'{s} {"does not satisfy: " if neg else ""}{relations[pred]} {o}'
    if pred=='COUNT':return f'the count of {s} is {v}'
    if pred in ('VISIBLE_IN_FRAME','EXISTS_IN_WORLD'):return f'{s} {"is" if v is not False and not neg else "is not"} {"visible" if pred=="VISIBLE_IN_FRAME" else "present"}'
    if pred=='SAME_INSTANCE':return f'{s} and {o} {"are" if v else "are not"} the same instance'
    raise ValueError('UNSUPPORTED_FACT_REALIZER:'+pred)

def state_for(f,labels=None,frame=None):
    labels=labels or {};ents=[]
    for key in ('subject','object'):
        value=f.get(key)
        if value:
            label=labels.get(value,entity_description(value))
            if label.startswith('hypo3d:'):raise ValueError('MISSING_NATURAL_ENTITY_GROUNDING')
            ents.append(label)
    pred=f['predicate']
    if pred in RELATION_VARIABLES:
        if f.get('polarity','positive')!='positive':raise ValueError('NEGATIVE_RELATION_NOT_CANONICAL_COMPLEMENT')
        variable=RELATION_VARIABLES[pred];value=pred
    elif pred in VALUE_VARIABLES:
        variable=VALUE_VARIABLES[pred];value=f.get('value')
        if variable=='visibility' and value is None:value=f.get('polarity','positive')=='positive'
    else:raise ValueError('UNSUPPORTED_CANONICAL_PREDICATE:'+pred)
    state=dict(entities=ents,variable=variable,value=value)
    frame=frame or f.get('context',{}).get('reference_frame')
    if frame:state['frame']=frame
    return canonicalize_state(state)

def query_for(state,context='',intervention='',stage='OBSERVED'):
    out=(context+'\n' if context else '')+'All supplied images are original visual evidence.\n'
    if intervention:out+='Hypothetical intervention: '+intervention+'\n'
    out+='Report '+stage+' state for entities '+json.dumps(state['entities'])+', variable '+state['variable']+'.\n'
    if 'frame' in state:out+='Use reference frame '+state['frame']+'.\n'
    out+='Return only <STATE> with fields entities, variable, optional frame, value in that order, using JSON values. At most 512 output tokens.'
    return out

def main():
    a=cli(__doc__).parse_args();root=a.run_root;out=root/'supervision_v2'
    if a.dry_run:print(str(out));return
    compute()
    if (out/'MANIFEST.json').exists():
        if a.resume:print((out/'MANIFEST.json').read_text());return
        raise FileExistsError(out/'MANIFEST.json')
    if not read(root/'SPLIT_AUDIT.json')['status'].startswith('PASS'):raise ValueError('SPLIT_GATE')
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(MODEL,local_files_only=True)
    source_paths=[REPO/'release/production_available_v10/pairs.jsonl',REPO/'l4/v3_3/release/pairs.l4_three_part_v3.jsonl',
                  REPO/'release/production_available_v10/unknown_challenge.jsonl',REPO/'l4/v3_3/release/unknown_challenge.l4_v3.jsonl']
    pairs={r['pair_id']:r for p in source_paths[:2] for r in rows(p)}
    unknowns={r['sample_id']:r for p in source_paths[2:] for r in rows(p)}
    needed={r.get('pair_id') for split in ('train','dev') for r in rows(root/'data'/split/'requests.jsonl')}
    # Release intentionally omits style/alias metadata needed by the original parser.
    # Recover it by EXACT public-text matching from accepted construction artifacts.
    source_index={}
    for path in sorted((REPO/'candidates/auto_accepted').glob('pairs.*.jsonl')):
        for original in rows(path):
            pid=original.get('pair_id')
            if pid not in needed or pid not in pairs:continue
            candidates={}
            for side in ('supported','contradictory'):
                claim=pairs[pid][side+'_claim'];pool=original.get(side+'_candidates',[])+[original.get(side+'_claim',{})]
                matches=[c for c in pool if c.get('natural_text')==claim.get('natural_text') and 'style_family' in c]
                if matches:candidates[side]={k:matches[0][k] for k in ('natural_text','style_family','entity_aliases','entity_declaration') if k in matches[0]}
            if len(candidates)==2 and pid not in source_index:
                source_index[pid]=dict(candidates=candidates,path=path,artifacts=original.get('artifacts',{}))
        print(json.dumps(dict(source_index=len(source_index),file=str(path))),flush=True)
    # Index names only; read relevant evidence files once per pair.
    certs=defaultdict(list);evidence=defaultdict(list)
    for path in sorted((REPO/'certificates').glob('*/*/*.json')):certs[path.stem].append(path)
    for path in sorted((REPO/'evidence_subgraphs').glob('*/*/*.json')):evidence[path.stem].append(path)
    native_path=REPO/'transition_micrographs/hypo3d_l4_v2_official_referit3d_fusion_v2_7/prestates.count_v2.jsonl'
    native={(r['scene_id'],r['change_id'],r['question_id']):r for r in rows(native_path)}
    pair_cache={};hash_cache={};receipts=[];rejects=[];state_rejects=[];summary={}
    def source_ref(path):
        if str(path) not in hash_cache:hash_cache[str(path)]=ref(path)
        return hash_cache[str(path)]
    def pair_proof(pair):
        pid=pair['pair_id']
        if pid in pair_cache:return pair_cache[pid]
        if pair.get('validation',{}).get('final_status')!='AUTO_ACCEPTED':raise ValueError('SOURCE_NOT_AUTO_ACCEPTED')
        level=pair.get('level') or pair['task']['level'];labels={};states=[]
        if level!='L4':
            original=source_index.get(pid)
            if original is None:raise ValueError('EXACT_RELEASE_REALIZATION_NOT_FOUND')
            candidates=[]
            for ep in evidence.get(pid,[]):
                cp=REPO/'certificates'/ep.relative_to(REPO/'evidence_subgraphs')
                if not cp.exists():continue
                expected=original['artifacts'].get(str(ep.relative_to(REPO)))
                if expected and sha(ep)!=expected.removeprefix('sha256:'):raise ValueError('SOURCE_EVIDENCE_HASH_MISMATCH')
                e=read(ep);c=read(cp);rules={n['id'].removeprefix('rule:') for n in c.get('proof_nodes',[]) if n.get('type') in ('RULE','TRANSITION_RULE')}
                results={side:independent_label(candidate=original['candidates'][side],entity_graph=pair[side+'_claim']['normalized'],world_facts=e['facts'],authorized_rule_ids=rules)
                         for side in ('supported','contradictory')}
                if results['supported']['label']=='SUPPORTED' and results['contradictory']['label']=='CONTRADICTORY':candidates.append((ep,cp,e,c,results))
            if not candidates:raise ValueError('SOURCE_EVIDENCE_REPLAY_UNAVAILABLE')
            ep,cp,e,c,results=candidates[0]
            if len({digest(x[2]['facts']) for x in candidates})>1:raise ValueError('AMBIGUOUS_EVIDENCE_VERSION')
            facts={f['fact_id']:f for f in e['facts']};claims=pair['supported_claim'];ctx=claims['normalized']['context']
            context=_context_forms(ctx)[0]
            used=sorted(set(results['supported']['evidence_fact_ids']+results['contradictory']['evidence_fact_ids']))
            for fid in used:
                st=state_for(facts[fid]);states.append(dict(state=st,stage='OBSERVED',query=query_for(st,context),fact_ids=[fid]))
            # A compositional state target comes from the accepted normalized conclusion,
            # only after source-premise replay proved it. Not an invented intermediate chain.
            for atom in claims['normalized']['atoms']:
                st=state_for(atom,frame=ctx.get('reference_frame'))
                states.append(dict(state=st,stage='OBSERVED',query=query_for(st,context),fact_ids=results['supported']['evidence_fact_ids']))
            reasons={side:'; '.join(atom_text(facts[fid]) for fid in results[side]['evidence_fact_ids'])+'. '
                          +('These source-grounded facts entail the claim.' if side=='supported' else 'These source-grounded facts refute the claim.')
                     for side in ('supported','contradictory')}
            record=dict(reasons=reasons,states=states,source_refs=[source_ref(ep),source_ref(cp),source_ref(original['path'])],
                        fact_ids=used,rule_ids=sorted(rules),proof_status='INDEPENDENT_LABEL_REPLAY_PASS')
        elif pair.get('l4_origin')=='BENCHMARK_CONTROLLED':
            pre=pair['pre_state_reference']['facts'];action=pair['intervention']
            ea=execute_transition_a(pre,action);eb=check_transition_b(pre,action)
            if ea['status']!='PASS' or eb['status']!='PASS' or ea['post_facts']!=eb['post_facts']:raise ValueError('CONTROLLED_REPLAY_FAIL')
            cv=verify_controlled_pair(dict(pre_facts=pre,action=action,family=action['family'],dependency_type=pair['dependency_type']),
                pair['supported_claim'],pair['contradictory_claim'])
            if cv['status']!='PASS':raise ValueError('CONTROLLED_CLAIM_REPLAY_FAIL:'+','.join(cv['errors']))
            for side in ('supported','contradictory'):
                cg=pair[side+'_claim']['graph']
                for k in ('subject','object'):
                    if cg.get(k) and cg.get(k+'_label'):labels[cg[k]]=cg[k+'_label']
            context='Use the supplied original scene and its declared reference frame.';intervention=pair['model_input']['intervention_text']
            for stage,ff in [('S0',pre),('S1',ea['post_facts'])]:
                for f in ff:
                    try:st=state_for(f,labels,action.get('parameters',{}).get('reference_frame'))
                    except ValueError as exc:
                        state_rejects.append(dict(pair_id=pid,stage=stage,fact=f,reason=str(exc),status='STATE_UNAVAILABLE'))
                        continue
                    states.append(dict(state=st,stage=stage,query=query_for(st,context,intervention if stage=='S1' else '',stage),fact_ids=[f.get('fact_id')]))
            initial='; '.join(atom_text(f,labels) for f in pre if not str(labels.get(f['subject'],f['subject'])).startswith('hypo3d:'))
            post=pair['supported_claim']['graph'];post_text=atom_text(post,labels)
            reason='Initially, '+initial+'. Apply the stated action: '+intervention+' The deterministic updated state is: '+post_text+'. '
            record=dict(reasons={'supported':reason+'This agrees with the claim.','contradictory':reason+'This conflicts with the claim.'},states=states,
                        source_refs=[source_ref(source_paths[1])],fact_ids=[f.get('fact_id') for f in pre],rule_ids=[action['family']],
                        proof_status='TWO_INDEPENDENT_TRANSITION_ENGINES_PASS',source_pre_facts=pre,source_post_facts=ea['post_facts'])
        elif level=='L4' and pair['supported_claim']['graph']['predicate']=='COUNT':
            source=pair.get('source',{});key=(source.get('scene_id'),source.get('change_id'),source.get('question_id'))
            if key not in native:raise ValueError('NATIVE_PRESTATE_NOT_FOUND')
            b=native[key]
            check=verify_count_pair_accessibly(pre_state_subgraph=b['pre_state_subgraph'],accessible_transition=b['accessible_transition'],
                supported_claim=pair['supported_claim']['graph'],contradictory_claim=pair['contradictory_claim']['graph'],necessary_pre_fact_ids=b['necessary_pre_fact_ids'])
            if check['status']!='PASS':raise ValueError('NATIVE_ACCESSIBLE_REPLAY_FAIL')
            pre=b['pre_state_subgraph']['facts'];post=pair['supported_claim']['graph'];intervention=pair['model_input']['intervention_text']
            for stage,ff in [('S0',pre),('S1',[post])]:
                for f in ff:
                    st=state_for(f);states.append(dict(state=st,stage=stage,query=query_for(st,'Whole original scene.',intervention if stage=='S1' else '',stage),fact_ids=[f.get('fact_id')]))
            reason='Initially, '+atom_text(pre[0])+'. Apply the stated intervention: '+intervention+' Updating that count gives '+atom_text(post)+'. '
            record=dict(reasons={'supported':reason+'This agrees with the claim.','contradictory':reason+'This conflicts with the claim.'},states=states,
                        source_refs=[source_ref(native_path),source_ref(source_paths[1])],fact_ids=b['necessary_pre_fact_ids'],
                        rule_ids=[b['accessible_transition']['rule_id']],proof_status='ACCESSIBLE_NATIVE_TRANSITION_REPLAY_PASS')
        else:raise ValueError('L4_POST_ORACLE_ONLY_NO_ACCESSIBLE_TRANSITION_PROOF')
        # Unique auxiliary tasks; never label single-step post-state as S2.
        record['states']=list({digest(x):x for x in record['states']}.values());pair_cache[pid]=record;return record
    for split in ('train','dev'):
        gg={r['sample_id']:r for r in rows(root/'data'/split/'private_gold.jsonl')}
        aa=[];cc=[];ss=[]
        for index,r in enumerate(rows(root/'data'/split/'requests.jsonl')):
            if a.limit and index>=a.limit:break
            g=gg[r['sample_id']];base=dict(sample_id=r['sample_id'],pair_id=r.get('pair_id'),level=r['level'],split=split,
                underlying_world_id=g['underlying_world_id'],global_world_id=g['global_world_id'],request=r)
            aa.append(dict(base,target='{"label":'+json.dumps(g['gold']),end_turn=False,loss_scope='LABEL_PREFIX_ONLY_NO_CONFIDENCE_NO_REASON_NO_EOS'))
            try:
                if g['gold']=='UNKNOWN':
                    u=unknowns[r['sample_id']];certificate=None;cp=None
                    for path in certs.get(r['sample_id'],[]):
                        candidate=read(path)
                        if candidate.get('satisfiable_with_claim') and candidate.get('satisfiable_with_negation'):certificate=candidate;cp=path;break
                    if certificate is None and u.get('validation',{}).get('satisfiable_with_claim') and u['validation'].get('satisfiable_with_negation'):certificate=u;cp=source_paths[3]
                    if certificate is None:raise ValueError('UNKNOWN_WITNESS_CERTIFICATE_UNAVAILABLE')
                    gaps=certificate.get('missing_decisive_evidence') or [certificate.get('unknown_reason','necessary decisive evidence')]
                    rationale='The accessible input omits '+', '.join(str(x).lower().replace('_',' ') for x in gaps)+'. Both the claim and its negation remain consistent with the available evidence; therefore the claim is not determined.'
                    proof=dict(source_refs=[source_ref(cp)],fact_ids=[],rule_ids=['EVIDENCE_UNDERDETERMINATION'],proof_status='SOURCE_TWO_WITNESS_CERTIFICATE')
                else:
                    pair=pairs[g['pair_id']];proof=pair_proof(pair)
                    rationale=proof['reasons']['supported' if g['gold']=='SUPPORTED' else 'contradictory']
                    if g['gold']=='SUPPORTED':
                        for k,st in enumerate(proof['states']):
                            target=serialize_state(st['state']);tokens=len(tokenizer.encode(target,add_special_tokens=False))+1
                            if tokens>512:raise ValueError('STATE_TARGET_TOO_LONG')
                            ss.append(dict(base,aux_id=r['sample_id']+':state:'+str(k),target=target,target_tokens=tokens,end_turn=True,
                                task_prompt=st['query'],stage=st['stage'],state=st['state'],fact_ids=st['fact_ids'],source_refs=proof['source_refs']))
                target=rationale+'\nAnswer: '+g['gold'];tokens=len(tokenizer.encode(target,add_special_tokens=False))+1
                if tokens>512:raise ValueError('COT_TARGET_TOO_LONG')
                task_prompt=((r.get('media_context','')+'\n') if r.get('media_context') else '')
                if r.get('intervention_text'):task_prompt+='Hypothetical intervention: '+r['intervention_text']+'\n'
                task_prompt+='Spatial claim: '+r['claim_text']+'\nExplain the evidence and applicable spatial reasoning, then end with Answer: SUPPORTED, CONTRADICTORY, or UNKNOWN. At most 512 output tokens.'
                cc.append(dict(base,target=target,target_tokens=tokens,end_turn=True,task_prompt=task_prompt,source_refs=proof['source_refs']))
                receipts.append(dict(sample_id=r['sample_id'],split=split,level=r['level'],proof_status=proof['proof_status'],
                    source_refs=proof['source_refs'],fact_ids=proof['fact_ids'],rule_ids=proof['rule_ids']))
            except (ValueError,KeyError) as exc:rejects.append(dict(sample_id=r['sample_id'],split=split,level=r['level'],reason=str(exc),status='COT_UNAVAILABLE',answer_retained=True))
            if index%500==0:print(json.dumps(dict(split=split,processed=index,answer=len(aa),cot=len(cc),states=len(ss),rejects=len(rejects))),flush=True)
        for name,data in [('answer',aa),('cot',cc),('state',ss)]:write(out/split/(name+'.jsonl'),data,True)
        summary[split]=dict(answer=len(aa),cot=len(cc),state=len(ss),cot_same_pool_complete=len(aa)==len(cc),
            state_by_level=dict(Counter(x['level'] for x in ss)),state_by_stage=dict(Counter(x['stage'] for x in ss)))
    write(out/'rejects.jsonl',rejects,True);write(out/'proof_receipts.jsonl',receipts,True)
    write(out/'state_rejects.jsonl',state_rejects,True)
    manifest=dict(status='PREPARED_WITH_EXPLICIT_COVERAGE',counts=summary,reject_counts=dict(Counter(r['reason'] for r in rejects)),
        source_files=list(hash_cache.values()),test_opened=False,partial=bool(a.limit),state_reject_count=len(state_rejects),
        cot_training_gate='PASS' if all(x['cot_same_pool_complete'] for x in summary.values()) else 'BLOCKED_STRICT_SAME_POOL_INCOMPLETE',
        s2_from_single_step_forbidden=True,job_id=os.environ['SLURM_JOB_ID'],code_sha256=sha(__file__))
    write(out/'MANIFEST.json',manifest);print(json.dumps(manifest,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
