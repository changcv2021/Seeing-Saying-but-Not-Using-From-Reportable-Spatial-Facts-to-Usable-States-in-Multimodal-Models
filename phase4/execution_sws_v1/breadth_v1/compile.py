"""Compile native E8 and source-grounded non-count discovery, without predictions."""
import copy
import re
import sys
from collections import Counter,defaultdict
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from common_auto_v2 import *
from data_continuation_v1.prepare import source_guard
from real_compile_v1 import runtime_files
from real_design_v1 import SYSTEM
from real_processor_v1 import verify

INV={'LEFT_OF':'RIGHT_OF','RIGHT_OF':'LEFT_OF','ABOVE':'BELOW','BELOW':'ABOVE','FRONT_OF':'BEHIND','BEHIND':'FRONT_OF','BEFORE':'AFTER','AFTER':'BEFORE'}
AXIS={'LEFT_OF':'horizontal (left/right)','RIGHT_OF':'horizontal (left/right)','ABOVE':'vertical (above/below)','BELOW':'vertical (above/below)','FRONT_OF':'depth (front/behind)','BEHIND':'depth (front/behind)','BEFORE':'appearance order (before/after)','AFTER':'appearance order (before/after)'}
NATIVE='native_e8_breadth_v1_20260910'
EXPAND='noncount_breadth_v1_20260910'

def entity(x):
    if not isinstance(x,str):raise ValueError('MISSING_ENTITY')
    if x.startswith('bbox_anchor:'):
        values=x.rsplit(':',1)[-1].split('_')
        if len(values)!=4 or not all(t.isdigit() for t in values):raise ValueError('BAD_BBOX_ENTITY')
        return 'the object in bounding box ['+', '.join(values)+'] (normalized 0–1000 xyxy coordinates)'
    if x.startswith(('mention:','class:')):return 'the '+x.split(':',1)[1].split('@source_item:')[0].replace('_',' ')
    if re.fullmatch(r'[a-zA-Z][a-zA-Z _-]*',x):return 'the '+x.replace('_',' ')
    raise ValueError('ENTITY_NEEDS_SOURCE_GROUNDING:'+x)

def atom(pair):
    sc=pair['supported_claim']
    if 'graph' in sc:return dict(sc['graph'])
    aa=sc['normalized']['atoms']
    if len(aa)!=1:raise ValueError('COMPOUND_TARGET_NOT_IMPLEMENTED')
    return dict(aa[0])

def claim_text(pair,label):
    z=pair['supported_claim' if label=='SUPPORTED' else 'contradictory_claim']
    return z.get('natural_text') or z.get('text')

def spec(f):
    pred=f['predicate']
    if pred=='COUNT' and type(f.get('value')) is int and f.get('polarity','positive')=='positive':
        subject=entity(f['subject']).removeprefix('the ')
        return dict(kind='value',domain='count',nullable=True),f['value'],'What is the exact number of '+subject+' in the stated scope?'
    if pred not in INV or f.get('polarity','positive')!='positive':raise ValueError('NO_UNIQUE_VALUE_DOMAIN')
    domain=sorted([pred,INV[pred]])
    return dict(kind='value',domain='enum',nullable=True,values=domain),pred,('Along the '+AXIS[pred]+' axis, what is the relation of '+entity(f['subject'])+' to '+entity(f['object'])+'?')

def contract(s):
    value='a nonnegative integer' if s['domain']=='count' else 'one of '+json.dumps(s['values'])
    value+=' or null if not determined'
    if s['kind']=='verdict':return 'Return one JSON object with only "verdict": "SUPPORTED", "CONTRADICTORY", or "UNKNOWN".'
    if s['kind']=='facts':return 'Return {"facts":[{"query_id":...,"value":...},...]}, exactly once for each query ID '+json.dumps(s['query_ids'])+'. Each value is '+value+'.'
    if s['kind']=='joint':return 'Return one JSON object with keys '+', '.join(s['order'])+' in that order. "value" is '+value+'; "verdict" is "SUPPORTED", "CONTRADICTORY", or "UNKNOWN".'
    return 'Return one JSON object with only "value": '+value+'.'

def scope(pair,original):
    if pair.get('level')=='L4':return 'All supplied images depict the initial scene PRE. POST is the hypothetical scene after the stated change, not another observed photograph.'
    ctx=pair['supported_claim']['normalized']['context']
    return ('SCOPE: '+str(ctx.get('scope'))+'. REFERENCE FRAME: '+str(ctx.get('reference_frame'))+'. TARGET VIEW: '+str(ctx.get('view_id'))+'. '+original.get('media_context',''))

def observation(b,media):
    return scope(b['source']['pair'],b['original_requests'][0])+'\nIMAGE ORDER: '+', '.join(str(i+1)+'='+m['role'] for i,m in enumerate(media))+'.\n'

class Compiler:
    def __init__(self,c,root,batch):self.c=c;self.root=root;self.batch=batch;self.req={};self.gold={};self.aliases=[];self.matched=[];self.panels=[];self.gaps=[]
    def emit(self,b,condition,s,expected,question,exp='E8',media=None,role='NEUTRAL',oracle=None,extra='',target='observed',wording='W0'):
        media=copy.deepcopy(b['original_requests'][0]['media'] if media is None else media)
        if any(m['kind']!='image' for m in media):raise ValueError('VIDEO_PROCESSOR_NOT_YET_BRIDGED')
        text=observation(b,media)+extra+'\n'
        if oracle:text+='ORACLE INFORMATION (permitted for this condition only):\n'+oracle+'\n'
        text+='TARGET: '+target+'\nQUERY: '+question+'\nOUTPUT CONTRACT: '+contract(s)+'\nStay within 512 output tokens.'
        w=b['world_cluster_id'];family='NATIVE_'+b['level']+'_'+('COUNT' if atom(b['source']['pair'])['predicate']=='COUNT' else 'NONCOUNT')
        if b['level']=='SETUP':family='SYNTHETIC_SETUP'
        r=dict(experiment=exp,condition=condition,world_cluster_id=w,split='discovery',logical_bundle_id=digest([self.batch,w,b['level']]),
            sample_family=family,source_type=b['source']['pair'].get('l4_origin','NATIVE'),level=b['level'],
            payload=dict(system=SYSTEM,text=text,media=media),schema=s,requested_tokens=512,information_role=role,
            target_state=target,queried_fact_id='q1',view_variant='FULL' if media==b['original_requests'][0]['media'] else 'CHANGED_MEDIA',
            wording=wording,order_assignment=s.get('order'),models=self.c['models'],review_status=self.c['review']['default_review_status'],
            scientific_review_grade='AUTO_ONLY_PROVISIONAL',oracle_access_level='EXPLICIT_LOCAL_INFORMATION' if oracle else 'NONE')
        rid='sws_breadth_'+digest([self.batch,w,r['payload'],s])[:24];r['request_id']=rid;r['model_independent_request_hash']=digest(r)
        g=dict(request_id=rid,expected=expected,world_cluster_id=w,source_pair_id=b['pair_id'],source_level=b['level'],
            source_bundle=b['_ref'],predicate=atom(b['source']['pair'])['predicate'],binary_nonidentifying=s['domain']=='enum' and len(s.get('values',[]))==2,
            ordinary_input_without_answer=not bool(oracle),oracle_allowed_fields=oracle,genuine_multiview_necessity=False)
        if rid in self.req:
            if self.gold[rid]['expected']!=expected:raise ValueError('SAME_INPUT_CONFLICTING_GOLD')
        else:self.req[rid]=r;self.gold[rid]=g
        self.aliases.append(dict(request_id=rid,experiment=exp,condition=condition,wording=wording,view_variant=r['view_variant']))
        return rid
    def gap(self,b,condition,reason):self.gaps.append(dict(world_cluster_id=b['world_cluster_id'],level=b['level'],pair_id=b['pair_id'],condition=condition,status='NOT_DIAGNOSABLE',reason=reason))
    def publish(self):
        out=self.root/'batches'/self.batch
        if not self.req:raise ValueError('EMPTY_BATCH')
        reqs=list(self.req.values());worlds=sorted({r['world_cluster_id'] for r in reqs},key=lambda w:digest([self.c['seed'],'BREADTH_SHARD',w]))
        save(out/'public_inputs/requests.jsonl',reqs,'jsonl');save(out/'private_gold/request_gold.jsonl',self.gold.values(),'jsonl')
        save(out/'private_gold/logical_aliases.jsonl',self.aliases,'jsonl');save(out/'private_gold/matched_structure.jsonl',self.matched,'jsonl')
        save(out/'private_gold/world_panel.jsonl',self.panels,'jsonl');save(out/'reports/NOT_DIAGNOSABLE.jsonl',self.gaps,'jsonl')
        shards=[]
        # Bound real work by requests while preserving each entire world bundle.
        groups=[];ww=[];n=0
        for w in worlds:
            nr=sum(r['world_cluster_id']==w for r in reqs)
            if ww and n+nr>240:groups.append(ww);ww=[];n=0
            ww.append(w);n+=nr
        if ww:groups.append(ww)
        for sid,ws in enumerate(groups):
            rr=[r for r in reqs if r['world_cluster_id'] in ws];path=out/f'public_inputs/shard_{sid:03}.jsonl';save(path,rr,'jsonl')
            shards.append(dict(shard=sid,worlds=len(ws),requests=len(rr),request_file=entry(path)))
        save(out/'manifest/shards.json',shards)
        code=runtime_files(self.c)+[entry(HERE/x) for x in ('compile.py','runner.py','job.sh','analysis.py')]
        public=[entry(out/'public_inputs/requests.jsonl'),entry(out/'manifest/shards.json')]+[s['request_file'] for s in shards]
        private=[entry(out/'private_gold'/x) for x in ('request_gold.jsonl','logical_aliases.jsonl','matched_structure.jsonl','world_panel.jsonl')]
        lock=dict(batch=self.batch,created_at=now(),code=code,public_inputs=public,private_inputs=private,
            config_snapshot=self.c,models=self.c['models'],source_selection='FROZEN_E8_ANCHORS_AND_SOURCE_ONLY_HASH_NO_MODEL_OUTPUTS',
            human_gate=False,qualification='AUTO_ONLY_PROVISIONAL',scope='QUALIFIED_NATIVE_DIAGNOSTICS_NOT_ALL_WORLD_SUBCONDITIONS')
        save(out/'manifest/REQUEST_LOCK.json',lock)
        report=dict(batch=self.batch,status='COMPILED_PROCESSOR_PENDING',worlds=len(worlds),requests_per_model=len(reqs),
            requests_by_level=dict(Counter(r['level'] for r in reqs)),logical_by_experiment=dict(Counter(r['experiment'] for r in self.aliases)),
            gaps=len(self.gaps),gap_reasons=dict(Counter(r['reason'] for r in self.gaps)),shards=shards,
            no_model_output_selection=True,no_human_gate=True,genuine_multiview_necessity_certified_worlds=0)
        save(out/'reports/COMPILE_ACCEPTANCE.json',report);return report

def original_verdicts(cc,b,extra=''):
    out={};s=dict(kind='verdict',domain='enum',values=['SUPPORTED','CONTRADICTORY','UNKNOWN'],nullable=True)
    for label in ('SUPPORTED','CONTRADICTORY'):
        text=claim_text(b['source']['pair'],label)
        if not text:raise ValueError('MISSING_ORIGINAL_CLAIM')
        out[label]=cc.emit(b,'FINAL_'+label,s,dict(verdict=label),'Judge this candidate against the stated observations and any hypothetical change: '+text,role='CANDIDATE',extra=extra)
    return out

def native(cc,b):
    pair=b['source']['pair'];level=b['level'];at=atom(pair);extra='';ids={}
    if level=='L4':
        it=pair.get('intervention',{});action=it.get('model_visible_text') or it.get('text') or b['original_requests'][0].get('intervention_text')
        if not action:raise ValueError('MISSING_VISIBLE_ACTION')
        extra='HYPOTHETICAL CHANGE: '+action+'\nPRE is the supplied initial scene. POST is after this change.\n'
    ids.update(original_verdicts(cc,b,extra))
    try:s,value,q=spec(at)
    except ValueError as exc:cc.gap(b,'FACT_VALUE',str(exc));return
    if level=='L4':
        if at['predicate']!='COUNT':cc.gap(b,'PRE_ACTION_POST','NONCOUNT_TRANSITION_TYPED_ADAPTER_REQUIRED');return
        pre=[f for f in pair.get('pre_state_reference',{}).get('facts',[]) if f['predicate']=='COUNT' and f['subject']==at['subject'] and f.get('scope')==at.get('scope')]
        if len(pre)!=1 or type(pre[0].get('value')) is not int:
            # Never decode a numeric value from a fact ID or infer PRE by reversing the answer.
            cc.gap(b,'PRE_VALUE','STRUCTURED_PRE_VALUE_NOT_IN_RELEASE_BUNDLE')
            ids['POST_VALUE']=cc.emit(b,'POST_VALUE',s,dict(value=value),q,extra=extra,target='POST')
            cc.matched.append(dict(experiment='E8',world_cluster_id=b['world_cluster_id'],level=level,**ids));return
        pv=pre[0]['value'];deltas=pair['intervention'].get('count_deltas',{})
        if at['subject'] not in deltas or pv+deltas[at['subject']]!=value:
            cc.gap(b,'PRE_ACTION_POST','EXACT_COUNT_TRANSITION_REPLAY_UNAVAILABLE');return
        ids['PRE_VALUE']=cc.emit(b,'PRE_VALUE',s,dict(value=pv),q,extra=extra,target='PRE')
        ids['POST_VALUE']=cc.emit(b,'POST_VALUE',s,dict(value=value),q,extra=extra,target='POST')
        js=dict(s,kind='facts',query_ids=['q1','q2'])
        ids['JOINT_STATE']=cc.emit(b,'JOINT_STATE',js,dict(facts={'q1':pv,'q2':value}),'q1: '+q+' TARGET=PRE. q2: '+q+' TARGET=POST.',extra=extra,target='PRE_AND_POST')
        delta=deltas[at['subject']];av='ADD' if delta>0 else 'REMOVE' if delta<0 else 'NO_CHANGE'
        ass=dict(kind='value',domain='enum',values=['ADD','REMOVE','NO_CHANGE'],nullable=True)
        ids['ACTION_PARSE']=cc.emit(b,'ACTION_PARSE',ass,dict(value=av),'For the named category '+entity(at['subject'])+', does the stated action add instances, remove instances, or leave the number unchanged?',media=[],extra=extra,target='ACTION')
        ids['ORACLE_PRE']=cc.emit(b,'ORACLE_PRE',s,dict(value=value),q,extra=extra,target='POST',oracle='In PRE, the exact count of '+entity(at['subject'])+' is '+str(pv)+'.')
        ids['ORACLE_POST']=cc.emit(b,'ORACLE_POST',dict(kind='verdict',domain='count',nullable=True),dict(verdict='CONTRADICTORY'),
            'Judge this candidate: '+claim_text(pair,'CONTRADICTORY'),extra=extra,target='POST',role='CANDIDATE',oracle='In POST, the exact count of '+entity(at['subject'])+' is '+str(value)+'.')
    elif level=='L2':
        needed={e['fact_id'] for m in pair.get('media',{}).get('source_references',[]) for e in m.get('evidence_bbox_annotations',[])}
        fs={r['fact']['fact_id']:r['fact'] for r in b['matching_source_facts'] if r['fact']['fact_id'] in needed}
        if len(needed)!=2 or set(fs)!=needed:cc.gap(b,'PREMISES','EXACT_TWO_PREMISE_PROOF_NOT_RESOLVED');return
        ff=sorted(fs.values(),key=lambda f:digest([cc.c['seed'],f['fact_id']]))
        if not all(f['predicate']==at['predicate'] and f.get('polarity')=='positive' and f.get('derivation') is None for f in ff):raise ValueError('PREMISE_TYPE_MISMATCH')
        edges={(f['subject'],f['object']) for f in ff}
        if not any((at['subject'],mid) in edges and (mid,at['object']) in edges for mid in {f['subject'] for f in ff}|{f['object'] for f in ff}):raise ValueError('CHAIN_REPLAY_FAILED')
        for i,f in enumerate(ff,1):
            ps,pv,pq=spec(f);ids['PREMISE_'+str(i)]=cc.emit(b,'PREMISE_'+str(i),ps,dict(value=pv),pq)
        ids['CONCLUSION']=cc.emit(b,'CONCLUSION',s,dict(value=value),q)
        js=dict(s,kind='facts',query_ids=['q1','q2']);jj=' '.join('q'+str(i)+': '+spec(f)[2] for i,f in enumerate(ff,1))
        ids['JOINT_PREMISES']=cc.emit(b,'JOINT_PREMISES',js,dict(facts={'q1':ff[0]['predicate'],'q2':ff[1]['predicate']}),jj)
        oracle='\n'.join(entity(f['subject'])+' has relation '+f['predicate']+' to '+entity(f['object'])+'.' for f in ff)
        if any(f['subject']==at['subject'] and f['object']==at['object'] for f in ff):raise ValueError('ORACLE_CONCLUSION_LEAK')
        ids['ORACLE_PREMISES']=cc.emit(b,'ORACLE_PREMISES',s,dict(value=value),q,oracle=oracle)
        ids['ORACLE_VERDICT']=cc.emit(b,'ORACLE_VERDICT',dict(kind='verdict',domain='enum',values=s['values'],nullable=True),dict(verdict='CONTRADICTORY'),
            'Judge this candidate: '+claim_text(pair,'CONTRADICTORY'),role='CANDIDATE',oracle=oracle)
    else:
        ids['FACT_VALUE']=cc.emit(b,'FACT_VALUE',s,dict(value=value),q)
        ids['ORACLE_FACT_VERDICT']=cc.emit(b,'ORACLE_FACT_VERDICT',dict(s,kind='verdict'),dict(verdict='CONTRADICTORY'),
            'Judge this candidate: '+claim_text(pair,'CONTRADICTORY'),role='CANDIDATE',oracle='For the query "'+q+'", the value is '+json.dumps(value)+'.')
        if level=='L3':
            media=b['original_requests'][0]['media']
            for name,mm in [('REVERSED',list(reversed(media))),('ROTATED',media[1:]+media[:1])]:
                ids[name]=cc.emit(b,'VIEW_ORDER_'+name,s,dict(value=value),q,media=mm)
            colored=[m['role'] for m in media if any(x['color']=='red' for x in m.get('presentation',{}).get('boxes',[]))]
            if len(colored)==1:
                ls=dict(kind='value',domain='enum',values=[m['role'] for m in media],nullable=True)
                ids['MARKER_VIEW']=cc.emit(b,'MARKER_VIEW',ls,dict(value=colored[0]),'Which source view contains the red annotated bounding-box outline? Report its stable frame label, not its position in the current input order.')
            else:cc.gap(b,'MARKER_VIEW','NO_UNIQUE_SOURCE_RED_MARKER_VIEW')
            cc.gap(b,'LOCAL_FACT_AND_FUSION_ABLATION','PER_VIEW_RELATION_AND_SUFFICIENCY_WITNESS_NOT_YET_REPLAYED')
        else:cc.gap(b,'OBJECT_IDENTITY','SEPARATE_ENTITY_IDENTITY_GOLD_NOT_DERIVED_FROM_RELATION_ANSWER')
    cc.matched.append(dict(experiment='E8',world_cluster_id=b['world_cluster_id'],level=level,**ids))

def expand(cc,b,e6=False):
    at=atom(b['source']['pair']);s,value,q=spec(at)
    if at['predicate'] not in INV:raise ValueError('NONCOUNT_RELATION_REQUIRED')
    false=INV[value]; ids={};w=b['world_cluster_id']
    for wording in ('W0','W1'):
        qq=q if wording=='W0' else 'Using the supplied evidence and its stated reference frame, report the requested relation. '+q
        for name,role,cv in [('NEUTRAL','NEUTRAL',None),('TRUE','CANDIDATE',value),('FALSE','CANDIDATE',false),('SHAM','SHAM',false)]:
            extra='' if cv is None else ('CANDIDATE VALUE for the spatial query: '+cv+'.' if role=='CANDIDATE' else 'UNRELATED NON-SPATIAL REGISTER entry: '+cv+'. This entry is not a spatial observation.')
            ids[wording+'_'+name]=cc.emit(b,name,s,dict(value=value),qq,exp='E2',extra=extra,role=role,wording=wording)
        cc.matched.append(dict(experiment='E2',world_cluster_id=w,wording=wording,target_gold=value,candidate_value=false,
            neutral=ids[wording+'_NEUTRAL'],false=ids[wording+'_FALSE'],sham=ids[wording+'_SHAM'],binary_nonidentifying=True))
    if e6:
        for cv in (value,false):
            prefix='CANDIDATE VALUE for the spatial query: '+cv+'.'
            mid={};label='SUPPORTED' if cv==value else 'CONTRADICTORY'
            for form in ('FACT_ONLY','VERDICT_ONLY','FACT_FIRST','VERDICT_FIRST'):
                ss=dict(s);ss['kind']='value' if form=='FACT_ONLY' else 'verdict' if form=='VERDICT_ONLY' else 'joint'
                if ss['kind']=='joint':ss['order']=['value','verdict'] if form=='FACT_FIRST' else ['verdict','value']
                expected=dict(value=value) if ss['kind']=='value' else dict(verdict=label) if ss['kind']=='verdict' else dict(value=value,verdict=label)
                mid[form]=cc.emit(b,form,ss,expected,q,exp='E6',extra=prefix,role='CANDIDATE')
            cc.matched.append(dict(experiment='E6',world_cluster_id=w,target_gold=value,candidate_value=cv,**mid,binary_nonidentifying=True))
    cc.gap(b,'PROTECTED_FACT','SINGLE_QUERY_EXTENSION_NOT_MULTIFACT_PRESERVATION_CLAIM')

def main():
    a=arguments(__doc__).parse_args();c,root=setup(a)
    if a.dry_run:print('Source-only E8 <=8 calls/anchor and non-count paired expansion; no outputs read.');return
    src=root/'preparation/native_e8_c1_v1_20260910';dest=root/'preparation/breadth_v1_20260910'
    if (dest/'ACCEPTANCE.json').exists():print('ALREADY_COMPILED');return
    guard=source_guard();source=load(src/'PREPARATION_ACCEPTANCE.json')
    if source['status']!='NATIVE_EVIDENCE_AND_PARTIAL_ASSET_AUDIT_COMPLETE':raise ValueError('SOURCE_PREPARATION_INCOMPLETE')
    index=list(rows(src/'native_bundle_index.jsonl'));oldworlds=set()
    for path in (root/'batches').glob('ca_source_d*/manifest/world_allocation.jsonl'):
        oldworlds.update(r['world_cluster_id'] for r in rows(path))
    for path in (root/'batches').glob('ca_source_d*/private_gold/world_panel.jsonl'):oldworlds.update(r['world_cluster_id'] for r in rows(path))
    save(dest/'SELECTION_LOCK.json',dict(created_at=now(),seed=c['seed'],source_anchor_lock=entry(src/'NATIVE_ANCHOR_LOCK.json'),
        source_index=entry(src/'native_bundle_index.jsonl'),old_worlds=sorted(oldworlds),
        noncount_discovery_remaining=72,view_discovery_cap=40,e6_remaining=max(0,144-len(oldworlds)),
        rank='sha256([seed,BREADTH_NONCOUNT,world,level])',selection_before_predictions=True,code=entry(__file__)))
    nc=Compiler(c,root,NATIVE);ec=Compiler(c,root,EXPAND);eligible=[]
    for rec in index:
        verify([rec['bundle']]);b=load(rec['bundle']['path']);b['_ref']=rec['bundle']
        if b['status']!='EVIDENCE_BUNDLE_READY_FOR_TYPED_QUERY_COMPILER':nc.gap(b,'ALL',b['status']);continue
        try:
            before=len(nc.aliases);native(nc,b)
            if len(nc.aliases)-before>8:raise ValueError('E8_PER_ANCHOR_BUDGET_EXCEEDED')
            nc.panels.append(dict(world_cluster_id=b['world_cluster_id'],source_level=b['level'],bundle=rec['bundle']))
            at=atom(b['source']['pair'])
            if b['level'] in ('L1','L2','L3') and at['predicate'] in INV and at.get('polarity','positive')=='positive' and b['world_cluster_id'] not in oldworlds and all(m['kind']=='image' for m in b['original_requests'][0]['media']):eligible.append(b)
        except ValueError as exc:nc.gap(b,'REMAINING',str(exc))
    selected=set();nums=Counter();e6count=0
    for b in sorted(eligible,key=lambda b:digest([c['seed'],'BREADTH_NONCOUNT',b['world_cluster_id'],b['level']])):
        w=b['world_cluster_id'];family='VIEW_FRAME_IDENTITY' if b['level']=='L3' else 'NONCOUNT_RELATION';cap=40 if family=='VIEW_FRAME_IDENTITY' else 72
        if w in selected or nums[family]>=cap:continue
        # Structural selection only. Single fact worlds remain secondary, not protected-table evidence.
        try:expand(ec,b,e6=e6count<max(0,144-len(oldworlds)))
        except ValueError as exc:ec.gap(b,'ALL',str(exc));continue
        selected.add(w);nums[family]+=1;e6count+=1
        ec.panels.append(dict(world_cluster_id=w,primary_stratum=family,source_level=b['level'],bundle=b['_ref'],independent_facts=1,
            multifact_main_eligible=False,genuinely_multiview_necessity=False,binary_nonidentifying=True))
    # Fail closed on ordinary-payload answer/proof serialization and round-trip canonical gold parsing.
    from contracts import parse
    tests=0
    for cc in (nc,ec):
        for rid,r in cc.req.items():
            if set(r['payload'])!={'system','text','media'}:raise ValueError('UNSANITIZED_PAYLOAD')
            if any(x in r['payload']['text'] for x in ('source_record_hash','certificate_id','fact:','is_false','gold_label')):raise ValueError('PRIVATE_PAYLOAD_LEAK')
            expected=cc.gold[rid]['expected']; obj=copy.deepcopy(expected)
            if 'facts' in obj:obj['facts']=[dict(query_id=k,value=v) for k,v in obj['facts'].items()]
            parsed=parse(json.dumps(obj),r['schema'])
            if parsed['status']!='VALID' or parsed['component_values']!=expected:raise ValueError('GOLD_SCHEMA_ROUNDTRIP_FAILED')
            tests+=1
    setupcc=Compiler(c,root,'breadth_setup_v1_20260910')
    fixture=dict(world_cluster_id='sws:breadth:setup',level='SETUP',pair_id='synthetic:breadth:setup',
        _ref=dict(origin='SYNTHETIC_SYMBOLIC',code=entry(__file__)),original_requests=[dict(media=[])],
        source=dict(pair=dict(l4_origin='SYNTHETIC_SYMBOLIC',supported_claim=dict(normalized=dict(
            atoms=[dict(predicate='LEFT_OF',subject='A',object='B')],context=dict(scope='explicit_symbolic_records',reference_frame='declared',view_id='none'))))))
    cases=[
        (dict(kind='value',domain='enum',values=['LEFT_OF','RIGHT_OF'],nullable=True),dict(value='LEFT_OF'),'The symbolic relation record says A LEFT_OF B. Report the recorded relation.'),
        (dict(kind='facts',domain='enum',values=['LEFT_OF','RIGHT_OF'],query_ids=['q1','q2'],nullable=True),dict(facts={'q1':'LEFT_OF','q2':'RIGHT_OF'}),'Independent symbolic records: q1=LEFT_OF; q2=RIGHT_OF. Report both.'),
        (dict(kind='value',domain='enum',values=['frame_0','frame_1','frame_2'],nullable=True),dict(value='frame_2'),'The explicit annotation record says the red marker is in frame_2. Which frame is recorded?'),
        (dict(kind='facts',domain='count',query_ids=['q1','q2'],nullable=True),dict(facts={'q1':3,'q2':2}),'Independent symbolic counts: q1=3; q2=2. Report both.'),
        (dict(kind='value',domain='enum',values=['ADD','REMOVE','NO_CHANGE'],nullable=True),dict(value='REMOVE'),'The action removes one table. Classify its operation.'),
        (dict(kind='value',domain='enum',values=['LEFT_OF','RIGHT_OF'],nullable=True),dict(value=None),'The independent symbolic record contains no relation for A and B. Report the unknown value.')]
    for i,(ss,expected,qq) in enumerate(cases):setupcc.emit(fixture,'SETUP_'+str(i),ss,expected,qq,exp='SETUP')
    setupcc.panels.append(dict(world_cluster_id=fixture['world_cluster_id'],source_level='SETUP',source_type='SYNTHETIC_SYMBOLIC'))
    reports=[nc.publish()]
    if ec.req:reports.append(ec.publish())
    reports.append(setupcc.publish())
    save(dest/'ACCEPTANCE.json',dict(status='COMPILED_QUALIFIED_PARTS_PROCESSOR_PENDING',created_at=now(),job_id=os.environ['SLURM_JOB_ID'],
        batches=reports,source_only_guard=guard,gold_schema_roundtrips=tests,new_noncount_strata=dict(nums),
        native_levels_preserved=True,no_answer_based_selection=True,full_multiview_branch_complete=False,full_E8_conditions_complete=False))
    print(json.dumps(dict(batches=[{k:r[k] for k in ('batch','worlds','requests_per_model','gaps')} for r in reports],roundtrip_tests=tests)),flush=True)

if __name__=='__main__':main()
