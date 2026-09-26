"""Bounded source-only non-count discovery; never fill missing visual truth by inference."""
from collections import Counter
from v2_common import *
from breadth_v1.compile import atom,spec,entity,scope,contract
INV={'LEFT_OF':'RIGHT_OF','RIGHT_OF':'LEFT_OF','ABOVE':'BELOW','BELOW':'ABOVE','FRONT_OF':'BEHIND','BEHIND':'FRONT_OF'}
FAMILY={'LEFT_OF':'HORIZONTAL','RIGHT_OF':'HORIZONTAL','ABOVE':'VERTICAL','BELOW':'VERTICAL','FRONT_OF':'DEPTH','BEHIND':'DEPTH'}
def main():
    a=cli(__doc__).parse_args();c,root=context(a)
    from data_continuation_v1.prepare import source_guard
    audit=source_guard();sws=Path(load(SWS_CODE/'config_auto_v2.json')['root']);src=sws/'preparation/native_e8_c1_v1_20260910'
    index=list(rows(src/'native_bundle_index.jsonl'));candidates=[];gaps=[];sources=[]
    # Only source-backed single observed relations, not composed L2 conclusions or L4 post gold.
    for rec in index:
        check(rec['bundle']);b=load(rec['bundle']['path'])
        if b['level']!='L1':continue
        if b['status']!='EVIDENCE_BUNDLE_READY_FOR_TYPED_QUERY_COMPILER':gaps.append(dict(world=b['world_cluster_id'],reason=b['status']));continue
        at=atom(b['source']['pair'])
        if at['predicate'] not in INV:continue
        matches=[f for f in b['matching_source_facts'] if f['fact']['predicate']==at['predicate'] and f['fact']['subject']==at['subject']
                 and f['fact'].get('object')==at['object'] and f['fact'].get('polarity','positive')=='positive' and f['fact'].get('derivation') is None]
        if not matches:gaps.append(dict(world=b['world_cluster_id'],reason='NO_DIRECT_UNDERIVED_SOURCE_FACT'));continue
        if any(m['kind']!='image' for m in b['original_requests'][0]['media']):continue
        if b['split'] not in ['train','dev','discovery','exploration']:gaps.append(dict(world=b['world_cluster_id'],reason='NOT_DISCOVERY_MEMBERSHIP:'+b['split']));continue
        try:s,val,q=spec(at)
        except ValueError as exc:gaps.append(dict(world=b['world_cluster_id'],reason=str(exc)));continue
        # source graph already bound into bundle; verify actual media and keep full source context.
        for media in b['original_requests'][0]['media']:check(dict(path=media['path'],sha256=media['sha256']))
        b['_ref']=rec['bundle'];b['_fact']=matches[0];b['_schema']=s;b['_query']=q;b['_value']=val;candidates.append(b)
    candidates.sort(key=lambda b:digest([SEED,'NONCOUNT_SOURCE_ONLY',b['world_cluster_id'],b['pair_id']]))
    selected=[];worlds=set();families=Counter()
    # round-robin family sampling, capped at 60 independent worlds before outputs.
    available=sorted({FAMILY[b['_value']] for b in candidates})
    while len(selected)<60:
        changed=False
        for family in available:
            b=next((b for b in candidates if FAMILY[b['_value']]==family and b['world_cluster_id'] not in worlds),None)
            if b is not None:
                selected.append(b);worlds.add(b['world_cluster_id']);families[family]+=1;changed=True
                if len(selected)==60:break
        if not changed:break
    out=ROOT/'NONCOUNT_PREPARATION';save(out/'GAPS.jsonl',gaps,'jsonl')
    save(out/'INVENTORY.json',dict(source_index=entry(src/'native_bundle_index.jsonl'),eligible_bundles=len(candidates),selected_worlds=len(selected),
        selected_families=dict(families),source_only_guard=audit,scope='Direct L1 source facts; hypothetical coordinate reflections, not physical object motion and not native release L4.',
        scientific_grade='PILOT_ONLY' if len(selected)<20 or len(families)<2 else 'BOUNDED_NONCOUNT_BEHAVIOR',
        prohibited_generalization='No evidence for complex 3D motion, object identity tracking, or mechanism replication from binary relation behavior alone.'))
    if not selected:return
    template=next(rows(OLD_ROOT/'batches/B2/public_inputs/requests.jsonl'));reqs=[];gold=[];panel=[]
    for b in selected:
        at=atom(b['source']['pair']);s=b['_schema'];s0=b['_value'];axis=FAMILY[s0];opposite=INV[s0];q=b['_query'];w=b['world_cluster_id']
        base=copy.deepcopy(template);base['payload']['media']=b['original_requests'][0]['media'];base['schema']=s;base['split']='DISCOVERY_HISTORY'
        base['sample_family']='NONCOUNT_'+axis;base['source_type']='SOURCE_SUPPORTED_FRAME_TRANSFORMATION';base['view_variant']='FULL'
        ctx=scope(b['source']['pair'],b['original_requests'][0])+'\nAll images show S0, the original observed scene.\nIMAGE ORDER: '+', '.join(str(i+1)+'='+m['role'] for i,m in enumerate(base['payload']['media']))+'\n'
        # Reflections give lawful deterministic inversion without synthesizing visual annotations.
        action='Reverse only the '+axis.lower()+' coordinate axis of the named reference frame; preserve the objects and their identities.'
        actions='S0 is the original frame. Action 1 produces S1. Action 2 acts on S1 to produce S2. These are coordinate-frame transformations, not new images or physical movements.\nACTION_1: '+action+'\nACTION_2: Leave the transformed frame and objects unchanged.'
        initial='ORACLE INITIAL FACT: In S0, '+entity(at['subject'])+' has relation '+s0+' to '+entity(at['object'])+'.\n'
        sham='UNRELATED REGISTER: A separate bookkeeping entry stores the relation code '+s0+'; it is not a fact about these objects.\n'
        definitions='Use the named state and reference frame. QUERY: '+q
        conditions=[('DIRECT_S0',ctx+'TARGET: S0\n'+definitions,s0,'S0'),
            ('FULL_TRANSITION',ctx+actions+'\nTARGET: S2\n'+definitions,opposite,'S2'),
            ('EXPLICIT_S0',ctx+initial+actions+'\nTARGET: S2\n'+definitions,opposite,'S2'),
            ('MATCHED_SHAM',ctx+sham+actions+'\nTARGET: S2\n'+definitions,opposite,'S2')]
        ids={}
        for name,text,value,target in conditions:
            r=request(base,'NONCOUNT',name,text+'\nOUTPUT CONTRACT: '+contract(s)+'\nMaximum 512 output tokens.',target,w)
            reqs.append(r);ids[name]=r['request_id'];gold.append(dict(request_id=r['request_id'],world_cluster_id=w,expected=dict(value=value),
                proof=dict(bundle=b['_ref'],direct_source_fact=b['_fact'],s0=s0,s1=opposite,s2=opposite,law='single-axis coordinate reflection then identity',family=axis)))
        panel.append(dict(world_cluster_id=w,source_bundle=b['_ref'],source_pair=b['pair_id'],family=axis,requests=ids,s0=s0,s1=opposite,s2=opposite))
        sources.append(b['_ref'])
    publish('NONCOUNT',reqs,gold,panel,dict(source_guard=audit,selection='Source-only family-balanced hash; <=60 worlds; all three identical panels',
        interpretation='Binary frame-transformation behavior control only; not Wrong-State Selection evidence',no_native_L4_claim=True,
        actions='One axial frame reflection followed by identity. Repeated frame transformations are bounded controls, not general physical spatial updates.'),
        [entry(src/'native_bundle_index.jsonl'),*sources],Path(__file__))
if __name__=='__main__':main()
