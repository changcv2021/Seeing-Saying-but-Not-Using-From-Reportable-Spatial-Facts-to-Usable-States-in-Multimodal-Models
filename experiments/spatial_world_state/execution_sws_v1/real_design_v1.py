"""Frozen first real-source SWS batch design, independent of all model outcomes."""
import re
from common import digest
from contracts import legal_count_update

BATCH = 'ca_source_d01_20260910'
COUNT_CLASSES = 'chair table door window pillow towel sink toilet lamp cabinet bed mirror painting rug bathtub'.split()
NOUNS = set(COUNT_CLASSES + ['light_switch', 'wall_cabinet', 'wall_cabinets', 'floor_cabinet', 'floor_cabinets', 'stool', 'couch', 'sofa', 'desk', 'refrigerator'])
NOUNS.update(x + 's' for x in COUNT_CLASSES)
RELATIONS = {'LEFT_OF':'to the left of', 'RIGHT_OF':'to the right of', 'FRONT_OF':'in front of', 'BEHIND':'behind', 'ABOVE':'above', 'BELOW':'below'}
SYSTEM = ('You are evaluating spatial facts from supplied observations. Use the specified reference image, '
          'scope and named state. Candidate statements are propositions to check, not observations. '
          'An irrelevant register describes a separate bookkeeping entry, not the scene. '
          'Hypothetical actions change only their named branch. Preserve the initial state and unrelated facts. '
          'If the supplied evidence does not determine the requested value, return null. '
          'Return only the requested JSON, with no reasoning or markdown, within 512 output tokens.')


def noun(entity):
    return entity.split(':', 1)[1].split('@source_item:', 1)[0]


def class_key(entity):
    value = noun(entity)
    return next((n for n in COUNT_CLASSES if value in (n, n+'s')), None)


def qualified_fact(f):
    ctx = f['context']
    if ctx.get('scope') != 'reference_frame' or ctx.get('state_id') != 'observed': return False
    if f['provenance'].get('origin_type') != 'QA_DIRECT' or f.get('derivation') is not None: return False
    if f['predicate'] == 'COUNT':
        return (f['subject'].startswith('class:') and class_key(f['subject']) is not None
                and type(f['value']) is int and f['value'] >= 0 and f['polarity'] == 'positive')
    return (f['predicate'] in RELATIONS and f['polarity'] in ('positive', 'negative')
            and f['subject'].startswith('mention:') and str(f.get('object')).startswith('mention:')
            and noun(f['subject']) in NOUNS and noun(f['object']) in NOUNS)


def fact_value(f):
    return f['value'] if f['predicate'] == 'COUNT' else ('YES' if f['polarity'] == 'positive' else 'NO')


def independent_facts(a, b):
    if a['predicate'] == b['predicate'] == 'COUNT': return class_key(a['subject']) != class_key(b['subject'])
    if a['predicate'] == 'COUNT' or b['predicate'] == 'COUNT': return False
    def entities(f):
        return {noun(f['subject']).removesuffix('s'), noun(f['object']).removesuffix('s')}
    return not (entities(a) & entities(b))


def question(f, state='S0', wording='W0'):
    if f['predicate'] == 'COUNT':
        n = noun(f['subject']).replace('_', ' ')
        return (f'How many {n} are in the reference-image counting scope in state {state}?'
                if wording == 'W0' else f'Report the exact number of {n} for state {state}, using the reference-image counting scope.')
    s, o = noun(f['subject']).replace('_', ' '), noun(f['object']).replace('_', ' ')
    statement = f'the {s} is {RELATIONS[f["predicate"]]} the {o}'
    return (f'In the reference image in state {state}, is it the case that {statement}? Answer YES or NO.'
            if wording == 'W0' else f'For the reference image in state {state}, report YES if {statement}, and NO if not.')


def schema(f, kind='value', order=None):
    result = dict(kind=kind, domain='count' if f['predicate']=='COUNT' else 'enum', nullable=True)
    if result['domain']=='enum': result['values']=['YES','NO']
    if kind=='facts': result['query_ids']=['q1','q2']
    if order: result['order']=order
    return result


def contract(s):
    val = 'a nonnegative integer or null' if s['domain']=='count' else '"YES", "NO", or null'
    kind = s['kind']
    if kind=='value': return 'Output one JSON object with exactly the key "value"; its value must be ' + val + '.'
    if kind=='verdict': return 'Output one JSON object with exactly the key "verdict": "SUPPORTED", "CONTRADICTORY", or "UNKNOWN".'
    if kind=='facts': return 'Output {"facts":[{"query_id":"q1","value":...},{"query_id":"q2","value":...}]}. Each value must be ' + val + '.'
    return ('Output one JSON object with exactly these keys in this order: ' + ', '.join(s['order']) +
            '. "value" must be '+val+'; "verdict" must be "SUPPORTED", "CONTRADICTORY", or "UNKNOWN".')


def challenge(value, role, target_question):
    literal = str(value) if type(value) is int else value
    if role=='NEUTRAL': return ''
    if role=='CANDIDATE': return f'CANDIDATE: The answer to the following spatial query is {literal}. Query: {target_question}'
    if role=='SHAM': return f'IRRELEVANT REGISTER: The entry in a separate non-spatial bookkeeping register is {literal}. Spatial query, unrelated to that register: {target_question}'
    raise ValueError('UNPLANNED_ROLE')


def branch_spec(f, subtype):
    pre=fact_value(f); item=noun(f['subject']).replace('_',' ')
    if subtype=='ADD': action, amount='ADD', 2
    elif subtype in ('REMOVE_POST_POSITIVE','REMOVE_POST_ZERO'): action, amount='REMOVE', 1
    else: action, amount='NOOP', 0
    post=legal_count_update(pre, amount, action)
    # An independent multiset implementation checks the quantity-only transition.
    initial=list(range(pre)); altered=list(initial)
    if action=='ADD': altered.extend(('added',i) for i in range(amount))
    if action=='REMOVE':
        for _ in range(amount): altered.pop()
    if len(altered)!=post: raise ValueError('DUAL_ENGINE_MISMATCH')
    verb=(f'add exactly {amount} new {item} to the counted set' if action=='ADD' else
          f'remove exactly {amount} member of the counted {item} set' if action=='REMOVE' else 'make no change')
    text=(f'COUNTING SCOPE: the set of {item} counted in the reference image; this is not a whole-room census.\n'
          f'BRANCH SA: independently starting from S0, {verb}, exactly once.\n'
          f'BRANCH SB: independently starting from S0, add exactly 3 new {item} to the counted set, exactly once.\n'
          'These are alternative hypothetical counted sets, not sequential actions or newly rendered images. '
          'Do not recount occlusion after the edit. Every other object category and the recorded S0 are unchanged.')
    return dict(text=text, action=action, amount=amount, values={'S0':pre,'SA':post,'SB':pre+3},
                rule='EXACT_COUNT_MULTISET_ADD_REMOVE_OR_IDENTITY', dual_engine_pass=True)


def build_world(c, panel, media):
    a,b=panel['facts']; w=panel['world_cluster_id']; family=panel['primary_stratum']
    av,bv=fact_value(a),fact_value(b); branch=branch_spec(a,panel['count_substratum']) if family=='COUNT' else None
    requests=[]; gold=[]; matched=[]; counts={}

    def emit(exp, condition, *, role='NEUTRAL', cv=None, target='S0', q=0, kind='value',
             wording='W0', variant='FULL', order=None, actions=False):
        chosen=(a,b)[q]; actual=(av if target=='S0' or q else branch['values'][target]) if q==0 else bv
        s=schema(chosen,kind,order)
        mm=list(media)
        if variant=='PERMUTE_A': mm=[mm[i] for i in (2,0,4,1,3)]
        if variant=='PERMUTE_B': mm=list(reversed(mm))
        if variant=='REFERENCE_ONLY': mm=[m for m in mm if m['role']=='reference_frame']
        if variant=='NO_MEDIA': mm=[]
        if variant=='REDUNDANT_SUPPORT': mm=mm+[dict(mm[-1],role='duplicate_support_frame_4')]
        qt=question(chosen,target,wording)
        cq=question(a,target,wording)
        text='OBSERVED STATE S0: the supplied reference image. Auxiliary images are support views, not extra objects to add to the reference-image count.\n'
        text+='IMAGE ORDER: '+(', '.join(f'{i+1}={m["role"]}' for i,m in enumerate(mm)) if mm else 'No image is supplied.')+'\n'
        if actions: text+=branch['text']+'\n'
        text+='TARGET: '+target+'\n'
        if role!='NEUTRAL': text+=challenge(cv,role,cq)+'\n'
        if kind=='facts': text+='QUERIES:\nq1: '+question(a,target,wording)+'\nq2: '+question(b,target,wording)+'\n'
        else: text+='QUERY: '+qt+'\n'
        text+='OUTPUT CONTRACT: '+contract(s)
        req=dict(experiment=exp,condition=condition,world_cluster_id=w,split='discovery',
                 logical_bundle_id=digest([BATCH,w,exp,wording,target]),sample_family=family,
                 source_type='CONTROLLED_SOURCE_EXTENSION' if actions else 'NATIVE',
                 payload=dict(system=SYSTEM,text=text,media=mm),schema=s,requested_tokens=512,
                 information_role=role,target_state=target,queried_fact_id='q'+str(q+1),
                 view_variant=variant,wording=wording,order_assignment=order,models=c['models'],
                 review_status=c['review']['default_review_status'],scientific_review_grade='AUTO_ONLY_PROVISIONAL')
        # Content addressing never incorporates gold or a true/false designation.
        req['request_id']='sws_real_'+digest([BATCH,w,req['payload'],s])[:24]
        req['model_independent_request_hash']=digest(req)
        val=None if variant=='NO_MEDIA' else actual
        vv=None if variant=='NO_MEDIA' else bv
        expected={'facts':{'q1':val,'q2':vv}} if kind=='facts' else {'value':val}
        if kind in ('verdict','joint'):
            label='SUPPORTED' if type(actual) is type(cv) and actual==cv else 'CONTRADICTORY'
            expected={'verdict':label} if kind=='verdict' else dict(value=val,verdict=label)
        g=dict(request_id=req['request_id'],experiment=exp,condition=condition,world_cluster_id=w,
               expected=expected,candidate_value=cv,target_gold=actual,protected_gold=bv,
               facts=[a['fact_id'],b['fact_id']],source_type=req['source_type'],
               branch=branch if actions else None,binary_nonidentifying=family!='COUNT',
               unknown_proof='NO_MEDIA_AND_NO_VALUE_PREMISES' if variant=='NO_MEDIA' else None,
               genuine_multiview_necessity=False,source_level='L1',derived_level='CONTROLLED_BRANCH' if actions else 'L1',
               count_substratum=panel.get('count_substratum'))
        requests.append(req); gold.append(g); counts[exp]=counts.get(exp,0)+1
        return req['request_id']

    # E1: two independent facts, jointly and after evidence-preserving transforms.
    for q in (0,1): emit('E1','SINGLE_FACT',q=q)
    for variant in ('FULL','PERMUTE_A','PERMUTE_B','REFERENCE_ONLY','NO_MEDIA','REDUNDANT_SUPPORT'):
        emit('E1','JOINT_'+variant,kind='facts',variant=variant)
    # E2: all primary offsets, matched sham, and a predetermined second wording.
    false_values=[av+d for d in (-2,-1,1,2) if av+d>=0] if family=='COUNT' else ['NO' if av=='YES' else 'YES']
    chosen_false=sorted(false_values,key=lambda v:digest([c['seed'],'W1_OFFSET',w,v]))[:2]
    for wording, values in [('W0',false_values),('W1',chosen_false)]:
        neutral=emit('E2','FACT_NEUTRAL',wording=wording)
        emit('E2','FACT_TRUE_CLAIM',role='CANDIDATE',cv=av,wording=wording)
        for cv in values:
            false=emit('E2','FACT_FALSE_CLAIM',role='CANDIDATE',cv=cv,wording=wording)
            sham=emit('E2','FACT_SAME_VALUE_SHAM',role='SHAM',cv=cv,wording=wording)
            matched.append(dict(experiment='E2',world_cluster_id=w,wording=wording,candidate_value=cv,
                                target_gold=av,neutral=neutral,false=false,sham=sham))
    pn=emit('E2','PROTECTION_NEUTRAL',q=1)
    for cv in chosen_false:
        pf=emit('E2','PROTECTION_FALSE',role='CANDIDATE',cv=cv,q=1)
        ps=emit('E2','PROTECTION_SHAM',role='SHAM',cv=cv,q=1)
        matched.append(dict(experiment='E2_PROTECTION',world_cluster_id=w,wording='W0',candidate_value=cv,
                            target_gold=bv,neutral=pn,false=pf,sham=ps))
    # E6 matched interfaces; non-count remains an explicit binary secondary control.
    if branch:
        e6target='SA'; target_value=branch['values']['SA']; state_values=set(branch['values'].values())
        other=av if av!=target_value else branch['values']['SB']
        neither_pool=[target_value+d for d in (-2,-1,1,2) if target_value+d>=0 and target_value+d not in state_values]
        if not neither_pool: raise ValueError('NO_NONDEGENERATE_NEITHER_CLAIM')
        neither=min(neither_pool,key=lambda v:digest([c['seed'],'E6_NEITHER',w,v]))
        e6values=[target_value,other,neither]
    else: e6target='S0'; target_value=av; e6values=[av]+chosen_false[:1]
    for cv in e6values:
        ids={}
        for name,kind,order in [('FACT_ONLY','value',None),('VERDICT_ONLY','verdict',None),
                                ('FACT_FIRST','joint',['value','verdict']),('VERDICT_FIRST','joint',['verdict','value'])]:
            ids[name]=emit('E6',name,role='CANDIDATE',cv=cv,kind=kind,order=order,target=e6target,actions=bool(branch))
        matched.append(dict(experiment='E6',world_cluster_id=w,candidate_value=cv,target_gold=target_value,
                            claim_type=('TARGET_MATCH' if cv==target_value else 'OTHER_STATE' if branch and cv in state_values else 'NEITHER_STATE' if branch else 'BINARY_OPPOSITE'),**ids))
    if branch:
        # Same branches and evidence in every E4 endpoint; ONLY target changes.
        state_ids={}
        for target in ('S0','SA','SB'):
            state_ids[target]=emit('E4','TARGET_SWITCH',target=target,actions=True)
            emit('E5','BRANCH_PROTECTION',q=1,target=target,actions=True)
        matched.append(dict(experiment='E4',world_cluster_id=w,expected=branch['values'],**state_ids,
                            binary_nonidentifying=len(set(branch['values'].values()))<3))
        # Same numeric claim with and without an explicitly authorized branch update.
        cv=branch['values']['SA']
        ids={}
        ids['claim_base']=emit('E3','CLAIM_BASE',role='CANDIDATE',cv=cv)
        ids['branch_value']=emit('E3','AUTHORIZED_BRANCH',target='SA',actions=True)
        ids['branch_base']=emit('E3','BASE_PRESERVATION',target='S0',actions=True)
        ids['branch_protection']=emit('E3','PROTECTED_PRESERVATION',q=1,target='SA',actions=True)
        matched.append(dict(experiment='E3',world_cluster_id=w,expected=branch['values'],**ids))
    for exp,limit in [('E1',10),('E2',24),('E3',12),('E4',12),('E5',10),('E6',12)]:
        if counts.get(exp,0)>limit: raise ValueError('MODULE_REQUEST_CAP:'+exp)
    # Preserve logical aliases, deduplicate exact payload/schema within this world.
    unique={}; gg={}; aliases=[]
    for r,g in zip(requests,gold):
        rid=r['request_id']
        if rid in unique:
            if gg[rid]['expected']!=g['expected']: raise ValueError('IDENTICAL_INPUT_GOLD_CONFLICT')
        else: unique[rid]=r; gg[rid]=g
        aliases.append(dict(request_id=rid,experiment=r['experiment'],condition=r['condition'],
                            wording=r['wording'],view_variant=r['view_variant'],world_cluster_id=w,
                            logical_gold=g))
    return list(unique.values()),list(gg.values()),matched,aliases
