"""Frozen v2 scalar adapter; explicit versioned nullable-action extension only."""
import sys
from pathlib import Path
from v3common import CODE
sys.path.insert(0, str(CODE.parent/'src'))
sys.path.insert(0, str(CODE.parent/'format_repair_v2'))
from format_adapter_v2 import canonicalize, score_v2, selftest as adapter_selftest
from scorer import observed, scalar_ok


def parse(raw, schema):
    if raw is None:
        return dict(status='NOT_RUN', pred=None, extractable_valid=None, strict_contract_ok=None, normalization='NONE')
    if raw.get('infrastructure_error'):
        return dict(status='INFRA_FAILURE', pred=None, extractable_valid=False, strict_contract_ok=False, normalization='NONE')
    normalized, audit = canonicalize(raw, schema)
    obj, _ = observed(normalized.get('raw_response',''), normalized.get('truncated',False))
    original, original_json = observed(raw.get('raw_response',''), raw.get('truncated',False))
    kind = schema['kind']
    if kind == 'value':
        valid = set(obj) == {'value'} and scalar_ok(obj['value'], schema)
        pred = obj.get('value')
        strict = set(original) == {'value'} and scalar_ok(original['value'], schema)
        state = 'NULL' if pred is None else 'VALUE'
    elif kind == 'joint':
        valid = set(obj) == set(schema['keys']) and all(scalar_ok(obj[k], schema) for k in schema['keys'])
        pred = obj
        strict = valid
        state = 'VALID_JOINT'
    elif kind == 'verdict':
        pred = obj.get('label')
        valid = set(obj) == {'label'} and isinstance(pred,str) and pred in ['SUPPORTED','CONTRADICTORY','UNKNOWN']
        strict = valid
        state = 'VALID_LABEL'
    elif kind == 'action':
        valid = (set(obj) == {'operation','target','amount'} and
                 (obj.get('operation') is None or obj['operation'] in schema['operations']) and
                 (obj.get('target') is None or isinstance(obj['target'],str) and bool(obj['target'].strip())) and
                 (obj.get('amount') is None or type(obj['amount']) is int and obj['amount'] >= 0))
        pred = obj
        strict = valid
        state = 'VALID_ACTION'
    else:
        raise ValueError('UNSUPPORTED_SCHEMA')
    return dict(status=state if valid else 'INVALID', pred=pred, extractable_valid=bool(valid),
                strict_contract_ok=bool(strict), normalization=audit['normalization'], original_json_valid=original_json,
                key_order=list(original), truncated=bool(raw.get('truncated')), parse_version='a1_value_alias_v2_with_v3_nullable_action')


def score(raw, gold):
    out = parse(raw, gold['schema'])
    out['correct'] = None
    out['component_scores'] = None
    if out['status'] in ['NOT_RUN','INFRA_FAILURE'] or not gold.get('condition_eligible',True):
        return out
    wanted = gold['expected']
    out['correct'] = bool(out['extractable_valid'] and type(out['pred']) is type(wanted) and out['pred'] == wanted)
    if gold['schema']['kind'] == 'action':
        pred = out['pred'] or {}
        out['component_scores'] = {k: bool(out['extractable_valid'] and type(pred.get(k)) is type(wanted[k]) and pred.get(k) == wanted[k]) for k in wanted}
        out['target_scope'] = 'CATEGORY_ONLY'
        out['entity_grounding'] = 'NOT_MEASURED'
    return out
