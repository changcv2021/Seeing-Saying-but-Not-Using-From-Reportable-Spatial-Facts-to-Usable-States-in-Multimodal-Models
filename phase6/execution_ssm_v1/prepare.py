"""Freeze source-grounded B1, independent B2, and source-component partitions before outputs."""
import copy
import re
from collections import defaultdict,Counter
from dataclasses import asdict
from ssm_common import *
from state_contracts import Program,Action
from real_compile_v1 import runtime_files,SOURCE_IMAGES
from real_design_v1 import branch_spec,noun,question,SYSTEM,independent_facts
from coverage_supplement_v1.compile import contract
from data_continuation_v1.prepare import source_guard
from contracts import parse

COUNT=dict(kind='value',domain='count',nullable=True)
def step_text(a,category):
    if a.kind=='NOOP':return 'make no change to the counted set'
    if a.kind=='SET':return f'set the register value to exactly {a.amount}, replacing its previous value'
    return f'{a.kind.lower()} exactly {a.amount} '+('new ' if a.kind=='ADD' else 'counted ')+category
def replay(p):
    x=list(range(p.s0))
    for a,want in [(p.a1,p.s1),(p.a2,p.s2)]:
        if a.kind=='ADD':x.extend([None]*a.amount)
        elif a.kind=='REMOVE':
            for _ in range(a.amount):x.pop()
        elif a.kind=='SET':x=[None]*a.amount
        assert len(x)==want
def signature(p):
    vals=dict(S0=p.s0,S1=p.s1,S2=p.s2,A1_AMOUNT=p.a1.amount,A2_AMOUNT=p.a2.amount)
    return dict(commutes_on_this_state=p.commutes_on_this_state(),s2_equals_s0=p.s2==p.s0,s2_equals_s1=p.s2==p.s1,
        value_signature_collisions={str(v):[k for k,z in vals.items() if z==v] for v in set(vals.values()) if list(vals.values()).count(v)>1})

class Builder:
    def __init__(self,c,batch):self.c=c;self.batch=batch;self.req={};self.gold={};self.logical=[];self.panels=[]
    def emit(self,w,seq,cond,text,value,media,split,schema=None,role='NEUTRAL',target='S2',proof=None):
        schema=schema or COUNT;payload=dict(system=SYSTEM,text=text+'\nOUTPUT CONTRACT: '+contract(schema),media=media)
        rid='ssm_'+digest([self.batch,w,payload,schema])[:24]
        r=dict(request_id=rid,experiment=self.batch,condition=cond,world_cluster_id=w,split=split,
            logical_bundle_id=digest([self.batch,w]),sample_family='SOURCE_SUPPORTED_COUNT_SEQUENCE' if self.batch=='B1' else 'SYNTHETIC_SYMBOLIC_PROGRAM',
            source_type='CONTROLLED_SOURCE_EXTENSION' if self.batch=='B1' else 'SYMBOLIC_CONTROL',payload=payload,schema=schema,
            requested_tokens=512,information_role=role,target_state=target,queried_fact_id=cond,view_variant='FULL' if media else 'NO_MEDIA',
            wording='SSM_V1_FROZEN',models=MODELS,review_status='HUMAN_REVIEW_WAIVED_BY_RESEARCHER',scientific_review_grade='AUTO_ONLY_PROVISIONAL')
        r['model_independent_request_hash']=digest(r)
        g=dict(request_id=rid,world_cluster_id=w,expected=dict(value=value),proof=proof)
        if rid in self.req:
            assert self.gold[rid]['expected']==g['expected'],'DUPLICATE_INPUT_CONFLICTING_GOLD'
        else:self.req[rid]=r;self.gold[rid]=g
        assert parse(json.dumps(g['expected']),schema)['status']=='VALID'
        self.logical.append(dict(logical_id='ssml_'+digest([self.batch,w,seq,cond])[:24],world_cluster_id=w,sequence=seq,condition=cond,
            request_id=rid,split=split,execution_source='NEW_GENERATION_OR_EXACT_WITHIN_BATCH_ALIAS'))
        return rid
    def publish(self,root,refs):
        dest=root/'batches'/self.batch
        req=list(self.req.values());save(dest/'public_inputs/requests.jsonl',req,'jsonl')
        save(dest/'private_gold/request_gold.jsonl',self.gold.values(),'jsonl')
        save(dest/'private_gold/logical_manifest.jsonl',self.logical,'jsonl');save(dest/'private_gold/world_panel.jsonl',self.panels,'jsonl')
        save(dest/'public_inputs/logical_manifest.jsonl',self.logical,'jsonl')
        worlds=sorted({r['world_cluster_id'] for r in req},key=lambda w:digest([20260911,'SHARD',w]))
        n=4 if self.batch=='B1' else 2;shards=[]
        for i in range(n):
            ws=set(worlds[i::n]);rr=[r for r in req if r['world_cluster_id'] in ws];path=dest/f'public_inputs/shard_{i:03}.jsonl'
            save(path,rr,'jsonl');shards.append(dict(shard=i,worlds=sorted(ws),requests=len(rr),request_file=entry(path)))
        save(dest/'manifest/shards.json',shards)
        code=runtime_files(self.c)+[entry(p) for p in sorted(HERE.glob('*.py'))]+[entry(p) for p in sorted(HERE.glob('*.sh'))]+[entry(PACKAGE/'tools/state_contracts.py')]
        code += [entry(SWS_CODE/'coverage_supplement_v1/compile.py'),entry(SWS_CODE/'interface_repair_v3/adapter.py'),entry(SWS_CODE/'interface_repair_v2/adapter.py')]
        save(dest/'manifest/REQUEST_LOCK.json',dict(batch=self.batch,code=code,public_inputs=[entry(dest/'public_inputs/requests.jsonl'),entry(dest/'public_inputs/logical_manifest.jsonl'),entry(dest/'manifest/shards.json')]+[s['request_file'] for s in shards],
            private_inputs=[entry(dest/'private_gold'/n) for n in ('request_gold.jsonl','logical_manifest.jsonl','world_panel.jsonl')],
            source_refs=refs,models=MODELS,seed=20260911,output_cap=512,created_at=now(),human_gate=False,
            output_selection=False,source_type='SOURCE_SUPPORTED_CONTROLLED_QUANTITY_NOT_NATIVE_GEOMETRIC_UPDATE' if self.batch=='B1' else 'SYMBOLIC_ONLY'))
        acc=dict(status='FROZEN_NOT_INFERRED',batch=self.batch,worlds=len(worlds),physical_requests_per_model=len(req),
            logical_conditions_per_model=len(self.logical),condition_counts=dict(Counter(x['condition'] for x in self.logical)),
            source_refs=refs,request_lock=entry(dest/'manifest/REQUEST_LOCK.json'))
        save(dest/'reports/COMPILE_ACCEPTANCE.json',acc);print(json.dumps(acc),flush=True)
        return acc

def main():
    a=cli(__doc__).parse_args();c,root=context(a)
    if a.dry_run:print('Compile all eligible B1/B2 without reading predictions.');return
    import unittest,io
    suite=unittest.defaultTestLoader.discover(str(PACKAGE/'tests'));buf=io.StringIO()
    tested=unittest.TextTestRunner(stream=buf,verbosity=2).run(suite)
    save(root/'preparation'/('contract_tests_'+os.environ['SLURM_JOB_ID']+'.txt'),buf.getvalue(),'text')
    if not tested.wasSuccessful():raise ValueError('PACKAGE_CONTRACT_TEST_FAILED')
    if (root/'manifest/PANEL_LOCK.json').exists():
        for b in ('B1','B2'):
            lock=load(root/'batches'/b/'manifest/REQUEST_LOCK.json')
            for ref in lock['code']+lock['public_inputs']+lock['private_inputs']:check(ref)
        print('EXACT_FROZEN_PANEL_REUSED');return
    guard=source_guard()
    source=Path(load(SWS_CODE/'config_auto_v2.json')['root'])/'batches/e5_sequence_supplement_v1_20260910'
    slock=load(source/'manifest/REQUEST_LOCK.json')
    for ref in slock['public_inputs']+slock['private_inputs']:check(ref)
    panel=list(rows(source/'private_gold/world_panel.jsonl'));assert len(panel)==80
    oldreq={r['request_id']:r for r in rows(source/'public_inputs/requests.jsonl')}
    oldgold={r['request_id']:r for r in rows(source/'private_gold/request_gold.jsonl')}
    matches=list(rows(source/'private_gold/matched_structure.jsonl'))
    # Source graph, common capture IDs and all shared media connect worlds before partitioning.
    parent={p['world_cluster_id']:p['world_cluster_id'] for p in panel};owner={};media_audit=[];reject=[];qualified=[]
    def find(w):
        while parent[w]!=w:w=parent[w]
        return w
    def union(x,y):parent[find(y)]=find(x)
    from PIL import Image,ImageOps
    for p in panel:
        w=p['world_cluster_id']
        try:
            assert len(p['facts'])==2 and independent_facts(*p['facts'])
            for f,ref in zip(p['facts'],p['source_graphs']):
                check(ref);assert f in load(ref['path'])['facts'];assert f['predicate']=='COUNT' and f['context']['scope']=='reference_frame'
                assert f['provenance']['origin_type']=='QA_DIRECT' and f['context']['world_id']==w
                for key in [f['context']['world_id'],*f['grounding']['frame_roles'].values()]:
                    if key in owner:union(w,owner[key])
                    owner[key]=w
            for m in p['media']:
                path=Path(m['path']);want=m['sha256'].removeprefix('sha256:')
                if not path.is_file():
                    loc=p['facts'][0]['grounding']['frame_roles'][m['role']];alt=SOURCE_IMAGES/loc
                    if not alt.is_file() or sha(alt)!=want:raise ValueError('SOURCE_MEDIA_MISSING:'+str(path))
                    # Do not alter historical paths: record recoverable alternate; replay needs explicit new protocol.
                    raise ValueError('LEGACY_MEDIA_LOCATOR_MISSING_ALTERNATE_AVAILABLE:'+str(alt))
                assert sha(path)==want
                with Image.open(path) as im:
                    im.load();size=list(im.size);ph=digest(list(ImageOps.grayscale(im).resize((16,16)).getdata()))
                for key in ['sha:'+want,'preview:'+ph]:
                    if key in owner:union(w,owner[key])
                    owner[key]=w
                media_audit.append(dict(world=w,role=m['role'],path=str(path),sha256=want,size=size,perceptual_group=ph))
            qualified.append(p)
        except Exception as exc:reject.append(dict(world_cluster_id=w,reason=str(exc),status='TASK_SEMANTICS_OR_SOURCE_UNRESOLVED'))
    comps=defaultdict(list)
    for p in panel:comps[find(p['world_cluster_id'])].append(p['world_cluster_id'])
    ordered=sorted(comps.values(),key=lambda ws:digest([20260911,'SOURCE_COMPONENT',sorted(ws)]));split={};counts=Counter()
    # Deterministic component allocation with stratification by source count subtype.
    stratum_counts=defaultdict(Counter)
    pby={p['world_cluster_id']:p for p in panel}
    for ws in ordered:
        st=Counter(pby[w]['count_substratum'] for w in ws)
        fractions={'LOCALIZE':.6,'SELECT':.2,'LOCKED_EVAL':.2}
        key=min(fractions,key=lambda k:sum((stratum_counts[s][k]+n)/fractions[k] for s,n in st.items()))
        for w in ws:split[w]=key;counts[key]+=1
        for s,n in st.items():stratum_counts[s][key]+=n
    splitrows=[dict(world_cluster_id=w,world_component_id='component_'+digest(sorted(comps[find(w)]))[:20],split=split[w],historically_exposed=True) for w in sorted(split)]
    save(root/'manifest/WORLD_PARTITION.jsonl',splitrows,'jsonl')
    save(root/'preparation/media_audit.jsonl',media_audit,'jsonl');save(root/'preparation/rejects.jsonl',reject,'jsonl')
    b1=Builder(c,'B1');audits=[]
    for p in qualified:
        w=p['world_cluster_id'];fact,pf=p['facts'];category=noun(fact['subject']).replace('_',' ');protected=noun(pf['subject']).replace('_',' ')
        br=branch_spec(fact,p['count_substratum']);a1=Action(br['action'],br['amount']);pre=fact['value'];pv=pf['value'];media=p['media']
        prefix=('OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.\nIMAGE ORDER: '+
            ', '.join(f'{i+1}={m["role"]}' for i,m in enumerate(media))+f'\nOBJECT: {category}. COUNTING SCOPE: the {category} counted in the reference image, not a whole-room census.\n')
        seqheader='The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.\n'
        def q(state,cat=category):return f'TARGET: {state}\nQUERY: How many {cat} are in the reference-image counting scope in state {state}?'
        b1.emit(w,'SHARED','PROTECTED_PRE_SUPPLEMENT',prefix+q('S0',protected),pv,media,split[w],target='S0',proof={'source_fact':pf['fact_id']})
        for m in [x for x in matches if x['world_cluster_id']==w]:
            seq=m['condition'];rev={'ADD':'REMOVE','REMOVE':'ADD','NOOP':'NOOP'}
            a2=Action(rev[a1.kind],a1.amount) if seq=='INVERSE' else Action('ADD',3)
            program=Program(pre,a1,a2,'SOURCE_SUPPORTED_COUNT');replay(program)
            old=oldreq[m['TARGET']];proof=oldgold[m['TARGET']]['proof']
            assert (proof['pre'],proof['first'],oldgold[m['TARGET']]['expected']['value'])==(pre,program.s1,program.s2)
            text=old['payload']['text'];assert 'The two steps are sequential within S2.' in text
            assert 'STEP 1: '+step_text(a1,category).split(' to the counted set')[0] in text or a1.kind=='NOOP'
            assert old['payload']['media']==media
            audit=dict(world_cluster_id=w,sequence=seq,split=split[w],program=asdict(program),s1=program.s1,s2=program.s2,protected=pv,
                semantics='CUMULATIVE_INSIDE_HYPOTHETICAL_S2_NOT_INDEPENDENT_STEPS',legacy_request_id=m['TARGET'],legacy_payload_hash=digest(old['payload']),
                legacy_request_file=entry(source/'public_inputs/requests.jsonl'),source_graphs=p['source_graphs'],source_facts=[f['fact_id'] for f in p['facts']],**signature(program))
            audits.append(audit);b1.panels.append(audit)
            b1.logical.append(dict(logical_id='ssml_'+digest(['B1',w,seq,'B00'])[:24],world_cluster_id=w,sequence=seq,condition='B00',split=split[w],
                request_id=m['TARGET'],execution_source='EXACT_LEGACY_REUSE',legacy_source=str(source),legacy_payload=old['payload'],legacy_schema=old['schema']))
            pro=dict(program=asdict(program),source_fact_ids=[fact['fact_id'],pf['fact_id']],independent_multiset_replay=True)
            before=prefix+seqheader+'ACTION_1: '+step_text(a1,category)+'.\n'
            def ctx(note='No state value is supplied here.',initial=''):
                return prefix+initial+seqheader+'ACTION_1: '+step_text(a1,category)+'.\nSTATE_NOTE: '+note+'\nACTION_2: '+step_text(a2,category)+'.\n'
            def emit(cond,body,value,med=media,target='S2',role='NEUTRAL',schema=None):
                return b1.emit(w,seq,cond,body,value,med,split[w],schema,role,target,pro)
            emit('B01',ctx()+q('S2'),program.s2)
            emit('B02',prefix+q('S0'),pre,target='S0')
            emit('B03',ctx()+q('S1'),program.s1,target='S1')
            emit('B04',ctx()+'QUERY: Which named state is the input to ACTION_2? Return its state name.', 'S1',schema=dict(kind='value',domain='enum',values=['S0','S1','S2'],nullable=True))
            emit('B05',ctx(initial=f'ORACLE INITIAL FACT: the target count in S0 is exactly {pre}.\n')+q('S2'),program.s2,role='ORACLE')
            emit('B06',ctx(f'ORACLE CHECKPOINT: the target count in S1 is exactly {program.s1}.')+q('S2'),program.s2,role='ORACLE')
            emit('B07',ctx(f'IRRELEVANT REGISTER: an unrelated bookkeeping entry is exactly {program.s1}. This is not a scene count or state update.')+q('S2'),program.s2,role='SHAM')
            sym=f'SYMBOLIC PROGRAM ONLY; no image evidence is required. The target counted set initially has exactly {pre} members in S0.\n'+seqheader+'ACTION_1: '+step_text(a1,'members')+'.\nACTION_2: '+step_text(a2,'members')+'.\nQUERY: What is the count in S2?'
            emit('B08',sym,program.s2,[],role='SYMBOLIC')
            suffix=lambda v:f'EXPLICIT SYMBOLIC INPUT: state X has exactly {v} members. Apply one action to X: '+step_text(a2,'members')+'.\nQUERY: What is the resulting count?'
            emit('B09',suffix(program.s1),program.s2,[],role='SYMBOLIC')
            for cond,state,value in [('B10','S0',pre),('B11','S1',program.s1),('B12','S2',program.s2)]:
                emit(cond,prefix+f'ORACLE COMPLETE STATE TABLE: S0={pre}; S1={program.s1}; S2={program.s2}.\n'+q(state),value,target=state,role='ORACLE')
            legal=[v for v in range(max(16,program.s1+5)) if v!=program.s1 and (a2.kind!='REMOVE' or v>=a2.amount)]
            low=max([v for v in legal if v<program.s1],default=legal[0]);high=next(v for v in legal if v>max(program.s1,low))
            for cond,value in [('B13',low),('B14',high)]:
                emit(cond,'COUNTERFACTUAL SYMBOLIC INPUT: This is a separate hypothetical input, not an observation of the image.\n'+suffix(value),a2.apply(value),[],role='COUNTERFACTUAL')
                pro_cf=b1.gold[b1.logical[-1]['request_id']]['proof']=dict(pro,counterfactual_s1=value,counterfactual_gold=a2.apply(value),low_strictly_below_actual=low<program.s1)
            emit('B15',ctx()+q('S0'),pre,target='S0')
            emit('B16',ctx()+q('S2',protected),pv)
            emit('B17',prefix+'Apply only the following first action to S0 to obtain S1. All other categories remain unchanged; do not recount occlusion.\nACTION_1: '+step_text(a1,category)+'.\n'+q('S1'),program.s1,target='S1')
    save(root/'preparation/sequence_audit.jsonl',audits,'jsonl')
    b2=Builder(c,'B2');family_order=sorted(range(16),key=lambda g:digest([20260911,'SYMBOLIC_FAMILY',g]))
    famsplit={g:'LOCALIZE' if i<10 else 'SELECT' if i<13 else 'LOCKED_EVAL' for i,g in enumerate(family_order)}
    programs=[]
    for base in range(16):
        definitions=[(base,Action('ADD',2),Action('REMOVE',1)),(base+1,Action('ADD',1),Action('REMOVE',1)),
            (base,Action('ADD',2),Action('ADD',3)),(base,Action('ADD',3),Action('REMOVE',2)),
            (base,Action('SET',2),Action('ADD',3)),(base,Action('ADD',4),Action('REMOVE',4))]
        for k,(s0,a1,a2) in enumerate(definitions):
            p=Program(s0,a1,a2);replay(p);w='ssm_symbolic_'+digest([base,k,asdict(p)])[:20];sp=famsplit[base]
            pp=dict(world_cluster_id=w,program_family=f'base_family_{base}',split=sp,program=asdict(p),s1=p.s1,s2=p.s2,**signature(p))
            programs.append(pp);b2.panels.append(pp)
            ctx=f'NON-SPATIAL SYMBOLIC REGISTER R. Its initial value in S0 is {s0}. Actions are cumulative; A2 acts on the result of A1.\nACTION_1: '+step_text(a1,'register units')+'.\nACTION_2: '+step_text(a2,'register units')+'.\n'
            for cond,state,val in [('FINAL','S2',p.s2),('INTERMEDIATE','S1',p.s1)]:
                b2.emit(w,'PROGRAM',cond,ctx+f'TARGET: {state}. QUERY: What is the value of register R at this state?',val,[],sp,proof=pp)
            b2.emit(w,'PROGRAM','SUFFIX',f'NON-SPATIAL SYMBOLIC REGISTER R has value {p.s1}. Apply only this action: '+step_text(a2,'register units')+'. What is the resulting value?',p.s2,[],sp,proof=pp)
            try: reversed_program=Program(s0,a2,a1)
            except ValueError:
                b2.logical.append(dict(logical_id='ssml_'+digest(['B2',w,'REVERSED'])[:24],world_cluster_id=w,sequence='PROGRAM',condition='REVERSED',split=sp,
                    request_id=None,execution_source='NOT_APPLICABLE',reason='REVERSED_PROGRAM_HAS_ILLEGAL_NEGATIVE_INTERMEDIATE'))
            else:
                b2.emit(w,'PROGRAM','REVERSED',f'NON-SPATIAL SYMBOLIC REGISTER R initially has value {s0}. Execute these two actions cumulatively in the listed order.\nSTEP 1: '+step_text(a2,'register units')+'.\nSTEP 2: '+step_text(a1,'register units')+'.\nQUERY: What is the final value?',reversed_program.s2,[],sp,proof=dict(pp,reversed_expected=reversed_program.s2))
    assert len(programs)==96 and len(b2.logical)==384
    refs=[entry(source/'manifest/REQUEST_LOCK.json'),entry(root/'manifest/WORLD_PARTITION.jsonl'),entry(HERE.parent/'SpaceConflict_Sequential_State_Mechanism_Work_Guide_CN.md')]
    result=[b1.publish(root,refs),b2.publish(root,refs)]
    save(root/'manifest/PANEL_LOCK.json',dict(status='FROZEN_BEFORE_NEW_MODEL_OUTPUTS',created_at=now(),batches=result,source_read_guard=dict(guard),
        original_worlds=80,qualified_worlds=len(qualified),rejected_worlds=len(reject),partition_counts=dict(counts),
        historical_gold_unchanged=True,mechanism_selection_not_started=True,B13_boundary_policy='NEAREST_LEGAL_ALTERNATIVE_IF_NO_LOWER_VALUE; ACTUAL_VALUE_AND_DIRECTION_RECORDED'))
    save(root/'config.json',c)
    save(root/'scheduler/resource_authorization.json',dict(approved=True,models=MODELS,source='USER_20260911_EXPLICIT_SUBMIT_ALL_B1_B2',
        restored_policy=entry(SWS_CODE/'config_auto_v2.json'),scope=['B1','B2','SOURCE_PREPARATION','PER_MODEL_TECHNICAL_PREFLIGHT','SCORING'],
        total_gpu_hour_cap=None,total_cap_policy='RESTORED_USER_NO_TOTAL_CAP_FIXED_B1_B2_SCIENTIFIC_SCOPE',internal_interventions_authorized_by_this_launch=False))
    print(json.dumps(dict(status='B1_B2_FROZEN',partition_counts=dict(counts),qualified_worlds=len(qualified))),flush=True)
if __name__=='__main__':main()
