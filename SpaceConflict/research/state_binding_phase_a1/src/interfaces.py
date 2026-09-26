"""Frozen A1 public interfaces; no gold values in schemas or exemplars."""
from common import digest

SYSTEM = ('Answer the specified diagnostic query using only the supplied evidence. '
          'Return one JSON object and no explanation, markdown, status key, or extra keys. '
          'Do not exceed 512 generated tokens. Content beyond that limit is ignored; '
          'only explicit retained output is scored. Do not continue another request.')
LABELS = ['SUPPORTED','CONTRADICTORY','UNKNOWN']
OPERATIONS = ['ADD','REMOVE','REPLACE','MOVE','SWAP']

def instruction(schema):
    domain=schema.get('domain','count')
    val='a nonnegative JSON integer (not a quoted number)' if domain=='count' else 'one of '+', '.join(domain)
    null='; JSON null is allowed only if the requested fact is genuinely unavailable' if schema.get('nullable') else '; null and UNDETERMINED are not allowed because the table is explicit'
    if schema['kind']=='value': return 'Output exactly one key: value. Its value must be '+val+null+'.'
    if schema['kind']=='joint': return 'Output exactly these keys in the requested order: '+', '.join(schema['keys'])+'. Each entry must be '+val+null+'.'
    if schema['kind']=='verdict':
        return ('Output exactly one key: label. Use SUPPORTED if the target value equals the claim value; '
                'CONTRADICTORY if the target value is known and differs; UNKNOWN only if target evidence is missing. '
                'Compare against the specified target only. No status or value key.')
    if schema['kind']=='action':
        return ('Output exactly operation, target, amount. operation: ADD, REMOVE, REPLACE, MOVE, or SWAP. '
                'target: the exact affected object category named in the intervention; amount: '
                'the explicitly affected number of objects as a nonnegative JSON integer. '
                'Do not output any PRE or POST value.')
    raise ValueError('UNSUPPORTED_INTERFACE')

def request(cfg,group,condition,text,schema,media=None,**extra):
    payload=dict(system=SYSTEM,text=text+'\n'+instruction(schema),media=media or [])
    r=dict(run_id=cfg['run_id'],prompt_version=cfg['prompt_version'],group_id=group,
           cluster_id=group,condition=condition,schema=schema,payload=payload,
           models=list(cfg['models']),**extra)
    r['request_id']='a1_'+digest(r)[:28]
    return r
