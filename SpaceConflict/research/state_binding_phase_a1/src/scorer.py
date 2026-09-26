"""A1 deterministic scoring of explicit retained fields; no LLM judge or gold guessing."""
import json
import re
from interfaces import LABELS, OPERATIONS

VERSION='a1_exact_fields_retained_prefix_v1'

def unique(pairs):
    obj={}
    for k,v in pairs:
        if k in obj: raise ValueError('DUPLICATE_FIELD')
        obj[k]=v
    return obj

def observed(text,truncated=False):
    text=text.strip()
    try:
        obj=json.loads(text,object_pairs_hook=unique)
        if isinstance(obj,dict): return obj,True
        return {},False
    except (ValueError,TypeError):
        if not truncated or not text.startswith('{'): return {},False
    # A truncated output is not automatically invalid. Only completed fields count.
    dec=json.JSONDecoder(object_pairs_hook=unique); obj={}; i=1
    while i<len(text):
        while i<len(text) and text[i].isspace(): i+=1
        if i==len(text): break
        try: key,end=dec.raw_decode(text,i)
        except ValueError: break
        if not isinstance(key,str) or key in obj: return {},False
        i=end
        while i<len(text) and text[i].isspace(): i+=1
        if i==len(text): break
        if text[i]!=':': return {},False
        i+=1
        while i<len(text) and text[i].isspace(): i+=1
        try: val,end=dec.raw_decode(text,i)
        except ValueError: break
        if end==len(text) and type(val) in (int,float): break
        # Incomplete numeric exponents, decimal fractions, booleans cannot be inferred.
        if end<len(text) and text[end] not in ',} \r\n\t': return {},False
        obj[key]=val; i=end
        while i<len(text) and text[i].isspace(): i+=1
        if i==len(text): break
        if text[i]=='}':
            if text[i+1:].strip(): return {},False
            break
        if text[i]!=',': return {},False
        i+=1
    return obj,False

def scalar_ok(value,schema):
    if value is None: return bool(schema.get('nullable'))
    if schema['domain']=='count': return type(value)==int and value>=0
    return isinstance(value,str) and value in schema['domain']

def score(raw,gold):
    if raw is None: return dict(status='NOT_RUN',schema_valid=None,json_valid=None,correct=None,pred=None)
    obj,jsonvalid=observed(raw.get('raw_response',''),raw.get('truncated',False))
    s=gold['schema']; kind=s['kind']; expected=gold['expected']; valid=False; pred=None
    if kind=='value':
        pred=obj.get('value'); valid=set(obj)=={'value'} and scalar_ok(pred,s)
    elif kind=='joint':
        pred={k:obj.get(k) for k in s['keys']}
        valid=set(obj)==set(s['keys']) and all(scalar_ok(obj[k],s) for k in s['keys'])
    elif kind=='verdict':
        pred=obj.get('label'); valid=set(obj)=={'label'} and isinstance(pred,str) and pred in LABELS
    elif kind=='action':
        pred=obj
        valid=(set(obj)=={'operation','target','amount'} and isinstance(obj.get('operation'),str)
               and obj['operation'] in OPERATIONS and isinstance(obj.get('target'),str)
               and bool(obj['target'].strip()) and type(obj.get('amount'))==int and obj['amount']>=0)
    else: raise ValueError('UNSUPPORTED_SCORE_KIND')
    if raw.get('infrastructure_error'): valid=False
    correct=bool(valid and type(pred)==type(expected) and pred==expected)
    status='INVALID' if not valid else 'NULL' if kind=='value' and pred is None else 'VALUE' if kind=='value' else 'VALID'
    # Auxiliary, diagnostic-only observation, never used to rescue malformed answers.
    return dict(status=status,schema_valid=valid,json_valid=jsonvalid,correct=correct,pred=pred,
        observed_object=obj,status_key_present='status' in obj,
        wrong_keys=sorted(set(obj)-set(['value'] if kind=='value' else s['keys'] if kind=='joint' else ['label'] if kind=='verdict' else ['operation','target','amount'])),
        truncated=bool(raw.get('truncated')),infrastructure_error=raw.get('infrastructure_error'),
        scorer_version=VERSION)

def selftest():
    g=dict(schema=dict(kind='value',domain='count',nullable=False),expected=12)
    cases=[('{"value":12}',False,True),('{"value":12,',True,True),('{"value":12',True,False),
           ('{"value":true}',False,False),('{"value":"12"}',False,False),
           ('{"value":12,"value":12}',False,False),('{"value":12} {}',False,False),
           ('{"status":"VALUE","value":12}',False,False),('{"value":12e',True,False),
           ('{"value":null}',False,False)]
    for text,trunc,wanted in cases:
        assert score(dict(raw_response=text,truncated=trunc),g)['correct']==wanted,(text,wanted)
    nullable=dict(schema=dict(g['schema'],nullable=True),expected=None)
    assert score(dict(raw_response='{"value":null}'),nullable)['correct']
    assert score(None,g)['correct'] is None
    for k in ['SUPPORTED','CONTRADICTORY','UNKNOWN']:
        assert score(dict(raw_response=json.dumps({'label':k})),dict(schema={'kind':'verdict'},expected=k))['correct']
    joint=dict(schema=dict(kind='joint',domain='count',nullable=True,keys=['PRE','POST']),expected={'PRE':1,'POST':2})
    assert score(dict(raw_response='{"POST":2,"PRE":1}'),joint)['correct']
    assert not score(dict(raw_response='{"POST":1,"PRE":2}'),joint)['correct']
    assert score(dict(raw_response='{"POST":null,"PRE":1}'),joint)['schema_valid']
    return dict(status='PASS',tests=18)
