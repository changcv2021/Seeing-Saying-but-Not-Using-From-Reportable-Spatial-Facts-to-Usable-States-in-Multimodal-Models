"""B0 fixed explicit-field scoring, including retained truncated prefixes; no judge."""
from b0common import *
sys.path.insert(0, str(A1CODE.parent/'src'))
from scorer import observed
sys.path.insert(0, str(A1CODE.parent/'format_repair_v2'))
from format_adapter_v2 import canonicalize

LABELS = ['SUPPORTED','CONTRADICTORY','UNKNOWN']
VERSION = 'b0_explicit_fields_order_legacy_alias_v1'


def parse(raw, schema):
    if raw is None: return dict(status='NOT_RUN',fact_present=False,verdict_present=False)
    if raw.get('infrastructure_error'): return dict(status='INFRA_FAILURE',fact_present=False,verdict_present=False)
    original, complete = observed(raw.get('raw_response',''),raw.get('truncated',False))
    canonical, audit = canonicalize(raw,schema)
    obj = original
    if audit['normalization']=='ALIAS_QUERY_VALUE_TO_VALUE':
        obj=audit['canonical_object']
    if audit['normalization'].startswith('REJECT_'): obj={}
    kind=schema['kind']; fk='target_value' if kind=='fact_verdict' else 'value'
    vk='verdict' if kind=='fact_verdict' else 'label'
    keys=[fk,vk] if kind=='fact_verdict' else [fk] if kind=='value' else [vk]
    fact_present=kind!='verdict' and fk in obj and (obj[fk] is None or type(obj[fk]) is int and obj[fk]>=0)
    verdict_present=kind!='value' and vk in obj and isinstance(obj[vk],str) and obj[vk] in LABELS
    valid=set(obj)==set(keys) and (kind=='verdict' or fact_present) and (kind=='value' or verdict_present)
    return dict(status=('NULL' if kind=='value' and obj.get(fk) is None else 'VALID') if valid else 'INVALID',
        fact_present=bool(fact_present),fact_pred=obj.get(fk) if fact_present else None,
        verdict_present=bool(verdict_present),pred_verdict=obj.get(vk) if verdict_present else None,
        schema_valid=bool(valid),json_complete=complete,key_order=list(obj),
        order_compliant=list(obj)==schema.get('order') if kind=='fact_verdict' else None,
        strict_contract_ok=valid and complete and audit['normalization']=='NONE',observed_object=obj,
        original_object=original,normalization=audit['normalization'],
        truncated=bool(raw.get('truncated')),parser_version=VERSION)


def score(raw, gold):
    p=parse(raw,gold['schema']); available=p['status'] not in ['NOT_RUN','INFRA_FAILURE']
    p.update(fact_correct=None,verdict_correct=None,self_consistency_violation=None,
             same_run_fact_correct_verdict_wrong=None,correct=None)
    if not available: return p
    kind=gold['schema']['kind']
    if kind!='verdict':
        p['fact_correct']=bool(p['fact_present'] and type(p['fact_pred']) is type(gold['fact_gold']) and p['fact_pred']==gold['fact_gold'])
    if kind!='value': p['verdict_correct']=bool(p['verdict_present'] and p['pred_verdict']==gold['gold_verdict'])
    if kind=='fact_verdict' and p['schema_valid'] and type(p['fact_pred']) is int:
        implied='SUPPORTED' if p['fact_pred']==gold['claim_value'] else 'CONTRADICTORY'
        p['self_consistency_violation']=p['pred_verdict']!=implied
        p['same_run_fact_correct_verdict_wrong']=p['fact_correct'] and not p['verdict_correct']
    p['correct']=bool(p['fact_correct'] if kind=='value' else p['verdict_correct'] if kind=='verdict' else p['fact_correct'] and p['verdict_correct'])
    return p
