"""Exact response normalization and cluster-aware reporting; no model judges."""
import collections
import re
import random
import math
from base import *
sys.path.insert(0,str(CODE/'reference/SpaceConflict_PhaseA_v2'))
from reference_metrics import (SwitchPair,switch_summary,classify_joint_map,classify_value_response,paired_cluster_effect,zero_event_upper_bound)

def observed_object(raw,truncated=False):
    text=clean_json(raw,truncated)
    try:
        obj=json.loads(text,object_pairs_hook=reject_dupes)
        return obj if isinstance(obj,dict) else {}
    except (ValueError,TypeError):
        if not truncated or not text.startswith('{'): return {}
    dec=json.JSONDecoder(object_pairs_hook=reject_dupes); got={}; i=1
    while i<len(text):
        while i<len(text) and text[i].isspace(): i+=1
        if i==len(text): break
        try: key,end=dec.raw_decode(text,i)
        except ValueError: break
        if not isinstance(key,str) or key in got: return {}
        i=end
        while i<len(text) and text[i].isspace(): i+=1
        if i==len(text): break
        if text[i]!=':': return {}
        i+=1
        while i<len(text) and text[i].isspace(): i+=1
        try: val,end=dec.raw_decode(text,i)
        except ValueError: break
        # An integer at the exact cutoff may be an unfinished multi-digit value.
        if end==len(text) and type(val) in (int,float): break
        got[key]=val; i=end
        while i<len(text) and text[i].isspace(): i+=1
        if i==len(text): break
        if text[i]=='}':
            if text[i+1:].strip(): return {}
            break
        if text[i]!=',': return {}
        i+=1
    return got

def value_response(obj,domain):
    if not isinstance(obj,dict): return 'INVALID',None
    if obj.get('status')=='UNDETERMINED' and obj.get('value') is None: return 'UNDETERMINED',None
    if obj.get('status')!='VALUE': return 'INVALID',None
    val=obj.get('value')
    if domain['type']=='nonnegative_integer':
        return ('VALUE',val) if type(val)==int and val>=0 else ('INVALID',None)
    aliases={'left':'LEFT_OF','right':'RIGHT_OF','front':'FRONT_OF','behind':'BEHIND','above':'ABOVE','below':'BELOW'}
    if isinstance(val,str): val=aliases.get(val.strip().lower(),val.strip().upper())
    return ('VALUE',val) if val in domain.get('values',[]) else ('INVALID',None)

def parse(raw,gold):
    if raw is None: return dict(status='NOT_RUN',correct=None)
    if raw.get('infrastructure_error'): return dict(status='INVALID',correct=False)
    text=raw.get('raw_response',''); truncated=raw.get('truncated',False)
    obj=observed_object(text,truncated); kind=gold['kind']
    if kind=='verdict':
        try: lab=parse_label(text,truncated,mapping=gold.get('mapping'),field=gold.get('field','label'))
        except (TypeError,ValueError): lab='INVALID'
        return dict(status='VALID' if lab in LABELS else 'INVALID',label=lab,correct=lab==gold['label'])
    if kind=='value':
        status,value=value_response(obj,gold['domain'])
        return dict(status=status,value=value,correct=status=='VALUE' and value==gold['value'])
    if kind=='joint':
        if set(obj)-set(gold['gold_by_state']): return dict(status='INVALID',values={},classifier='INCOMPLETE_OR_INVALID',correct=False)
        vals={}; valid={}; warnings=[]
        for s in gold['gold_by_state']:
            entry=obj.get(s)
            # The frozen joint contract permits status UNDETERMINED but does not
            # explicitly require a null placeholder. Never score that placeholder
            # as a claimed fact value, even when it happens to equal gold.
            if isinstance(entry,dict) and entry.get('status')=='UNDETERMINED':
                status,val=('INVALID' if gold.get('require_null_for_undetermined') and entry.get('value') is not None else 'UNDETERMINED'),None
                if entry.get('value') is not None: warnings.append(s+':UNDETERMINED_WITH_NON_NULL_PLACEHOLDER')
            else: status,val=value_response(entry,gold['domain'])
            vals[s]=val; valid[s]=status
        classification=classify_joint_map(gold['gold_by_state'],vals)
        return dict(status='VALID' if all(v in ['VALUE','UNDETERMINED'] for v in valid.values()) else 'INVALID',values=vals,state_statuses=valid,schema_warnings=warnings,classifier=classification,correct=classification=='EXACT')
    if kind=='action':
        if obj.get('status')=='UNDETERMINED': return dict(status='UNDETERMINED',correct=False,operation_correct=False,target_correct=False,scope_correct=False)
        op=obj.get('operation'); target=obj.get('target'); scope=obj.get('scope')
        terms=gold.get('target_terms',[gold.get('target','')])
        target_ok=isinstance(target,str) and bool(terms) and all(t and re.search(r'(?<!\w)'+re.escape(t.casefold())+r'(?!\w)',target.casefold()) for t in terms)
        valid=obj.get('status')=='RESOLVED' and isinstance(target,str) and op in ['REMOVE','ADD','REPLACE','MOVE','SWAP'] and isinstance(scope,str)
        return dict(status='VALID' if valid else 'INVALID',operation=op,target=target,scope=scope,
                    operation_correct=op==gold['operation'],target_correct=bool(target_ok),scope_correct=scope==gold['scope'],correct=bool(valid and op==gold['operation'] and target_ok and scope==gold['scope']),target_metric='LEXICAL_AUXILIARY_NOT_SEMANTIC_GOLD')
    raise ValueError('UNSUPPORTED_SCORE_KIND')

def estimate(records,field='correct',repetitions=2000):
    rr=[r for r in records if r.get(field) is not None]
    effect=paired_cluster_effect([(r['cluster_id'],int(r[field]),0) for r in rr],repetitions=repetitions)
    result=dict(numerator=sum(bool(r[field]) for r in rr),denominator=len(rr),clusters=effect['n_clusters'],estimate=effect['effect'],ci95=effect['ci95'],warning=effect['warning'],zero_event_cluster_upper95=None)
    if rr and not any(r[field] for r in rr): result['zero_event_cluster_upper95']=zero_event_upper_bound(effect['n_clusters'])
    return result

def conditional_estimate(records,field='correct',predicate='ALL',repetitions=2000,seed=20260907):
    """Resample the entire cohort of worlds, not only worlds passing the predicate."""
    worlds=collections.defaultdict(list)
    for r in records:
        if r.get(field) is not None: worlds[r['cluster_id']].append(r)
    parts=[]
    for key in sorted(worlds):
        eligible=[r for r in worlds[key] if predicate=='ALL' or r.get(predicate) is True]
        parts.append((sum(bool(r[field]) for r in eligible),len(eligible)))
    ratios=[n/d for n,d in parts if d]
    rng=random.Random(seed); draws=[]; empty=0
    for _ in range(repetitions):
        chosen=[rng.choice(parts) for _ in parts]
        # Numerators/denominators are reevaluated for every resampled world.
        values=[n/d for n,d in chosen if d]
        if values: draws.append(sum(values)/len(values))
        else: empty+=1
    draws.sort()
    def percentile(p):
        x=p*(len(draws)-1); lo=math.floor(x); hi=math.ceil(x)
        return draws[lo]+(draws[hi]-draws[lo])*(x-lo)
    return dict(numerator=sum(n for n,d in parts),denominator=sum(d for n,d in parts),clusters=sum(d>0 for n,d in parts),cohort_clusters=len(parts),
        estimate=sum(ratios)/len(ratios) if ratios else None,ci95=[percentile(.025),percentile(.975)] if draws else None,
        zero_denominator_bootstrap_fraction=empty/repetitions,warning='CONDITIONAL_DESCRIPTIVE_CLUSTER_MACRO; empty bootstrap draws recorded, not scored zero')
