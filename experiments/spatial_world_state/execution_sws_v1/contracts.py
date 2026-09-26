"""Fixed, gold-blind SWS interface and explicit partial-count constraint evaluator."""
import sys
from common import CODE, load
sys.path.insert(0,str(__import__('pathlib').Path(load(CODE/'config.json')['package'])/'tools'))
from research_utils import strict_json_loads, typed_equal

VERSION='sws_fixed_interface_v1'

def count_label(lower,upper,claim):
    if type(lower) is not int or lower<0: raise ValueError('INVALID_LOWER_BOUND')
    if upper is not None and (type(upper) is not int or upper<lower): raise ValueError('INCONSISTENT_BOUND')
    if type(claim) is not int or claim<0: raise ValueError('INVALID_CLAIM')
    if claim<lower or upper is not None and claim>upper: return 'CONTRADICTORY'
    if lower==upper==claim: return 'SUPPORTED'
    return 'UNKNOWN'

def value_ok(v,schema):
    if v is None: return bool(schema.get('nullable',True))
    if schema['domain']=='count': return type(v) is int and v>=0
    if schema['domain']=='enum': return type(v) is str and v in schema['values']
    raise ValueError('UNSUPPORTED_DOMAIN')

def parse(text,schema):
    result=dict(parser_version=VERSION,raw_preserved=True,status='INVALID',parsed=None,actual_key_order=[],normalization='NONE',component_values={})
    try: obj=strict_json_loads(text.strip())
    except (ValueError,TypeError): result['reason']='MALFORMED_OR_DUPLICATE_JSON'; return result
    if not isinstance(obj,dict): result['reason']='NON_OBJECT'; return result
    result['actual_key_order']=list(obj)
    if set(obj)=={'query_value'} and schema['kind']=='value':
        obj={'value':obj['query_value']}; result['normalization']='SOLE_QUERY_VALUE_ALIAS'
    result['parsed']=obj
    kind=schema['kind']; required={'value'} if kind=='value' else {'verdict'} if kind=='verdict' else {'facts'} if kind=='facts' else {'value','verdict'}
    if 'value' in obj and value_ok(obj['value'],schema): result['component_values']['value']=obj['value']
    if 'verdict' in obj and obj['verdict'] in ('SUPPORTED','CONTRADICTORY','UNKNOWN'): result['component_values']['verdict']=obj['verdict']
    if 'facts' in obj:
        facts=obj['facts']; ids=[]; clean={}; valid=isinstance(facts,list)
        if valid:
            for f in facts:
                if not isinstance(f,dict) or set(f)!={'query_id','value'} or not isinstance(f['query_id'],str): valid=False; break
                ids.append(f['query_id'])
                if not value_ok(f['value'],schema): valid=False; break
                clean[f['query_id']]=f['value']
            valid=valid and len(ids)==len(set(ids)) and set(ids)==set(schema['query_ids'])
        if valid: result['component_values']['facts']=clean
    result['status']='VALID' if set(obj)==required and set(result['component_values'])==required else 'INVALID'
    result['order_compliant']=result['actual_key_order']==schema.get('order',result['actual_key_order'])
    result['reason']=None if result['status']=='VALID' else 'SCHEMA_OR_DOMAIN_MISMATCH_COMPONENTS_RETAINED'
    return result

def legal_count_update(pre,amount,action):
    if type(pre) is not int or pre<0 or type(amount) is not int or amount<0: raise ValueError('INVALID_ACTION_ARGUMENT')
    if action=='ADD': return pre+amount
    if action=='REMOVE' and pre>=amount: return pre-amount
    if action=='NOOP' and amount==0: return pre
    raise ValueError('ILLEGAL_TRANSITION')
