"""Source-only C1 and missing E5 measurements, frozen before any new outputs."""
import copy
import shutil
from collections import Counter
from bc_common import *
from data_continuation_v1.prepare import source_guard
from real_compile_v1 import SOURCE_IMAGES,runtime_files
import real_design_v1 as design
from coverage_supplement_v1.compile import contract
from contracts import parse

class Builder:
    def __init__(self,c,out,name,split):
        self.c=c;self.out=out;self.name=name;self.split=split;self.req=[];self.gold=[];self.matches=[];self.panels=[]
    def emit(self,p,condition,schema,value,text,target='S0',experiment='C1',role='NEUTRAL'):
        r=dict(experiment=experiment,condition=condition,world_cluster_id=p['world_cluster_id'],split=self.split,
            logical_bundle_id=digest([self.name,p['world_cluster_id']]),sample_family='COUNT_CONTROLLED_BRANCH',
            source_type='CONTROLLED_SOURCE_EXTENSION',payload=dict(system=design.SYSTEM,text=text+'\nOUTPUT CONTRACT: '+contract(schema),media=p['media']),
            schema=schema,requested_tokens=512,information_role=role,target_state=target,queried_fact_id=condition,view_variant='FULL',
            wording='FROZEN_BC_V1',models=self.c['models'],review_status='HUMAN_REVIEW_WAIVED_BY_RESEARCHER',scientific_review_grade='AUTO_ONLY_PROVISIONAL')
        r['request_id']='bc_'+digest([self.name,p['world_cluster_id'],r['payload'],schema])[:24];r['model_independent_request_hash']=digest(r)
        expected=value if isinstance(value,dict) else dict(value=value)
        self.req.append(r);self.gold.append(dict(request_id=r['request_id'],world_cluster_id=p['world_cluster_id'],expected=expected,
            source_graphs=p['source_graphs'],facts=[f['fact_id'] for f in p['facts']],source_type=r['source_type']))
        return r['request_id']
    def publish(self,refs):
        dest=self.out/'batches'/self.name
        if (dest/'manifest/REQUEST_LOCK.json').exists():raise ValueError('REFUSE_REFREEZE')
        req={r['request_id']:r for r in self.req};gold={g['request_id']:g for g in self.gold}
        if len(req)!=len(self.req) or set(req)!=set(gold):raise ValueError('REQUEST_GOLD_BIJECTION')
        for rid,r in req.items():
            expected=copy.deepcopy(gold[rid]['expected'])
            if 'facts' in expected:expected['facts']=[dict(query_id=k,value=v) for k,v in expected['facts'].items()]
            pp=parse(json.dumps(expected),r['schema'])
            if pp['status']!='VALID' or pp['component_values']!=gold[rid]['expected']:raise ValueError('SOURCE_GOLD_SCHEMA_ROUNDTRIP:'+rid)
            if any(k in r['payload']['text'] for k in ('fact:','source_item:','world_graph','private_gold','target_gold')):raise ValueError('PRIVATE_INPUT_LEAK')
        save(dest/'public_inputs/requests.jsonl',self.req,'jsonl');save(dest/'private_gold/request_gold.jsonl',self.gold,'jsonl')
        save(dest/'private_gold/matched_structure.jsonl',self.matches,'jsonl');save(dest/'private_gold/world_panel.jsonl',self.panels,'jsonl')
        worlds=sorted({r['world_cluster_id'] for r in self.req},key=lambda w:digest([self.c['seed'],'BC_WORLD_SHARD',w]))
        shards=[]
        for sid in range(min(4,len(worlds))):
            ws=worlds[sid::min(4,len(worlds))];rr=[r for r in self.req if r['world_cluster_id'] in ws]
            pp=dest/f'public_inputs/shard_{sid:03}.jsonl';save(pp,rr,'jsonl')
            shards.append(dict(shard=sid,worlds=ws,requests=len(rr),request_file=entry(pp)))
        save(dest/'manifest/shards.json',shards)
        code=runtime_files(self.c)+[entry(HERE/n) for n in ('bc_common.py','compile_behavior.py','behavior_runner.py','job_cpu.sh','content_score.py')]
        code += [entry(SWS_CODE/'coverage_supplement_v1/compile.py'),entry(SWS_CODE/'interface_repair_v3/adapter.py'),entry(SWS_CODE/'interface_repair_v2/adapter.py')]
        lock=dict(batch=self.name,run_id=RUN,created_at=now(),code=code,config_snapshot=self.c,
            public_inputs=[entry(dest/'public_inputs/requests.jsonl'),entry(dest/'manifest/shards.json')]+[s['request_file'] for s in shards],
            private_inputs=[entry(dest/'private_gold'/n) for n in ('request_gold.jsonl','matched_structure.jsonl','world_panel.jsonl')],
            sources=refs,models=self.c['models'],split=self.split,output_budget=512,parser='SWS_INTERFACE_V3',
            source_selection='SOURCE_ONLY_NOT_MODEL_FAILURE',semantic_retries=0,human_gate=False)
        save(dest/'manifest/REQUEST_LOCK.json',lock)
        acc=dict(status='FROZEN_PROCESSOR_PENDING',batch=self.name,worlds=len(worlds),requests_per_model=len(req),shards=len(shards),
            split=self.split,job_id=os.environ['SLURM_JOB_ID'],conditions=dict(Counter(r['condition'] for r in self.req)),source_refs=refs)
        save(dest/'reports/COMPILE_ACCEPTANCE.json',acc);print(json.dumps(acc),flush=True)
        return dest

def prefix(p):
    return ('OBSERVED STATE S0: the supplied reference image. Support views do not add members to its counting scope.\nIMAGE ORDER: '+
        ', '.join(f'{i+1}={m["role"]}' for i,m in enumerate(p['media']))+'\n')

def c1(c,sws,out):
    qualification=out/'P4_C1/candidate_qualification.jsonl';eligible={r['world_cluster_id'] for r in rows(qualification) if r['status']=='QUALIFIED_WITHIN_REGISTERED_HISTORY'}
    source=sws/'preparation/holdout_val_rebuild_v1_20260910/private_gold/independent_pairs.jsonl'
    selected=sorted([r for r in rows(source) if r['world_cluster_id'] in eligible and r['family']=='COUNT'],key=lambda r:digest([c['seed'],'BC_C1',r['world_cluster_id']]))
    if not selected:
        save(out/'P4_C1/C1_NOT_RUN.json',dict(reason='NO_QUALIFIED_CANDIDATE',qualification=entry(qualification)));return
    b=Builder(c,out,'c1_count_v1','confirmation');count=dict(kind='value',domain='count',nullable=True)
    for s in selected:
        w=s['world_cluster_id'];ff=[x['fact'] for x in s['source_pair']];graphs=[x['source_graph'] for x in s['source_pair']]
        for x in s['source_pair']:
            check(x['source_graph'])
            if x['fact'] not in load(x['source_graph']['path'])['facts']:raise ValueError('SOURCE_FACT_NOT_IN_GRAPH')
        mm=[]
        for role,loc in sorted(ff[0]['grounding']['frame_roles'].items(),key=lambda x:(x[0]!='reference_frame',x[0])):
            src=SOURCE_IMAGES/loc;h=sha(src);dst=out/'batches/c1_count_v1/media'/(h+'.image');dst.parent.mkdir(parents=True,exist_ok=True)
            if not dst.exists():shutil.copyfile(src,dst)
            if sha(dst)!=h:raise ValueError('MEDIA_COPY_HASH_MISMATCH')
            mm.append(dict(kind='image',path=str(dst),sha256='sha256:'+h,role=role,presentation_max_pixels=401408))
        p=dict(world_cluster_id=w,facts=ff,source_graphs=graphs,media=mm,primary_stratum='COUNT',count_substratum='ADD',split='confirmation')
        b.panels.append(p);a,pf=ff;av,pv=(design.fact_value(f) for f in ff);qt=design.question(a);qp=design.question(pf);base=prefix(p);ids={}
        ids['PRE_VALUE']=b.emit(p,'PRE_VALUE',count,av,base+'TARGET: S0\nQUERY: '+qt)
        ids['PROTECTED_PRE']=b.emit(p,'PROTECTED_PRE',count,pv,base+'TARGET: S0\nQUERY: '+qp)
        true=b.emit(p,'TRUE_CANDIDATE',count,av,base+'TARGET: S0\n'+design.challenge(av,'CANDIDATE',qt)+'\nQUERY: '+qt,role='CANDIDATE')
        for cv in [av+d for d in (-2,-1,1,2) if av+d>=0]:
            pair=dict(experiment='E2',world_cluster_id=w,wording='FROZEN_BC_V1',target_gold=av,candidate_value=cv,neutral=ids['PRE_VALUE'],true=true)
            for role,key in [('CANDIDATE','false'),('SHAM','sham')]:
                pair[key]=b.emit(p,role+'_'+str(cv),count,av,base+'TARGET: S0\n'+design.challenge(cv,role,qt)+'\nQUERY: '+qt,role=role)
                pair['protected_'+key]=b.emit(p,'PROTECTED_'+role+'_'+str(cv),count,pv,base+'TARGET: S0\n'+design.challenge(cv,role,qt)+'\nQUERY: '+qp,role=role)
            pair['protected_neutral']=ids['PROTECTED_PRE'];b.matches.append(pair)
        branch=design.branch_spec(a,'ADD');ctx=base+branch['text']+'\n';noun=design.noun(a['subject']).replace('_',' ');protected=design.noun(pf['subject']).replace('_',' ')
        for state,value in branch['values'].items():
            ids['TARGET_'+state]=b.emit(p,'TARGET_'+state,count,value,ctx+'TARGET: '+state+'\nQUERY: '+design.question(a,state),target=state,role='AUTHORIZED_INTERVENTION')
        ids['PROTECTED_AFTER']=b.emit(p,'PROTECTED_AFTER',count,pv,ctx+'TARGET: SA\nQUERY: '+design.question(pf,'SA'),target='SA',role='AUTHORIZED_INTERVENTION')
        for label,schema,val,q in [
            ('ACTION_TYPE',dict(kind='value',domain='enum',values=['ADD','REMOVE','NOOP'],nullable=True),'ADD','Which operation is specified for branch SA?'),
            ('ACTION_TARGET',dict(kind='value',domain='enum',values=[noun,protected],nullable=True),noun,'Which counted category is changed in branch SA?'),
            ('ACTION_AMOUNT',count,2,'How many counted members are explicitly added in branch SA?')]:
            ids[label]=b.emit(p,label,schema,val,ctx+'TARGET: SA\nQUERY: '+q,target='SA',role='AUTHORIZED_INTERVENTION')
        schema=dict(kind='facts',domain='count',nullable=True,query_ids=['q0','qA','qB','qP'])
        ids['JOINT_STATE']=b.emit(p,'JOINT_STATE',schema,dict(facts=dict(q0=av,qA=av+2,qB=av+3,qP=pv)),ctx+
            '\nQUERIES: q0: '+design.question(a,'S0')+' qA: '+design.question(a,'SA')+' qB: '+design.question(a,'SB')+' qP: '+design.question(pf,'SA'),target='ALL',role='AUTHORIZED_INTERVENTION')
        b.matches.append(dict(experiment='STATE_CHAIN',world_cluster_id=w,ids=ids,expected_states=branch['values'],protected_gold=pv,transition=branch,
            selection_identifiable=len(set(branch['values'].values()))==3))
    refs=[entry(qualification),entry(source),entry(out/'manifest/BEHAVIORAL_CLOSURE_LOCK.json')]
    dest=b.publish(refs)
    save(out/'P4_C1/C1_PANEL_LOCK.json',dict(status='FROZEN_BEFORE_CONFIRMATION_OUTPUTS',worlds=[p['world_cluster_id'] for p in b.panels],
        request_lock=entry(dest/'manifest/REQUEST_LOCK.json'),models=c['models'],source_scope='SMALL_CA_VQA_COUNT_COHORT_NOT_ALL_SPATIAL_VARIABLES',
        H5_not_tested=True,actions='ADD_ONLY_CONFIRMATION; REMOVE_AND_MULTISTEP_IN_DISCOVERY_SEPARATE',
        primary_H1='FALSE_MINUS_SHAM_WRONG_RATE_GIVEN_NEUTRAL_CORRECT_WORLD_CLUSTER_BOOTSTRAP',
        H2='POST_WRONG_GIVEN_PRE_AND_ALL_THREE_ACTION_FIELDS_CORRECT',H3='BASE_AND_PROTECTED_DAMAGE_GIVEN_POST_CORRECT',
        H4='TARGET_ERROR_GIVEN_JOINT_STATE_CORRECT_NONDEGENERATE',no_forced_failure=True,grade='AUTO_ONLY_PROVISIONAL'))

def e5(c,sws,out):
    source=sws/'batches/e5_sequence_supplement_v1_20260910';panels=list(rows(source/'private_gold/world_panel.jsonl'))
    original={r['request_id']:r for r in rows(source/'public_inputs/requests.jsonl')};matches=list(rows(source/'private_gold/matched_structure.jsonl'))
    gg={r['request_id']:r for r in rows(source/'private_gold/request_gold.jsonl')};b=Builder(c,out,'e5_measurement_v1','discovery')
    count=dict(kind='value',domain='count',nullable=True)
    for p in panels:
        w=p['world_cluster_id'];a,pf=p['facts'];noun=design.noun(a['subject']).replace('_',' ');protect=design.noun(pf['subject']).replace('_',' ')
        branch=design.branch_spec(a,p['count_substratum']);b.panels.append(p)
        for m in [m for m in matches if m['world_cluster_id']==w]:
            src=original[m['TARGET']];body=src['payload']['text'].split('TARGET: S2\nQUERY:',1)[0];proof=gg[m['TARGET']]['proof'];ids={}
            if body==src['payload']['text']:raise ValueError('SOURCE_SEQUENCE_PREFIX_NOT_FOUND')
            first=branch['action'];second=('REMOVE' if first=='ADD' else 'ADD' if first=='REMOVE' else 'NOOP') if m['condition']=='INVERSE' else 'ADD'
            for step,action,amount in [(1,first,branch['amount']),(2,second,branch['amount'] if m['condition']=='INVERSE' else 3)]:
                for field,schema,val,q in [
                    ('TYPE',dict(kind='value',domain='enum',values=['ADD','REMOVE','NOOP'],nullable=True),action,f'Which operation is specified at STEP {step}?'),
                    ('AMOUNT',count,amount,f'How many members are changed at STEP {step}? Return 0 for no change.'),
                    ('TARGET',dict(kind='value',domain='enum',values=[noun,protect,'NONE'],nullable=True),'NONE' if action=='NOOP' else noun,f'Which counted category does STEP {step} change? Return NONE for no change.')]:
                    key=f'ACTION_{step}_{field}';ids[key]=b.emit(p,m['condition']+'_'+key,schema,val,body+'TARGET: S2\nQUERY: '+q,target='S2',experiment='E5_MEASUREMENT',role='AUTHORIZED_INTERVENTION')
            ids['INTERMEDIATE']=b.emit(p,m['condition']+'_INTERMEDIATE',count,proof['first'],body+
                'TARGET: S2 immediately after STEP 1 and before STEP 2\nQUERY: '+f'How many {noun} are in that intermediate counted set?',
                target='S2_AFTER_STEP1',experiment='E5_MEASUREMENT',role='AUTHORIZED_INTERVENTION')
            b.matches.append(dict(world_cluster_id=w,sequence=m['condition'],ids=ids,original_endpoints={k:m[k] for k in ('TARGET','BASE','PROTECTED')},
                source_proof=proof,source_requests_prefix_sha256=hashlib.sha256(body.encode()).hexdigest(),
                interpretation='SEPARATE_REQUEST_SAME_SEQUENCE_MEASUREMENT_NOT_HIDDEN_TRACE'))
    b.publish([entry(source/'private_gold'/n) for n in ('world_panel.jsonl','request_gold.jsonl','matched_structure.jsonl')]+[entry(source/'public_inputs/requests.jsonl')])

def main():
    p=cli(__doc__);p.add_argument('--batch',choices=['c1','e5'],required=True);a=p.parse_args();c,sws,out=context(a)
    if a.dry_run:print('Source-only frozen behavior '+a.batch);return
    guard=source_guard();{'c1':c1,'e5':e5}[a.batch](c,sws,out)
    save(out/'preparation'/('SOURCE_GUARD_'+a.batch+'.json'),guard)

if __name__=='__main__':main()
